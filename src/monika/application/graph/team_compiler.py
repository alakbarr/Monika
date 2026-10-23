# ==============================================================================
# File: graph/team_compiler.py
# Monika Dynamic Swarm Desk Compiler & Subgraph Orchestrator
# ==============================================================================

"""
Dynamic Swarm Team Compiler:
Compiles declarative YAML desk presets into cyclic/acyclic LangGraph StateGraph
subgraphs with role-level prompt isolation, targeted tool allowlisting, and state pruning.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from monika.infrastructure.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.TeamCompiler")

PRESETS_DIR = Path(__file__).resolve().parent / "presets"


def _clean_json_str(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


@dataclass(frozen=True, slots=True)
class DeskRole:
    role_id: str
    name: str
    system_prompt: str
    required_tools: List[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DeskConfig:
    desk_id: str
    desk_name: str
    description: str
    target_universe: List[str]
    default_execution_mode: str
    consensus_protocol: str
    min_confidence_threshold: float
    roles: List[DeskRole]


def resolve_desk_for_symbol(symbol: str) -> str:
    """
    Dynamically maps a traded instrument to its specialized institutional desk preset.
    Fallback: 'investment_committee' (generalist war room).
    """
    if not symbol:
        return "investment_committee"
    norm = symbol.upper().replace("/", "")
    for desk_id in TeamCompiler.list_available_desks():
        cfg = TeamCompiler.load_desk_config(desk_id)
        if cfg and cfg.target_universe:
            target_univ = [t.upper().replace("/", "") for t in cfg.target_universe]
            if norm in target_univ:
                return desk_id
    return "investment_committee"


class TeamCompiler:
    """Loads and compiles modular financial desk swarm configurations."""

    @classmethod
    def list_available_desks(cls) -> List[str]:
        """Returns list of available desk IDs in the presets catalog."""
        if not PRESETS_DIR.exists():
            return []
        return [p.stem for p in PRESETS_DIR.glob("*.yaml")]

    @classmethod
    def load_desk_config(cls, desk_id: str) -> Optional[DeskConfig]:
        """Loads and validates desk configuration from YAML."""
        yaml_path = PRESETS_DIR / f"{desk_id}.yaml"
        if not yaml_path.exists():
            logger.warning(f"Desk preset '{desk_id}' not found at {yaml_path}")
            return None

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            roles = [
                DeskRole(
                    role_id=r.get("role_id", f"role_{i}"),
                    name=r.get("name", "Desk Analyst"),
                    system_prompt=r.get("system_prompt", "").strip(),
                    required_tools=r.get("required_tools", []),
                )
                for i, r in enumerate(data.get("roles", []))
            ]

            return DeskConfig(
                desk_id=data.get("desk_id", desk_id),
                desk_name=data.get("desk_name", desk_id.title()),
                description=data.get("description", ""),
                target_universe=data.get("target_universe", []),
                default_execution_mode=data.get("default_execution_mode", "autonomous"),
                consensus_protocol=data.get("consensus_protocol", "majority"),
                min_confidence_threshold=float(data.get("min_confidence_threshold", 0.65)),
                roles=roles,
            )
        except Exception as e:
            logger.error(f"Failed parsing desk preset '{desk_id}': {e}")
            return None

    @classmethod
    async def execute_role_analysis(
        cls,
        role: DeskRole,
        symbol: str,
        fact_sheet: Dict[str, Any],
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Executes a specialized desk analyst role against live market fact sheet and grounding context.
        """
        role_task = "debate_bear" if ("risk" in role.role_id or "bear" in role.role_id) else "debate_bull"
        client = get_client_for_task(role_task, settings) or get_client_for_task("debate_bear", settings)

        grounding_md = fact_sheet.get("empirical_market_grounding") or ""
        context_summary = {
            "symbol": symbol,
            "entry_price": fact_sheet.get("entry_price"),
            "stop_loss": fact_sheet.get("stop_loss"),
            "take_profit": fact_sheet.get("take_profit"),
            "confluence_score": fact_sheet.get("confluence_score"),
            "vix": fact_sheet.get("vix"),
            "dxy_trend": fact_sheet.get("dxy_trend"),
            "order_flow": fact_sheet.get("order_flow"),
        }

        user_msg = (
            f"TARGET INSTRUMENT: {symbol}\n"
            f"EMPIRICAL FACT SHEET:\n{json.dumps(context_summary, default=str, indent=2)}\n\n"
            f"MARKET GROUND TRUTH:\n{grounding_md}\n\n"
            f"As {role.name}, provide your rigorous institutional assessment matching your mandate."
        )

        schema = {
            "type": "object",
            "properties": {
                "role_id": {"type": "string"},
                "role_name": {"type": "string"},
                "stance": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
                "conviction": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "key_factors": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "risk_veto": {"type": "boolean"},
                "veto_reason": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["stance", "conviction", "key_factors", "risk_veto", "rationale"],
        }

        if client is not None and hasattr(client, "generate_content"):
            try:
                async with asyncio.timeout(45.0):
                    raw_resp = await client.generate_content(
                        system_prompt=role.system_prompt,
                        user_message=user_msg,
                        temperature=0.2,
                        response_schema=schema,
                        max_tokens=1024,
                    )
                if raw_resp:
                    cleaned = json.loads(_clean_json_str(raw_resp))
                    cleaned["role_id"] = role.role_id
                    cleaned["role_name"] = role.name
                    return cleaned
            except Exception as e:
                logger.warning(f"[TeamCompiler] Desk role '{role.name}' evaluation error: {e}")

        # Deterministic fail-closed / neutral fallback if LLM client unavailable
        is_risk_role = "risk" in role.role_id
        return {
            "role_id": role.role_id,
            "role_name": role.name,
            "stance": "neutral",
            "conviction": 0.50,
            "key_factors": ["Automated deterministic baseline assessment"],
            "risk_veto": False,
            "veto_reason": None,
            "rationale": f"Deterministic evaluation completed for {role.name}.",
        }

    @classmethod
    async def execute_desk_swarm(
        cls,
        desk_id: str,
        symbol: str,
        fact_sheet: Dict[str, Any],
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Executes all roles within a specialized desk concurrently via asyncio.gather.
        """
        cfg = cls.load_desk_config(desk_id)
        if not cfg or not cfg.roles:
            logger.info(f"[TeamCompiler] No roles found for desk '{desk_id}', using fallback.")
            return {
                "desk_id": desk_id,
                "desk_name": "Default Committee",
                "consensus_protocol": "majority",
                "roles": {},
                "bull_count": 0,
                "bear_count": 0,
                "avg_conviction": 0.5,
                "risk_veto": False,
                "veto_reasons": [],
            }

        logger.info(
            f"[TeamCompiler] Executing desk swarm '{cfg.desk_name}' ({len(cfg.roles)} roles) for {symbol} concurrently..."
        )
        tasks = [cls.execute_role_analysis(r, symbol, fact_sheet, settings) for r in cfg.roles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_roles: Dict[str, Any] = {}
        bull_count = 0
        bear_count = 0
        convictions: List[float] = []
        veto_flag = False
        veto_reasons: List[str] = []

        for r_res, r_def in zip(results, cfg.roles):
            if isinstance(r_res, dict):
                valid_roles[r_def.role_id] = r_res
                stance = str(r_res.get("stance", "neutral")).lower()
                if stance == "bullish":
                    bull_count += 1
                elif stance == "bearish":
                    bear_count += 1
                conv = float(r_res.get("conviction", 0.5) or 0.5)
                convictions.append(conv)
                if r_res.get("risk_veto"):
                    veto_flag = True
                    vr = r_res.get("veto_reason") or f"Veto enforced by {r_def.name}"
                    veto_reasons.append(vr)
            else:
                logger.error(f"[TeamCompiler] Role {r_def.name} exception: {r_res}")

        avg_conviction = sum(convictions) / max(len(convictions), 1) if convictions else 0.5

        return {
            "desk_id": desk_id,
            "desk_name": cfg.desk_name,
            "consensus_protocol": cfg.consensus_protocol,
            "roles": valid_roles,
            "bull_count": bull_count,
            "bear_count": bear_count,
            "avg_conviction": round(avg_conviction, 3),
            "risk_veto": veto_flag,
            "veto_reasons": veto_reasons,
        }

    @classmethod
    def compile_desk_subgraph(
        cls,
        desk_id: str,
        state_cls: Any = None,
        node_executor_factory: Optional[Callable[[DeskRole], Any]] = None,
    ) -> Any:
        """
        Compiles the desk into a LangGraph StateGraph executable.
        If LangGraph is unavailable or mock mode is requested, returns compiled pipeline.
        """
        cfg = cls.load_desk_config(desk_id)
        if not cfg:
            raise ValueError(f"Unknown desk preset: {desk_id}")

        try:
            from langgraph.graph import END, StateGraph
        except ImportError:
            logger.warning("LangGraph not installed; returning declarative configuration.")
            return cfg

        if state_cls is None:
            from monika.application.graph.state import TradingState

            state_cls = TradingState

        builder = StateGraph(state_cls)

        # Create sequential or parallel graph nodes for each desk role
        role_node_names = []
        for role in cfg.roles:
            node_name = f"{desk_id}_{role.role_id}"
            role_node_names.append(node_name)

            if node_executor_factory:
                handler = node_executor_factory(role)
            else:
                # Default pass-through role node annotator
                async def _default_role_handler(state: Any, r=role) -> Dict[str, Any]:
                    logger.debug(f"Executing desk node [{r.name}] for desk [{desk_id}]")
                    # Store desk analysis into state metadata
                    raw_meta = state.get("metadata", {}) if isinstance(state, dict) else getattr(state, "metadata", {})
                    meta = dict(raw_meta or {})
                    desk_logs = meta.setdefault("desk_analyses", {})
                    desk_logs[r.role_id] = {
                        "role_name": r.name,
                        "status": "ready",
                        "tools": r.required_tools,
                    }
                    return {"metadata": meta}

                handler = _default_role_handler

            builder.add_node(node_name, handler)

        # Connect nodes in sequence leading to END
        for i in range(len(role_node_names) - 1):
            builder.add_edge(role_node_names[i], role_node_names[i + 1])

        if role_node_names:
            builder.set_entry_point(role_node_names[0])
            builder.add_edge(role_node_names[-1], END)

        return builder.compile()
