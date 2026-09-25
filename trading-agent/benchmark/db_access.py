import json
from contextlib import contextmanager
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from analysis.tools.tool_executor import ToolExecutor
from analysis.schemas.schemas import SubmitAssetAnalysisSchema, SubmitFundamentalBriefSchema
from database.models import AssetAnalysis, FundamentalBrief, NewsItem, NewsDigest, DecisionReflection, TelegramConversation


class BenchmarkToolExecutor(ToolExecutor):
    """ToolExecutor sungguhan (semua tool baca = data live dari Postgres/MT5
    cache, identik dgn produksi) tapi tool tulis divalidasi via schema Pydantic
    ASLI lalu ditangkap di memori -- TIDAK PERNAH menulis ke Postgres."""

    def __init__(self, session, settings, model_name=None):
        super().__init__(session, settings, model_name=model_name)
        self.captured: dict | None = None

    async def _tool_submit_asset_analysis(self, inp: dict) -> dict:
        try:
            payload = SubmitAssetAnalysisSchema.model_validate(inp).model_dump(exclude_unset=True, mode="json")
        except ValidationError as e:
            return {"status": "validation_failed",
                    "errors": [f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors()]}
        self.captured = {"tool": "submit_asset_analysis", "payload": payload}
        return {"status": "saved", "analysis_id": -1, "symbol": payload.get("symbol"),
                "decision": payload.get("decision"), "message": "benchmark: tidak dipersist"}

    async def _tool_submit_fundamental_brief(self, inp: dict) -> dict:
        try:
            payload = SubmitFundamentalBriefSchema.model_validate(inp).model_dump(exclude_unset=True, mode="json")
        except ValidationError as e:
            return {"status": "validation_failed",
                    "errors": [f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors()]}
        self.captured = {"tool": "submit_fundamental_brief", "payload": payload}
        return {"status": "saved", "brief_id": -1, "valid_until": None}

    async def _tool_propose_action(self, inp: dict) -> dict:
        self.captured = {"tool": "propose_action", "payload": inp}
        return {"status": "proposed", "message": "benchmark: tidak dipersist",
                "action_type": inp.get("action_type"), "params": inp.get("params")}


# ---------------------------------------------------------------------------
# run_agent()/run_chat_loop() milik BaseLLMClient MEMBUAT ToolExecutor sendiri
# di dalam (tidak menerima instance dari luar). Untuk mode "agent"/"chat" kita
# terpaksa patch method tulis di CLASS ToolExecutor untuk sementara. Karena
# ini state global proses, runner.py WAJIB menyerialkan pemanggilan mode ini
# (lihat _AGENT_LOCK di runner.py) supaya tidak race dengan panggilan model
# lain yang berjalan paralel.
# ---------------------------------------------------------------------------
_capture_box: dict = {}


async def _capturing_submit_asset_analysis(self, inp: dict) -> dict:
    try:
        payload = SubmitAssetAnalysisSchema.model_validate(inp).model_dump(exclude_unset=True, mode="json")
    except ValidationError as e:
        return {"status": "validation_failed",
                "errors": [f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors()]}
    _capture_box["result"] = {"tool": "submit_asset_analysis", "payload": payload}
    return {"status": "saved", "analysis_id": -1, "symbol": payload.get("symbol"),
            "decision": payload.get("decision"), "message": "benchmark: tidak dipersist"}


async def _capturing_submit_fundamental_brief(self, inp: dict) -> dict:
    try:
        payload = SubmitFundamentalBriefSchema.model_validate(inp).model_dump(exclude_unset=True, mode="json")
    except ValidationError as e:
        return {"status": "validation_failed",
                "errors": [f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors()]}
    _capture_box["result"] = {"tool": "submit_fundamental_brief", "payload": payload}
    return {"status": "saved", "brief_id": -1, "valid_until": None}


async def _capturing_propose_action(self, inp: dict) -> dict:
    _capture_box["result"] = {"tool": "propose_action", "payload": inp}
    return {"status": "proposed", "message": "benchmark: tidak dipersist",
            "action_type": inp.get("action_type"), "params": inp.get("params")}


@contextmanager
def guarded_tool_executor():
    """Context manager: selama block ini aktif, ToolExecutor._tool_submit_* /
    _tool_propose_action di-patch supaya tidak menulis DB. Selalu dipulihkan
    (finally), termasuk saat exception. Kembalikan dict box -- box['result']
    berisi payload yang ditangkap (kalau model memanggil tool tsb)."""
    _capture_box.clear()
    orig = (ToolExecutor._tool_submit_asset_analysis,
            ToolExecutor._tool_submit_fundamental_brief,
            ToolExecutor._tool_propose_action)
    ToolExecutor._tool_submit_asset_analysis = _capturing_submit_asset_analysis
    ToolExecutor._tool_submit_fundamental_brief = _capturing_submit_fundamental_brief
    ToolExecutor._tool_propose_action = _capturing_propose_action
    try:
        yield _capture_box
    finally:
        (ToolExecutor._tool_submit_asset_analysis,
         ToolExecutor._tool_submit_fundamental_brief,
         ToolExecutor._tool_propose_action) = orig


# ---------------------------------------------------------------------------
# Data loaders -- SEMUA dari Postgres asli, tidak ada yang di-hardcode. Kalau
# tabel relevan masih kosong (mis. belum pernah menjalankan Stage 1/2), fungsi
# akan raise RuntimeError yang jelas dan task tsb otomatis di-skip oleh runner.
# ---------------------------------------------------------------------------

async def pick_asset_analysis(session: AsyncSession, symbol: str | None = None,
                               need_tradeable: bool = True) -> AssetAnalysis:
    q = select(AssetAnalysis)
    if symbol:
        q = q.where(AssetAnalysis.symbol == symbol)
    if need_tradeable:
        q = q.where(AssetAnalysis.decision.in_(["buy", "sell"]))
    row = (await session.execute(q.order_by(AssetAnalysis.generated_at.desc()).limit(1))).scalar_one_or_none()
    if row is None and need_tradeable:
        return await pick_asset_analysis(session, symbol, need_tradeable=False)
    if row is None:
        raise RuntimeError(
            f"Tidak ada baris AssetAnalysis di DB untuk symbol={symbol!r}. "
            "Jalankan Stage 2 minimal 1 siklus sebelum benchmark task ini."
        )
    return row


async def latest_brief(session: AsyncSession) -> FundamentalBrief:
    row = (await session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))).scalar_one_or_none()
    if row is None:
        raise RuntimeError("Tidak ada FundamentalBrief di DB -- jalankan Stage 1 dulu.")
    return row


async def latest_digest(session: AsyncSession) -> NewsDigest | None:
    return (await session.execute(select(NewsDigest).order_by(NewsDigest.generated_at.desc()).limit(1))).scalar_one_or_none()


async def recent_news(session: AsyncSession, limit: int = 8) -> list[NewsItem]:
    rows = (await session.execute(select(NewsItem).order_by(NewsItem.fetched_at.desc()).limit(limit))).scalars().all()
    if not rows:
        raise RuntimeError("Tidak ada NewsItem di DB -- jalankan scraper dulu.")
    return list(rows)


async def resolved_reflection(session: AsyncSession) -> DecisionReflection | None:
    return (await session.execute(
        select(DecisionReflection).where(DecisionReflection.status == "resolved")
        .order_by(DecisionReflection.resolved_at.desc()).limit(1)
    )).scalar_one_or_none()


async def latest_user_message(session: AsyncSession) -> str | None:
    row = (await session.execute(
        select(TelegramConversation).where(TelegramConversation.role == "user")
        .order_by(TelegramConversation.timestamp.desc()).limit(1)
    )).scalar_one_or_none()
    return row.message if row else None


def _safe_json_loads(val: Any, default: Any) -> Any:
    if not val:
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return default


def entry_context(analysis: AssetAnalysis) -> dict:
    ez = _safe_json_loads(analysis.entry_zone, {})
    return {
        "decision": (analysis.decision or "wait").upper(),
        "rationale": analysis.rationale,
        "confluence_score": analysis.confluence_score,
        "confluence_factors": _safe_json_loads(analysis.confluence_factors_json, []),
        "entry_price": (ez.get("price") if isinstance(ez, dict) else None) or analysis.price_at_analysis,
        "stop_loss": analysis.stop_loss,
        "take_profit": analysis.take_profit,
        "invalidation": analysis.invalidation,
    }
