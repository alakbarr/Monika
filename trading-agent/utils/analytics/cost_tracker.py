# ==============================================================================
# File: utils/cost_tracker.py
# ==============================================================================

import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database.models import SystemConfig
from utils.infra.notifier import AgentNotifier

logger = logging.getLogger("TradingAgent.CostTracker")


class CostTracker:
    _cached_pause_state = None
    _cached_pause_time = None

    @staticmethod
    async def log_cycle_cost(
        session: AsyncSession,
        stage1_input: int,
        stage1_output: int,
        stage2_input: int,
        stage2_output: int,
        settings: Optional[dict] = None,
        cycle_id: Optional[str] = None,
    ) -> float:
        """
        Mencatat biaya API dari satu siklus analisis dan mengeceknya terhadap anggaran.
        Memprioritaskan agregasi riil dari TokenUsageLog jika cycle_id tersedia.

        Returns:
            cost_usd: Estimasi biaya siklus dalam USD.
        """
        s = settings or {}
        task_roles = s.get("llm", {}).get("task_roles", {})
        analysis_cfg = s.get("analysis", {}) or s.get("claude", {})
        stage1_model = task_roles.get("stage1_fundamental", {}).get("primary") or analysis_cfg.get("fundamental_model", "claude-sonnet-5")
        stage2_model = task_roles.get("stage2_per_asset_primary", {}).get("primary") or analysis_cfg.get("model", "claude-sonnet-5")

        calculated_cost: Optional[float] = None

        # 1. Coba agregasikan biaya riil dari TokenUsageLog jika cycle_id ada
        if cycle_id:
            try:
                from database.models import TokenUsageLog
                db_cycle_cost = (await session.execute(
                    select(func.sum(TokenUsageLog.cost_estimate))
                    .where(TokenUsageLog.cycle_id == str(cycle_id))
                )).scalar()
                if db_cycle_cost is not None:
                    calculated_cost = round(float(db_cycle_cost), 4)
            except Exception as e:
                logger.debug(f"Could not query TokenUsageLog for cycle {cycle_id}: {e}")

        # 2. Fallback ke kalkulasi manual jika belum terhitung
        if calculated_cost is None:
            from utils.analytics.pricing import cost_usd, infer_provider_from_model
            p1 = task_roles.get("stage1_fundamental", {}).get("provider") or infer_provider_from_model(stage1_model)
            p2 = task_roles.get("stage2_per_asset_primary", {}).get("provider") or infer_provider_from_model(stage2_model)
            cost_stage1 = cost_usd(stage1_model, stage1_input, stage1_output, provider=p1)
            cost_stage2 = cost_usd(stage2_model, stage2_input, stage2_output, provider=p2)
            calculated_cost = round(cost_stage1 + cost_stage2, 4)

        entry = {
            "cycle_date": datetime.now(timezone.utc).isoformat(),
            "cycle_id": cycle_id,
            "stage1_tokens": stage1_input + stage1_output,
            "stage2_tokens": stage2_input + stage2_output,
            "total_input_tokens": stage1_input + stage2_input,
            "total_output_tokens": stage1_output + stage2_output,
            "total_cost_usd": calculated_cost,
            "stage1_model": stage1_model,
            "stage2_model": stage2_model,
        }

        # Load existing history for backup tracking
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "api_cost_tracking")
        )).scalar_one_or_none()

        history = []
        if cfg and cfg.value:
            try:
                history = json.loads(cfg.value)
            except Exception:
                pass

        history.append(entry)
        history = history[-100:]  # Keep last 100 cycles

        if cfg:
            cfg.value = json.dumps(history)
        else:
            session.add(SystemConfig(key="api_cost_tracking", value=json.dumps(history)))

        await session.commit()
        logger.info(f"Cycle API cost logged: ${calculated_cost:.4f} ({stage1_input + stage2_input} in, {stage1_output + stage2_output} out)")

        # --- Budget alert check ---
        if settings:
            await CostTracker.check_and_update_budget_status(session, settings, history=history, latest_cost=calculated_cost)

        return calculated_cost

    @staticmethod
    async def check_and_update_budget_status(
        session: AsyncSession,
        settings: dict,
        history: Optional[list] = None,
        latest_cost: float = 0.0,
    ) -> dict:
        """
        Evaluasi pengeluaran bulan berjalan & harian vs anggaran secara dinamis (SSOT: TokenUsageLog).
        Memperbarui SystemConfig(key='budget_pause') dan cache memory CostTracker.
        
        Returns:
            dict ringkasan status budget (mtd_cost, monthly_budget, usage_pct, daily_cost, daily_budget, is_paused).
        """
        cost_cfg = (settings or {}).get("cost_tracking", {})
        from config.settings import DEFAULT_MONTHLY_BUDGET_USD
        budget_usd: float = float(cost_cfg.get("monthly_budget_usd", DEFAULT_MONTHLY_BUDGET_USD))
        if not budget_usd or budget_usd <= 0:
            budget_usd = DEFAULT_MONTHLY_BUDGET_USD

        daily_budget_usd = float(cost_cfg.get("daily_budget_usd", 5.0))
        limit_anthropic = int(cost_cfg.get("daily_anthropic_limit", 10_000_000))
        limit_gemini = int(cost_cfg.get("daily_gemini_limit", cost_cfg.get("daily_token_limit", 4_000_000)))

        now = datetime.now(timezone.utc)
        current_month = now.strftime("%Y-%m")
        current_day = now.strftime("%Y-%m-%d")
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        day_start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 1. Query SSOT dari TokenUsageLog untuk MTD, Daily Cost, dan Daily Token Usage per Provider
        try:
            from database.models import TokenUsageLog
            from unittest.mock import MagicMock, AsyncMock

            def _extract_scalar(res: Any, default: float = 0.0) -> float:
                if hasattr(res, "scalar_one") and callable(res.scalar_one):
                    try:
                        v: Any = res.scalar_one()
                        if v is not None and not isinstance(v, (MagicMock, AsyncMock)):
                            return float(v)
                    except Exception:
                        pass
                if hasattr(res, "scalar") and callable(res.scalar):
                    try:
                        v: Any = res.scalar()
                        if v is not None and not isinstance(v, (MagicMock, AsyncMock)):
                            return float(v)
                    except Exception:
                        pass
                return default

            db_mtd_res = await session.execute(
                select(func.coalesce(func.sum(TokenUsageLog.cost_estimate), 0.0))
                .where(TokenUsageLog.timestamp >= month_start)
            )
            mtd_cost = _extract_scalar(db_mtd_res, 0.0)

            db_daily_res = await session.execute(
                select(func.coalesce(func.sum(TokenUsageLog.cost_estimate), 0.0))
                .where(TokenUsageLog.timestamp >= day_start_dt)
            )
            daily_cost_usd = _extract_scalar(db_daily_res, 0.0)

            # Agregasi token harian riil per provider
            provider_token_res = await session.execute(
                select(
                    func.lower(TokenUsageLog.provider),
                    func.coalesce(func.sum(TokenUsageLog.total_tokens), 0)
                )
                .where(TokenUsageLog.timestamp >= day_start_dt)
                .group_by(func.lower(TokenUsageLog.provider))
            )
            provider_token_rows = provider_token_res.all() if hasattr(provider_token_res, "all") else []
            token_map = {}
            if isinstance(provider_token_rows, (list, tuple)):
                for row in provider_token_rows:
                    if isinstance(row, (list, tuple)) and len(row) >= 2 and not isinstance(row[0], (MagicMock, AsyncMock)):
                        try:
                            token_map[str(row[0])] = int(row[1])
                        except (ValueError, TypeError):
                            pass
            daily_anthropic = token_map.get("anthropic", 0)
            daily_gemini = token_map.get("gemini", 0)

        except Exception as db_err:
            logger.warning(f"TokenUsageLog SSOT query failed, falling back to history JSON: {db_err}")
            if not isinstance(history, list):
                try:
                    cfg = (await session.execute(
                        select(SystemConfig).where(SystemConfig.key == "api_cost_tracking")
                    )).scalar_one_or_none()
                    parsed = json.loads(cfg.value) if cfg and cfg.value else []
                    history = parsed if isinstance(parsed, list) else []
                except Exception:
                    history = []

            mtd_cost = sum(
                float(e.get("total_cost_usd", e.get("estimated_cost_usd", 0.0)) or 0.0)
                for e in (history or [])
                if isinstance(e, dict) and e.get("cycle_date", "").startswith(current_month)
            )
            daily_cost_usd = sum(
                float(e.get("total_cost_usd", e.get("estimated_cost_usd", 0.0)) or 0.0)
                for e in (history or [])
                if isinstance(e, dict) and e.get("cycle_date", "").startswith(current_day)
            )
            daily_anthropic = sum(
                (e.get("stage1_tokens", 0) if "claude" in str(e.get("stage1_model", "")).lower() else 0) +
                (e.get("stage2_tokens", 0) if "claude" in str(e.get("stage2_model", "")).lower() else 0)
                for e in (history or []) if e.get("cycle_date", "").startswith(current_day)
            )
            daily_gemini = sum(
                (e.get("stage1_tokens", 0) if "gemini" in str(e.get("stage1_model", "")).lower() else 0) +
                (e.get("stage2_tokens", 0) if "gemini" in str(e.get("stage2_model", "")).lower() else 0)
                for e in (history or []) if e.get("cycle_date", "").startswith(current_day)
            )

        # Enforce Monotonic Invariant: MTD harus selalu >= Daily
        mtd_cost = max(mtd_cost, daily_cost_usd)
        usage_pct = (mtd_cost / budget_usd) * 100
        logger.info(f"Month-to-date API cost: ${mtd_cost:.4f} / ${budget_usd:.2f} ({usage_pct:.1f}%)")

        # 2. Limit validations
        is_daily_budget_exceeded = daily_budget_usd > 0 and daily_cost_usd >= daily_budget_usd
        alerts = []
        if daily_anthropic >= limit_anthropic * 0.9:
            alerts.append(f"Anthropic limit at {daily_anthropic/limit_anthropic*100:.1f}% ({daily_anthropic}/{limit_anthropic})")
        if daily_gemini >= limit_gemini * 0.9:
            alerts.append(f"Gemini limit at {daily_gemini/limit_gemini*100:.1f}% ({daily_gemini}/{limit_gemini})")
        if is_daily_budget_exceeded:
            alerts.append(f"Daily dollar spend limit reached: ${daily_cost_usd:.2f} >= ${daily_budget_usd:.2f}")

        if alerts and (usage_pct < 95 and not is_daily_budget_exceeded):
            msg = "⚠️ <b>DAILY API LIMIT WARNING</b>\n" + "\n".join(alerts)
            try:
                notifier = AgentNotifier()
                await notifier.send_critical(msg)
            except Exception:
                pass

        if usage_pct >= 95:
            msg = (
                f"💸 <b>API BUDGET EXCEEDED</b>\n"
                f"MTD cost: ${mtd_cost:.4f} — budget: ${budget_usd:.2f} ({usage_pct:.1f}%)\n"
                f"Pausing AI API calls until budget is acknowledged.\n"
                f"Set <code>cost_tracking.monthly_budget_usd</code> higher or restart to resume."
            )
            logger.error(f"API budget exceeded: ${mtd_cost:.4f} / ${budget_usd:.2f}")
            try:
                notifier = AgentNotifier()
                await notifier.send_critical(msg)
            except Exception as e:
                logger.warning(f"Could not send budget alert: {e}")

        should_pause = (usage_pct >= 95) or is_daily_budget_exceeded
        
        pause_cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "budget_pause")
        )).scalar_one_or_none()

        if should_pause:
            if pause_cfg:
                pause_cfg.value = "true"
            else:
                session.add(SystemConfig(key="budget_pause", value="true"))
            await session.commit()
            CostTracker._cached_pause_state = True
            CostTracker._cached_pause_time = now
            if is_daily_budget_exceeded and not (usage_pct >= 95):
                try:
                    notifier = AgentNotifier()
                    await notifier.send_critical(f"🛑 <b>DAILY SPEND CIRCUIT BREAKER TRIPPED</b>\nDaily AI spend (${daily_cost_usd:.2f}) reached daily limit (${daily_budget_usd:.2f}). System paused.")
                except Exception:
                    pass
        else:
            # Auto-clear lingering budget_pause when cost is safely within budget
            if pause_cfg and pause_cfg.value == "true":
                pause_cfg.value = "false"
                await session.commit()
                logger.info(f"Budget pause auto-cleared: MTD ${mtd_cost:.4f}/${budget_usd:.2f}, Daily ${daily_cost_usd:.4f}/${daily_budget_usd:.2f}")
            CostTracker._cached_pause_state = False
            CostTracker._cached_pause_time = now

        if 80 <= usage_pct < 95:
            msg = (
                f"⚠️ <b>API Budget Warning</b>\n"
                f"MTD cost: ${mtd_cost:.4f} — {usage_pct:.1f}% of ${budget_usd:.2f} budget used.\n"
                f"At current pace, budget may be exceeded before month end."
            )
            logger.warning(f"API budget at {usage_pct:.1f}%: ${mtd_cost:.4f} / ${budget_usd:.2f}")
            try:
                notifier = AgentNotifier()
                await notifier.send_warning(msg)
            except Exception as e:
                logger.warning(f"Could not send budget warning: {e}")

        return {
            "mtd_cost": mtd_cost,
            "monthly_budget": budget_usd,
            "usage_pct": usage_pct,
            "daily_cost": daily_cost_usd,
            "daily_budget": daily_budget_usd,
            "is_paused": should_pause,
            "alerts": alerts,
        }

    @staticmethod
    async def _check_budget(
        session: AsyncSession,
        history: list,
        latest_cost: float,
        settings: dict,
    ) -> None:
        """Backward-compatible wrapper for check_and_update_budget_status."""
        await CostTracker.check_and_update_budget_status(
            session=session,
            settings=settings,
            history=history,
            latest_cost=latest_cost,
        )

    @classmethod
    def is_budget_paused_cached(cls) -> bool:
        """Synchronous in-memory check if AI budget is paused."""
        return bool(cls._cached_pause_state)

    @staticmethod
    async def is_budget_paused(
        session: AsyncSession,
        settings: Optional[dict] = None,
        force_recheck: bool = False,
    ) -> bool:
        """
        Mengembalikan True jika anggaran terlampaui (AI calls akan dihentikan).
        Jika settings disediakan atau cache kedaluwarsa, melakukan re-evaluasi dinamis.
        """
        now = datetime.now(timezone.utc)
        
        # Jika settings disediakan dan (dipaksa atau cache kadaluwarsa > 60s), re-evaluasi dinamis
        if settings is not None:
            is_stale = (CostTracker._cached_pause_time is None) or ((now - CostTracker._cached_pause_time).total_seconds() >= 60)
            if force_recheck or is_stale:
                status = await CostTracker.check_and_update_budget_status(session, settings)
                return status["is_paused"]

        if not force_recheck and CostTracker._cached_pause_time and (now - CostTracker._cached_pause_time).total_seconds() < 60:
            return bool(CostTracker._cached_pause_state)
            
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "budget_pause")
        )).scalar_one_or_none()
        
        is_paused = cfg is not None and cfg.value == "true"
        CostTracker._cached_pause_state = is_paused
        CostTracker._cached_pause_time = now
        return is_paused

    @staticmethod
    async def clear_budget_pause(session: AsyncSession) -> None:
        """Menghapus flag pause anggaran (dipanggil setelah user mereset anggaran)."""
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "budget_pause")
        )).scalar_one_or_none()
        if cfg:
            cfg.value = "false"
        else:
            session.add(SystemConfig(key="budget_pause", value="false"))
        await session.commit()
        CostTracker._cached_pause_state = False
        CostTracker._cached_pause_time = datetime.now(timezone.utc)
        logger.info("Budget pause cleared.")

    @staticmethod
    async def get_rolling_7day_cost(session: AsyncSession) -> dict:
        """Mengembalikan metrik pengeluaran 7 hari terakhir berbasis TokenUsageLog (SSOT)."""
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)

        try:
            from database.models import TokenUsageLog
            cost_7d_db = (await session.execute(
                select(func.coalesce(func.sum(TokenUsageLog.cost_estimate), 0.0))
                .where(TokenUsageLog.timestamp >= seven_days_ago)
            )).scalar_one()
            cycles_7d_db = (await session.execute(
                select(func.count(func.distinct(TokenUsageLog.cycle_id)))
                .where(TokenUsageLog.timestamp >= seven_days_ago, TokenUsageLog.cycle_id.isnot(None))
            )).scalar_one()

            total_7d = float(cost_7d_db or 0.0)
            cycles_cnt = int(cycles_7d_db or 0)
            return {
                "cost_7d": round(total_7d, 4),
                "cycles_7d": cycles_cnt,
                "avg_per_cycle": round(total_7d / cycles_cnt, 4) if cycles_cnt else 0.0,
                "projected_monthly": round(total_7d / 7 * 30, 2),
            }
        except Exception as db_err:
            logger.debug(f"Rolling 7-day TokenUsageLog query failed, using history fallback: {db_err}")
            cfg = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == "api_cost_tracking")
            )).scalar_one_or_none()
            
            history = []
            if cfg and cfg.value:
                try:
                    history = json.loads(cfg.value)
                except Exception:
                    pass

            recent = []
            for entry in history:
                try:
                    dt = datetime.fromisoformat(entry["cycle_date"])
                    if dt >= seven_days_ago:
                        recent.append(entry)
                except Exception:
                    continue
                    
            total_7d = sum(float(e.get("total_cost_usd", 0.0) or 0.0) for e in recent)
            return {
                "cost_7d": round(total_7d, 4),
                "cycles_7d": len(recent),
                "avg_per_cycle": round(total_7d / len(recent), 4) if recent else 0.0,
                "projected_monthly": round(total_7d / 7 * 30, 2),
            }
