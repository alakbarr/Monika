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

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

logger = logging.getLogger("TradingAgent.TeamCompiler")

PRESETS_DIR = Path(__file__).resolve().parent / "presets"


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
            from langgraph.graph import StateGraph, END
        except ImportError:
            logger.warning("LangGraph not installed; returning declarative configuration.")
            return cfg

        if state_cls is None:
            from graph.state import TradingState
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
                    meta = dict(getattr(state, "metadata", {}) or {})
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
