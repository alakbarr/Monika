"""
Remediasi dan Normalisasi Riwayat Biaya API & Status Budget AI.

Skrip ini:
1. Menyelaraskan kembali entri kalkulasi biaya siklus pada SystemConfig(key='api_cost_tracking')
   dengan aturan pricing terbaru (Free tier Gemini, Groq, OpenRouter :free, Ollama vs Paid tier).
2. Mengeksekusi CostTracker.check_and_update_budget_status() untuk memastikan
   Single Source of Truth (TokenUsageLog) tersinkronisasi dan me-reset flag 'budget_pause' ke false.
"""

import asyncio
import json
import logging
import sys
import os

# Ensure trading-agent is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("RemediateBudgetHistory")


async def remediate_budget():
    from database.db import AsyncSessionLocal
    from database.models import SystemConfig, TokenUsageLog
    from sqlalchemy import select, func
    from utils.analytics.pricing import cost_usd, infer_provider_from_model
    from utils.analytics.cost_tracker import CostTracker
    from config.settings import load_settings

    settings = load_settings()

    async with AsyncSessionLocal() as session:
        # 1. Inspect and normalize api_cost_tracking
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "api_cost_tracking")
        )).scalar_one_or_none()

        if cfg and cfg.value:
            try:
                history = json.loads(cfg.value)
            except Exception:
                history = []

            logger.info(f"Ditemukan {len(history)} entri dalam api_cost_tracking. Memulai normalisasi...")
            updated_count = 0

            for entry in history:
                if not isinstance(entry, dict):
                    continue

                stage1_model = entry.get("stage1_model", "")
                stage2_model = entry.get("stage2_model", "")
                stage1_tokens = entry.get("stage1_tokens", 0)
                stage2_tokens = entry.get("stage2_tokens", 0)
                total_in = entry.get("total_input_tokens", 0)
                total_out = entry.get("total_output_tokens", 0)

                # Split in/out proportionally if detailed split is missing
                s1_in = int(stage1_tokens * 0.9) if stage1_tokens > 0 else 0
                s1_out = stage1_tokens - s1_in
                s2_in = int(stage2_tokens * 0.9) if stage2_tokens > 0 else 0
                s2_out = stage2_tokens - s2_in

                p1 = infer_provider_from_model(stage1_model)
                p2 = infer_provider_from_model(stage2_model)

                old_cost = entry.get("total_cost_usd", 0.0)
                recalc_cost1 = cost_usd(stage1_model, s1_in, s1_out, provider=p1)
                recalc_cost2 = cost_usd(stage2_model, s2_in, s2_out, provider=p2)
                recalc_cost = round(recalc_cost1 + recalc_cost2, 4)

                if old_cost != recalc_cost:
                    logger.info(
                        f"  [NORMALIZE] Cycle {entry.get('cycle_date')}: "
                        f"${old_cost:.4f} -> ${recalc_cost:.4f} (Model: {stage1_model}, {stage2_model})"
                    )
                    entry["total_cost_usd"] = recalc_cost
                    updated_count += 1

            cfg.value = json.dumps(history)
            await session.commit()
            logger.info(f"Selesai menormalisasi {updated_count} entri yang terdistorsi.")

        # 2. Sinkronisasi dan evaluasi ulang Budget Status via SSOT (TokenUsageLog)
        b_stat = await CostTracker.check_and_update_budget_status(session, settings)
        logger.info(
            f"Status Budget Terbaru:\n"
            f"  • MTD Cost     : ${b_stat['mtd_cost']:.4f} / ${b_stat['monthly_budget']:.2f} ({b_stat['usage_pct']:.1f}%)\n"
            f"  • Daily Cost   : ${b_stat['daily_cost']:.4f} / ${b_stat['daily_budget']:.2f}\n"
            f"  • Budget Paused: {b_stat['is_paused']}"
        )

        if not b_stat['is_paused']:
            logger.info("✅ SUCCESS: Flag budget_pause telah bersih (false) dan AI trading dapat berjalan normal.")
        else:
            logger.warning("⚠️ Budget masih ter-pause. Periksa kembali batasan anggaran Anda.")


if __name__ == "__main__":
    asyncio.run(remediate_budget())
