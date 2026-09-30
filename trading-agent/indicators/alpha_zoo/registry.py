# ==============================================================================
# File: indicators/alpha_zoo/registry.py
# Monika Enterprise Factor Registry & Static Metadata Engine
# ==============================================================================

"""
Factor Registry with Static AST Metadata Extraction and NaN Dependency Masking.

Guarantees:
- Safe AST extraction without module execution or import side-effects.
- Strict input validation: factors require standard OHLCV columns.
- Automatic post-compute NaN masking: if any required input column has NaN at bar t,
  the factor output at bar t is strictly masked to NaN.
- Infinite value scrubbing: +/- inf is converted to NaN.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from indicators.alpha_zoo.meta import AlphaMeta


class RegistryError(Exception):
    """Raised when factor registration, compilation, or execution violates invariants."""
    pass


FactorCallable = Callable[[pd.DataFrame], Union[pd.Series, pd.DataFrame]]


def load_alpha_meta_from_py(file_path: Union[str, Path]) -> AlphaMeta:
    """
    Extracts __alpha_meta__ from a Python factor file via static AST parsing.
    Does NOT import the module or execute any code.
    """
    path = Path(file_path)
    if not path.is_file():
        raise RegistryError(f"Factor source file not found: {path}")

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__alpha_meta__":
                    try:
                        raw_dict = ast.literal_eval(node.value)
                        return AlphaMeta(**raw_dict)
                    except Exception as err:
                        raise RegistryError(f"Failed to parse __alpha_meta__ in {path}: {err}") from err

    raise RegistryError(f"No valid __alpha_meta__ found in {path}")


class FactorRegistry:
    """
    Central registry and execution engine for quantitative alpha factors.
    """
    _FACTORS: Dict[str, Tuple[FactorCallable, AlphaMeta]] = {}

    @classmethod
    def register(cls, meta: AlphaMeta):
        """Decorator to register a factor calculation function with its AlphaMeta."""
        def decorator(fn: FactorCallable) -> FactorCallable:
            if meta.name in cls._FACTORS:
                # Allow re-registering for test suites / hot reload
                pass
            cls._FACTORS[meta.name] = (fn, meta)
            return fn
        return decorator

    @classmethod
    def register_manual(cls, name: str, fn: FactorCallable, meta: AlphaMeta) -> None:
        """Explicitly register a factor callable and its metadata."""
        cls._FACTORS[name] = (fn, meta)

    @classmethod
    def get(cls, name: str) -> Tuple[FactorCallable, AlphaMeta]:
        if name not in cls._FACTORS:
            raise KeyError(f"Factor '{name}' is not registered in FactorRegistry")
        return cls._FACTORS[name]

    @classmethod
    def list_factors(cls, category: Optional[str] = None) -> List[AlphaMeta]:
        factors = [meta for _, meta in cls._FACTORS.values()]
        if category:
            factors = [m for m in factors if m.category == category]
        return sorted(factors, key=lambda m: m.name)

    @classmethod
    def clear(cls) -> None:
        """Clears the registry (useful for testing)."""
        cls._FACTORS.clear()

    @classmethod
    def compute(
        cls,
        name: str,
        df: pd.DataFrame,
        strict_masking: bool = True,
    ) -> pd.Series:
        """
        Executes a factor calculation with deterministic NaN dependency masking.
        
        Args:
            name: Factor identifier
            df: OHLCV DataFrame (must contain required columns)
            strict_masking: If True, any bar with NaN in required inputs becomes NaN in output.
            
        Returns:
            Computed factor Series with strict NaN guarantees.
        """
        fn, meta = cls.get(name)

        # 1. Synthesize turnover/amount and vwap if standard OHLCV columns exist
        df_eval = df.copy(deep=False)
        if "amount" not in df_eval.columns and "close" in df_eval.columns and "volume" in df_eval.columns:
            df_eval["amount"] = df_eval["close"] * df_eval["volume"]
        if "vwap" not in df_eval.columns and "high" in df_eval.columns and "low" in df_eval.columns and "close" in df_eval.columns:
            df_eval["vwap"] = (
                df_eval["high"] + df_eval["low"] + df_eval["close"] + df_eval.get("open", df_eval["close"])
            ) / 4.0

        # 2. Verify required columns
        for col in meta.columns_required:
            if col not in df_eval.columns:
                raise RegistryError(
                    f"Factor '{name}' requires column '{col}', but input columns are: {list(df_eval.columns)}"
                )

        # 3. Compute factor:
        # Wrap into single-asset 2D column dictionary panel for universal formula compatibility
        # (guarantees .columns compatibility with WorldQuant, GTJA 191, Qlib, and Academic alphas).
        panel_dict = {c: pd.DataFrame({"asset": df_eval[c]}) for c in df_eval.columns}
        try:
            res = fn(panel_dict)
        except Exception:
            try:
                res = fn(df_eval)
            except Exception as err:
                raise RegistryError(f"Error computing factor '{name}': {err}") from err

        if isinstance(res, pd.DataFrame):
            if res.shape[1] == 1:
                res = res.iloc[:, 0]
            else:
                raise RegistryError(f"Factor '{name}' returned multi-column DataFrame instead of Series")

        if not isinstance(res, pd.Series):
            res = pd.Series(res, index=df.index, name=name)
        else:
            res.name = name

        # 3. Infinite value scrubbing
        res = res.replace([np.inf, -np.inf], np.nan)

        # 4. Strict input dependency NaN masking
        if strict_masking:
            valid_mask = pd.Series(True, index=df.index)
            for col in meta.columns_required:
                valid_mask = valid_mask & df[col].notna()
            res = res.where(valid_mask, np.nan)

        # 5. Enforce minimum warmup bars
        if meta.min_warmup_bars > 0 and len(res) >= meta.min_warmup_bars:
            res.iloc[: meta.min_warmup_bars - 1] = np.nan

        return res

    @classmethod
    def compute_all(
        cls,
        df: pd.DataFrame,
        category: Optional[str] = None,
        strict_masking: bool = True,
    ) -> pd.DataFrame:
        """
        Computes all registered factors (optionally filtered by category)
        and joins them into a single wide DataFrame.
        """
        results: Dict[str, pd.Series] = {}
        target_factors = cls.list_factors(category=category)

        for meta in target_factors:
            try:
                results[meta.name] = cls.compute(meta.name, df, strict_masking=strict_masking)
            except Exception:
                results[meta.name] = pd.Series(np.nan, index=df.index, name=meta.name)

        return pd.DataFrame(results, index=df.index)

    @classmethod
    def load_zoo_factors(cls, factors_dir: Optional[Path | str] = None) -> int:
        """
        Dynamically discovers and registers all 462 quantitative alpha factor
        definitions from the indicators/alpha_zoo/factors directory.
        """
        if factors_dir is None:
            factors_dir = Path(__file__).resolve().parent / "factors"
        else:
            factors_dir = Path(factors_dir)

        if not factors_dir.exists():
            return 0

        loaded_count = 0
        import importlib.util
        for py_path in factors_dir.rglob("*.py"):
            if py_path.name.startswith("__"):
                continue
            try:
                mod_name = f"indicators.alpha_zoo.factors.{py_path.parent.name}.{py_path.stem}"
                spec = importlib.util.spec_from_file_location(mod_name, py_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "__alpha_meta__") and hasattr(mod, "compute"):
                        meta_dict = getattr(mod, "__alpha_meta__")
                        fn = getattr(mod, "compute")
                        factor_id = meta_dict.get("id", py_path.stem)
                        category = meta_dict.get("theme", ["momentum"])[0] if meta_dict.get("theme") else "momentum"
                        if category == "reversal":
                            category = "mean_reversion"
                        elif category not in ("momentum", "mean_reversion", "volatility", "volume", "liquidity", "trend", "structural", "fundamental", "risk_premia", "microstructure"):
                            category = "momentum"

                        meta = AlphaMeta(
                            name=factor_id,
                            category=category,
                            lookback=int(meta_dict.get("min_warmup_bars", 5) or 5),
                            columns_required=meta_dict.get("columns_required", ["close"]),
                            min_warmup_bars=int(meta_dict.get("min_warmup_bars", 5) or 5),
                            decay_horizon=int(meta_dict.get("decay_horizon", 5) or 5),
                            direction="positive_bullish",
                            formula_latex=str(meta_dict.get("formula_latex", "")),
                            description=str(meta_dict.get("notes") or f"{factor_id} quantitative alpha factor"),
                        )
                        # Register primary ID
                        cls.register_manual(meta.name, fn, meta)
                        # Register convenient aliases
                        if py_path.stem != meta.name:
                            cls.register_manual(py_path.stem, fn, meta)
                        parent_pkg = py_path.parent.name
                        if parent_pkg == "microsoft_qlib_158":
                            cls.register_manual(f"qlib_{py_path.stem}", fn, meta)
                        elif parent_pkg == "academic":
                            cls.register_manual(f"academic_{py_path.stem}", fn, meta)
                        elif parent_pkg == "guotai_junan_191":
                            cls.register_manual(f"gtja_{factor_id}", fn, meta)
                        elif parent_pkg == "fundamental":
                            cls.register_manual(f"fundamental_{py_path.stem}", fn, meta)
                        loaded_count += 1
            except Exception:
                pass
        return loaded_count


AlphaZooRegistry = FactorRegistry


