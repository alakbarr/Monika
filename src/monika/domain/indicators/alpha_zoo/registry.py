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

from monika.domain.indicators.alpha_zoo.meta import AlphaCategory, AlphaDirection, AlphaMeta


class RegistryError(Exception):
    """Raised when factor registration, compilation, or execution violates invariants."""

    pass


FactorCallable = Callable[..., Union[pd.Series, pd.DataFrame]]


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
                        if not isinstance(raw_dict, dict):
                            raise ValueError("__alpha_meta__ is not a dict")
                        factor_id = raw_dict.get("name") or raw_dict.get("id") or path.stem
                        cat = raw_dict.get("category")
                        if not cat and raw_dict.get("theme"):
                            themes = raw_dict["theme"]
                            cat = themes[0] if isinstance(themes, list) and themes else str(themes)
                        cat = cat or "momentum"
                        if cat == "reversal":
                            cat = "mean_reversion"
                        valid_cats: dict[str, AlphaCategory] = {
                            "momentum": "momentum",
                            "mean_reversion": "mean_reversion",
                            "volatility": "volatility",
                            "volume": "volume",
                            "liquidity": "liquidity",
                            "trend": "trend",
                            "structural": "structural",
                            "fundamental": "fundamental",
                            "risk_premia": "risk_premia",
                            "microstructure": "microstructure",
                        }
                        validated_cat: AlphaCategory = valid_cats.get(cat, "momentum")
                        warmup = int(raw_dict.get("min_warmup_bars") or 5)
                        lookback = int(raw_dict.get("lookback") or warmup)
                        decay = int(raw_dict.get("decay_horizon") or 5)
                        dir_raw = str(raw_dict.get("direction") or "positive_bullish")
                        valid_dirs: dict[str, AlphaDirection] = {
                            "positive_bullish": "positive_bullish",
                            "positive_bearish": "positive_bearish",
                            "neutral_volatility": "neutral_volatility",
                        }
                        validated_dir: AlphaDirection = valid_dirs.get(dir_raw, "positive_bullish")

                        return AlphaMeta(
                            name=str(factor_id),
                            category=validated_cat,
                            lookback=lookback,
                            columns_required=raw_dict.get("columns_required", ["close"]),
                            min_warmup_bars=warmup,
                            decay_horizon=decay,
                            direction=validated_dir,
                            formula_latex=str(raw_dict.get("formula_latex", "")),
                            description=str(raw_dict.get("description") or raw_dict.get("nickname", "")),
                        )
                    except Exception as err:
                        raise RegistryError(f"Failed to parse __alpha_meta__ in {path}: {err}") from err

    raise RegistryError(f"No valid __alpha_meta__ found in {path}")


class FactorRegistry:
    """
    Central registry and execution engine for quantitative alpha factors.
    """

    _FACTORS: Dict[str, Tuple[FactorCallable, AlphaMeta]] = {}
    _LAZY_MANIFEST: Dict[str, Tuple[Path, AlphaMeta]] = {}
    _MANIFEST_LOADED: bool = False
    _ZOO_LOADED: bool = False

    @classmethod
    def ensure_zoo_loaded(cls) -> None:
        """Lazily load quantitative alpha factor manifest from the catalog."""
        if not cls._MANIFEST_LOADED:
            cls.load_manifest()
            cls._MANIFEST_LOADED = True

    @classmethod
    def load_manifest(cls, catalog_path: Optional[Path | str] = None) -> int:
        """Loads the quantitative alpha factor catalog manifest in milliseconds without importing modules."""
        if catalog_path is None:
            catalog_file = Path(__file__).resolve().parent / "catalog" / "factors.json"
        else:
            catalog_file = Path(catalog_path)

        if not catalog_file.exists():
            return cls.load_zoo_factors()

        import json
        import re

        try:
            with open(catalog_file, "r", encoding="utf-8") as f:
                catalog = json.load(f).get("factors", {})
        except Exception:
            return cls.load_zoo_factors()

        factors_dir = Path(__file__).resolve().parent / "factors"
        valid_cats = {
            "momentum",
            "mean_reversion",
            "volatility",
            "volume",
            "liquidity",
            "trend",
            "structural",
            "fundamental",
            "risk_premia",
            "microstructure",
        }

        for factor_key, f_data in catalog.items():
            factor_id = f_data.get("id", factor_key)
            cat = f_data.get("category") or (
                f_data.get("theme", ["momentum"])[0] if f_data.get("theme") else "momentum"
            )
            if cat == "reversal":
                cat = "mean_reversion"
            elif cat not in valid_cats:
                cat = "momentum"

            lookback = int(f_data.get("min_warmup_bars", 5) or 5)
            meta = AlphaMeta(
                name=factor_id,
                category=cat,
                lookback=lookback,
                columns_required=f_data.get("columns_required", ["close"]),
                min_warmup_bars=int(f_data.get("min_warmup_bars", 5) or 5),
                decay_horizon=int(f_data.get("decay_horizon", 5) or 5),
                direction=f_data.get("direction", "positive_bullish"),
                formula_latex=str(f_data.get("formula_latex", "")),
                description=str(
                    f_data.get("description") or f_data.get("notes") or f"{factor_id} quantitative alpha factor"
                ),
            )
            py_path = factors_dir / f_data["family"] / f_data["file_name"]
            stem = Path(f_data["file_name"]).stem
            parent_pkg = f_data["family"]

            cls._LAZY_MANIFEST[meta.name] = (py_path, meta)
            if stem != meta.name:
                cls._LAZY_MANIFEST[stem] = (py_path, meta)
            if parent_pkg == "microsoft_qlib_158":
                cls._LAZY_MANIFEST[f"qlib_{stem}"] = (py_path, meta)
                if factor_id.startswith("qlib158_"):
                    short_id = factor_id.replace("qlib158_", "")
                    cls._LAZY_MANIFEST[f"qlib_{short_id}"] = (py_path, meta)
                    m = re.match(r"(.*?_)?([a-zA-Z]+)(\d+)$", short_id)
                    if m:
                        cls._LAZY_MANIFEST[f"qlib_{m.group(2)}_{m.group(3)}"] = (py_path, meta)
            elif parent_pkg == "worldquant_101":
                if factor_id.startswith("alpha101_"):
                    num = factor_id.replace("alpha101_", "")
                    cls._LAZY_MANIFEST[f"wq_alpha_{num}"] = (py_path, meta)
                    cls._LAZY_MANIFEST[f"alpha_{num}"] = (py_path, meta)
            elif parent_pkg == "academic":
                cls._LAZY_MANIFEST[f"academic_{stem}"] = (py_path, meta)
            elif parent_pkg == "guotai_junan_191":
                cls._LAZY_MANIFEST[f"gtja_{factor_id}"] = (py_path, meta)
            elif parent_pkg == "fundamental":
                cls._LAZY_MANIFEST[f"fundamental_{stem}"] = (py_path, meta)

        cls._MANIFEST_LOADED = True
        return len(cls._LAZY_MANIFEST)

    @classmethod
    def _resolve_alias(cls, name: str) -> Optional[str]:
        if "_" in name:
            parts = name.split("_")
            if len(parts) == 3 and parts[2].isdigit():
                return f"{parts[0]}_{parts[1]}{parts[2]}"
        else:
            import re

            m = re.match(r"(qlib_\w+?)(\d+)$", name)
            if m:
                return f"{m.group(1)}_{m.group(2)}"
        return None

    @classmethod
    def register(cls, meta: AlphaMeta):
        """Decorator to register a factor calculation function with its AlphaMeta."""

        def decorator(fn: FactorCallable) -> FactorCallable:
            if meta.name in cls._FACTORS:
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
            cls.ensure_zoo_loaded()

        if name in cls._FACTORS:
            return cls._FACTORS[name]

        target_key = name
        if target_key not in cls._LAZY_MANIFEST:
            alt = cls._resolve_alias(target_key)
            if alt and alt in cls._LAZY_MANIFEST:
                target_key = alt

        if target_key in cls._LAZY_MANIFEST:
            py_path, meta = cls._LAZY_MANIFEST[target_key]
            import importlib.util

            spec = importlib.util.spec_from_file_location(f"alpha_zoo_{meta.name}", py_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                fn = getattr(mod, "compute")
                cls._FACTORS[meta.name] = (fn, meta)
                cls._FACTORS[name] = (fn, meta)
                if target_key != name:
                    cls._FACTORS[target_key] = (fn, meta)
                return cls._FACTORS[name]

        alt_name = cls._resolve_alias(name)
        if alt_name and alt_name in cls._FACTORS:
            return cls._FACTORS[alt_name]

        raise KeyError(f"Factor '{name}' is not registered in FactorRegistry")

    @classmethod
    def list_factors(cls, category: Optional[str] = None) -> List[AlphaMeta]:
        cls.ensure_zoo_loaded()
        unique_metas: Dict[str, AlphaMeta] = {}
        for _, meta in cls._FACTORS.values():
            if meta.name not in unique_metas:
                unique_metas[meta.name] = meta
        for _, meta in cls._LAZY_MANIFEST.values():
            if meta.name not in unique_metas:
                unique_metas[meta.name] = meta
        factors = list(unique_metas.values())
        if category:
            factors = [m for m in factors if m.category == category]
        return sorted(factors, key=lambda m: m.name)

    @classmethod
    def clear(cls) -> None:
        """Clears the registry loaded factors cache."""
        cls._FACTORS.clear()
        cls._ZOO_LOADED = False

    @classmethod
    def compute(
        cls,
        name: str,
        df: pd.DataFrame,
        strict_masking: bool = True,
        precomputed_panel: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> pd.Series:
        """
        Executes a factor calculation with deterministic NaN dependency masking.

        Args:
            name: Factor identifier
            df: OHLCV DataFrame (must contain required columns)
            strict_masking: If True, any bar with NaN in required inputs becomes NaN in output.
            precomputed_panel: Optional precomputed 2D single-asset column dictionary to bypass re-allocation.

        Returns:
            Computed factor Series with strict NaN guarantees.
        """
        fn, meta = cls.get(name)

        # 1. Synthesize turnover/amount and vwap if standard OHLCV columns exist
        df_eval = df.copy(deep=False)
        if "amount" not in df_eval.columns and "close" in df_eval.columns and "volume" in df_eval.columns:
            df_eval["amount"] = df_eval["close"] * df_eval["volume"]
        if (
            "vwap" not in df_eval.columns
            and "high" in df_eval.columns
            and "low" in df_eval.columns
            and "close" in df_eval.columns
        ):
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
        panel_dict = (
            precomputed_panel
            if precomputed_panel is not None
            else {c: pd.DataFrame({"asset": df_eval[c]}) for c in df_eval.columns}
        )
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
        and joins them into a single wide DataFrame with zero redundant panel allocations.
        """
        results: Dict[str, pd.Series] = {}
        target_factors = cls.list_factors(category=category)

        # Synthesize required base columns and 2D panel view once for the entire batch
        df_eval = df.copy(deep=False)
        if "amount" not in df_eval.columns and "close" in df_eval.columns and "volume" in df_eval.columns:
            df_eval["amount"] = df_eval["close"] * df_eval["volume"]
        if (
            "vwap" not in df_eval.columns
            and "high" in df_eval.columns
            and "low" in df_eval.columns
            and "close" in df_eval.columns
        ):
            df_eval["vwap"] = (
                df_eval["high"] + df_eval["low"] + df_eval["close"] + df_eval.get("open", df_eval["close"])
            ) / 4.0

        base_panel = {c: pd.DataFrame({"asset": df_eval[c]}) for c in df_eval.columns}

        for meta in target_factors:
            try:
                results[meta.name] = cls.compute(
                    meta.name,
                    df_eval,
                    strict_masking=strict_masking,
                    precomputed_panel=base_panel,
                )
            except Exception:
                results[meta.name] = pd.Series(np.nan, index=df.index, name=meta.name)

        return pd.DataFrame(results, index=df.index)

    @classmethod
    def load_zoo_factors(cls, factors_dir: Optional[Path | str] = None) -> int:
        """
        Dynamically discovers and registers all quantitative alpha factor definitions.
        Uses ultra-fast ahead-of-time manifest indexing when default factors_dir is used.
        """
        if factors_dir is None:
            count = cls.load_manifest()
            cls._ZOO_LOADED = True
            return count
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
                        elif category not in (
                            "momentum",
                            "mean_reversion",
                            "volatility",
                            "volume",
                            "liquidity",
                            "trend",
                            "structural",
                            "fundamental",
                            "risk_premia",
                            "microstructure",
                        ):
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
                            if factor_id.startswith("qlib158_"):
                                short_id = factor_id.replace("qlib158_", "")
                                cls.register_manual(f"qlib_{short_id}", fn, meta)
                        elif parent_pkg == "worldquant_101":
                            if factor_id.startswith("alpha101_"):
                                num = factor_id.replace("alpha101_", "")
                                cls.register_manual(f"wq_alpha_{num}", fn, meta)
                                cls.register_manual(f"alpha_{num}", fn, meta)
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
