#!/usr/bin/env python3
"""
Compile Alpha Factors and Synthesized Strategies into JSON Data Catalogs.

Extracts all 468 quantitative alpha factors from indicators/alpha_zoo/factors/
and 112 synthesized strategies from analysis/strategies/synthesized/ into structured,
machine-readable JSON catalogs under data/alpha_catalog/.
"""

import ast
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AlphaCompiler")

ROOT_DIR = Path(__file__).resolve().parent.parent
TRADING_AGENT_DIR = ROOT_DIR / "trading-agent"
FACTORS_DIR = TRADING_AGENT_DIR / "indicators" / "alpha_zoo" / "factors"
SYNTHESIZED_DIR = TRADING_AGENT_DIR / "analysis" / "strategies" / "synthesized"
CATALOG_DIR = TRADING_AGENT_DIR / "data" / "alpha_catalog"


def map_category(theme_list: Optional[List[str]]) -> str:
    """Normalize raw theme tags into canonical AlphaCategory enum."""
    if not theme_list:
        return "momentum"
    primary = theme_list[0].lower().strip()
    mapping = {
        "reversal": "mean_reversion",
        "mean-reversion": "mean_reversion",
        "mean_reversion": "mean_reversion",
        "momentum": "momentum",
        "volatility": "volatility",
        "volume": "volume",
        "liquidity": "liquidity",
        "trend": "trend",
        "structural": "structural",
        "fundamental": "fundamental",
        "risk_premia": "risk_premia",
        "microstructure": "microstructure",
    }
    return mapping.get(primary, "momentum")


def extract_alpha_factor(file_path: Path) -> Optional[Dict[str, Any]]:
    """Extract metadata and compute function source from an alpha factor Python file via AST."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except Exception as e:
        logger.warning(f"Failed to parse {file_path.name}: {e}")
        return None

    meta_dict: Dict[str, Any] = {}
    compute_src: str = ""

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__alpha_meta__":
                    try:
                        meta_dict = ast.literal_eval(node.value)
                    except Exception:
                        pass
        elif isinstance(node, ast.FunctionDef) and node.name == "compute":
            # Extract compute source code slice
            start_line = node.lineno - 1
            end_line = getattr(node, "end_lineno", len(source.splitlines()))
            lines = source.splitlines()
            compute_src = "\n".join(lines[start_line:end_line])

    if not meta_dict and not compute_src:
        return None

    factor_id = meta_dict.get("id") or file_path.stem
    family = file_path.parent.name
    category = map_category(meta_dict.get("theme"))

    return {
        "id": factor_id,
        "name": factor_id,
        "family": family,
        "file_name": file_path.name,
        "nickname": meta_dict.get("nickname", factor_id),
        "category": category,
        "theme": meta_dict.get("theme", [category]),
        "columns_required": meta_dict.get("columns_required", ["close"]),
        "lookback": int(meta_dict.get("min_warmup_bars", 5) or 5),
        "min_warmup_bars": int(meta_dict.get("min_warmup_bars", 5) or 5),
        "decay_horizon": int(meta_dict.get("decay_horizon", 5) or 5),
        "direction": "positive_bullish",
        "formula_latex": meta_dict.get("formula_latex", ""),
        "description": meta_dict.get("notes", f"{factor_id} quantitative alpha factor"),
        "code": compute_src,
    }


def extract_synthesized_strategy(file_path: Path) -> Optional[Dict[str, Any]]:
    """Extract metadata, parameters, and symbols from a synthesized strategy file via AST."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except Exception as e:
        logger.warning(f"Failed to parse {file_path.name}: {e}")
        return None

    strategy_id = file_path.stem
    applicable_symbols = []
    params: Dict[str, Any] = {}

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "strategy_id" and isinstance(item.value, ast.Constant):
                                strategy_id = str(item.value.value)
                            elif target.id == "applicable_symbols":
                                try:
                                    applicable_symbols = list(ast.literal_eval(item.value))
                                except Exception:
                                    pass
                elif isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for stmt in item.body:
                        if isinstance(stmt, ast.Assign):
                            for target in stmt.targets:
                                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                                    param_name = target.attr
                                    if isinstance(stmt.value, ast.Call):
                                        # e.g. int(safe_settings.get("htf_lookback", 24))
                                        for arg in stmt.value.args:
                                            if isinstance(arg, ast.Call) and len(arg.args) >= 2:
                                                try:
                                                    default_val = ast.literal_eval(arg.args[1])
                                                    params[param_name] = default_val
                                                except Exception:
                                                    pass

    return {
        "strategy_id": strategy_id,
        "file_name": file_path.name,
        "applicable_symbols": applicable_symbols,
        "parameters": params,
        "code_lines": len(source.splitlines()),
    }


def compile_catalogs() -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Compile Alpha Factors
    logger.info(f"Scanning alpha factors in {FACTORS_DIR}...")
    factors: Dict[str, Any] = {}
    if FACTORS_DIR.exists():
        for py_file in sorted(FACTORS_DIR.rglob("*.py")):
            if py_file.name.startswith("__"):
                continue
            item = extract_alpha_factor(py_file)
            if item:
                factors[item["id"]] = item

    factors_out = CATALOG_DIR / "factors.json"
    factors_payload = {
        "version": "1.0",
        "total_count": len(factors),
        "factors": factors,
    }
    factors_out.write_text(json.dumps(factors_payload, indent=2), encoding="utf-8")
    logger.info(f"Saved {len(factors)} alpha factors to {factors_out}")

    # 2. Compile Synthesized Strategies
    logger.info(f"Scanning synthesized strategies in {SYNTHESIZED_DIR}...")
    strategies: Dict[str, Any] = {}
    if SYNTHESIZED_DIR.exists():
        for py_file in sorted(SYNTHESIZED_DIR.rglob("*.py")):
            if py_file.name.startswith("__"):
                continue
            item = extract_synthesized_strategy(py_file)
            if item:
                strategies[item["strategy_id"]] = item

    strategies_out = CATALOG_DIR / "synthesized_strategies.json"
    strategies_payload = {
        "version": "1.0",
        "total_count": len(strategies),
        "strategies": strategies,
    }
    strategies_out.write_text(json.dumps(strategies_payload, indent=2), encoding="utf-8")
    logger.info(f"Saved {len(strategies)} synthesized strategies to {strategies_out}")


if __name__ == "__main__":
    compile_catalogs()
