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

        # 1. Verify required columns
        for col in meta.columns_required:
            if col not in df.columns:
                raise RegistryError(
                    f"Factor '{name}' requires column '{col}', but input columns are: {list(df.columns)}"
                )

        # 2. Compute factor
        try:
            res = fn(df)
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


AlphaZooRegistry = FactorRegistry

