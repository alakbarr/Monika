# ==============================================================================
# File: core/native/rust_bridge.py
# Description: High-performance C-ABI bridge to compiled Rust kernels (monika_core_rs).
# ==============================================================================

from __future__ import annotations

import ctypes
import hashlib
import logging
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("TradingAgent.RustBridge")

_LIB_INSTANCE: Optional[ctypes.CDLL] = None
_LIB_INITIALIZED: bool = False


def _get_shared_lib_path() -> Optional[Path]:
    """Locate the platform-specific compiled monika_core_rs shared library, building offline if needed."""
    crate_dir = Path(__file__).resolve().parent / "monika_core_rs"
    base_dir = crate_dir / "target" / "release"
    if sys.platform.startswith("win"):
        candidates = [base_dir / "monika_core_rs.dll"]
    elif sys.platform.startswith("darwin"):
        candidates = [base_dir / "libmonika_core_rs.dylib"]
    else:
        candidates = [base_dir / "libmonika_core_rs.so"]

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    # On-demand offline build if cargo is installed and binary is not yet compiled
    if (
        (crate_dir / "Cargo.toml").is_file()
        and os.environ.get("MONIKA_DISABLE_RUST_BUILD", "").strip().lower() not in ("1", "true", "yes")
        and shutil.which("cargo") is not None
    ):
        try:
            import subprocess

            subprocess.run(
                ["cargo", "build", "--release", "--offline"],
                cwd=str(crate_dir),
                timeout=30,
                capture_output=True,
                check=False,
            )
            for candidate in candidates:
                if candidate.is_file():
                    return candidate
        except Exception as build_err:
            logger.debug(f"[RustBridge] On-demand cargo build skipped: {build_err}")

    return None


def _load_library() -> Optional[ctypes.CDLL]:
    """
    Load the native library with shadow copying on Windows to prevent file-locking.
    Returns ctypes.CDLL handle or None if unavailable or disabled.
    """
    global _LIB_INSTANCE, _LIB_INITIALIZED
    if _LIB_INITIALIZED:
        return _LIB_INSTANCE

    _LIB_INITIALIZED = True

    if os.environ.get("MONIKA_DISABLE_RUST_ACCEL", "").strip().lower() in ("1", "true", "yes"):
        logger.debug("[RustBridge] Native Rust accelerator explicitly disabled via MONIKA_DISABLE_RUST_ACCEL.")
        return None

    lib_path = _get_shared_lib_path()
    if lib_path is None:
        logger.debug("[RustBridge] Native Rust shared library not found in target/release.")
        return None

    try:
        load_path = lib_path
        if sys.platform.startswith("win"):
            # Compute SHA-256 digest of original binary to create an immutable shadow copy
            data = lib_path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()[:12]
            shadow_path = Path(tempfile.gettempdir()) / f"monika_core_rs_{digest}.dll"
            if not shadow_path.is_file() or shadow_path.stat().st_size != len(data):
                shutil.copy2(lib_path, shadow_path)
            load_path = shadow_path

        lib = ctypes.CDLL(str(load_path))

        # Setup ctypes function signatures
        f64_p = ctypes.POINTER(ctypes.c_double)
        u8_p = ctypes.POINTER(ctypes.c_uint8)
        usize_p = ctypes.POINTER(ctypes.c_size_t)

        # 1. monika_vpin_fractional_f64
        lib.monika_vpin_fractional_f64.argtypes = [
            f64_p,
            f64_p,
            ctypes.c_size_t,
            ctypes.c_double,
            ctypes.c_size_t,
        ]
        lib.monika_vpin_fractional_f64.restype = ctypes.c_double

        # 2. monika_kyle_lambda_ols_f64
        lib.monika_kyle_lambda_ols_f64.argtypes = [
            f64_p,
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_kyle_lambda_ols_f64.restype = ctypes.c_int32

        # 3. monika_tick_rule_cvd_f64
        lib.monika_tick_rule_cvd_f64.argtypes = [
            f64_p,
            f64_p,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_tick_rule_cvd_f64.restype = ctypes.c_int32

        # 4. monika_find_swings_f64
        lib.monika_find_swings_f64.argtypes = [
            f64_p,
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            u8_p,
            u8_p,
        ]
        lib.monika_find_swings_f64.restype = ctypes.c_int32

        # 5. monika_find_swing_pivots_f64
        lib.monika_find_swing_pivots_f64.argtypes = [
            f64_p,
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            usize_p,
            u8_p,
            f64_p,
        ]
        lib.monika_find_swing_pivots_f64.restype = ctypes.c_ssize_t

        # 6. monika_eval_equity_paths_f64
        lib.monika_eval_equity_paths_f64.argtypes = [
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_double,
            ctypes.c_double,
            f64_p,
            f64_p,
            usize_p,
        ]
        lib.monika_eval_equity_paths_f64.restype = ctypes.c_int32

        # 7. monika_monte_carlo_simulate_f64
        lib.monika_monte_carlo_simulate_f64.argtypes = [
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_uint32,
            ctypes.c_size_t,
            ctypes.c_uint64,
            f64_p,
            f64_p,
            usize_p,
        ]
        lib.monika_monte_carlo_simulate_f64.restype = ctypes.c_int32

        # 8. monika_cscv_pbo_from_chunks_f64
        lib.monika_cscv_pbo_from_chunks_f64.argtypes = [
            f64_p,
            f64_p,
            usize_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            usize_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_cscv_pbo_from_chunks_f64.restype = ctypes.c_ssize_t

        # 9. monika_ts_rank_f64
        lib.monika_ts_rank_f64.argtypes = [
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_ts_rank_f64.restype = ctypes.c_int32

        # 10. monika_decay_linear_f64
        lib.monika_decay_linear_f64.argtypes = [
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_decay_linear_f64.restype = ctypes.c_int32

        # 11. monika_rolling_corr_f64
        lib.monika_rolling_corr_f64.argtypes = [
            f64_p,
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_rolling_corr_f64.restype = ctypes.c_int32

        # 12. monika_sma_f64
        lib.monika_sma_f64.argtypes = [
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_sma_f64.restype = ctypes.c_int32

        # 13. monika_ema_f64
        lib.monika_ema_f64.argtypes = [
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_ema_f64.restype = ctypes.c_int32

        # 14. monika_rsi_f64
        lib.monika_rsi_f64.argtypes = [
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_rsi_f64.restype = ctypes.c_int32

        # 15. monika_atr_f64
        lib.monika_atr_f64.argtypes = [
            f64_p,
            f64_p,
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            f64_p,
        ]
        lib.monika_atr_f64.restype = ctypes.c_int32

        # 16. monika_bollinger_bands_f64
        lib.monika_bollinger_bands_f64.argtypes = [
            f64_p,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_double,
            f64_p,
            f64_p,
            f64_p,
        ]
        lib.monika_bollinger_bands_f64.restype = ctypes.c_int32

        # 17. monika_find_fvg_f64
        lib.monika_find_fvg_f64.argtypes = [
            f64_p,
            f64_p,
            f64_p,
            ctypes.c_size_t,
            ctypes.c_double,
            usize_p,
            u8_p,
            f64_p,
            f64_p,
            ctypes.POINTER(ctypes.c_ssize_t),
        ]
        lib.monika_find_fvg_f64.restype = ctypes.c_ssize_t

        _LIB_INSTANCE = lib
        logger.info(f"[RustBridge] Successfully loaded native Rust accelerator from {load_path}")
        return _LIB_INSTANCE
    except Exception as e:
        logger.warning(f"[RustBridge] Failed to load native Rust accelerator: {e}. Falling back to NumPy.")
        _LIB_INSTANCE = None
        return None


def is_rust_accelerator_available() -> bool:
    """Check if the native Rust accelerator is compiled, loadable, and enabled."""
    if os.environ.get("MONIKA_DISABLE_RUST_ACCEL", "").strip().lower() in ("1", "true", "yes"):
        return False
    return _load_library() is not None


def vpin_fractional_f64(
    prices: np.ndarray,
    volumes: np.ndarray,
    bucket_volume: float,
    n_buckets: int,
) -> Optional[float]:
    """Compute VPIN using Rust fractional volume bucket slicing kernel."""
    lib = _load_library()
    if lib is None:
        return None
    if len(prices) < 2 or len(volumes) < 2 or len(prices) != len(volumes):
        return None
    if bucket_volume <= 0.0 or not math.isfinite(bucket_volume) or n_buckets <= 0:
        return None

    p_arr = np.ascontiguousarray(prices, dtype=np.float64)
    v_arr = np.ascontiguousarray(volumes, dtype=np.float64)
    if not np.all(np.isfinite(p_arr)) or not np.all(np.isfinite(v_arr)):
        return None

    res = lib.monika_vpin_fractional_f64(
        p_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        v_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(len(p_arr)),
        ctypes.c_double(bucket_volume),
        ctypes.c_size_t(n_buckets),
    )
    if math.isnan(res):
        return None
    return float(res)


def kyle_lambda_ols_f64(
    y_vals: np.ndarray,
    x_vals: np.ndarray,
    window: int,
) -> Optional[np.ndarray]:
    """Compute rolling Kyle's Lambda OLS slope using Rust kernel."""
    lib = _load_library()
    if lib is None:
        return None
    n = len(y_vals)
    if n < window or window < 3 or n != len(x_vals):
        return None

    y_arr = np.ascontiguousarray(y_vals, dtype=np.float64)
    x_arr = np.ascontiguousarray(x_vals, dtype=np.float64)
    if not np.all(np.isfinite(y_arr)) or not np.all(np.isfinite(x_arr)):
        return None

    out_arr = np.zeros(n, dtype=np.float64)
    code = lib.monika_kyle_lambda_ols_f64(
        y_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        x_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(n),
        ctypes.c_size_t(window),
        out_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return out_arr


def tick_rule_cvd_f64(
    prices: np.ndarray,
    volumes: np.ndarray,
) -> Optional[np.ndarray]:
    """Compute Tick Rule Cumulative Volume Delta (CVD) series using Rust kernel."""
    lib = _load_library()
    if lib is None:
        return None
    n = len(prices)
    if n == 0 or n != len(volumes):
        return None

    p_arr = np.ascontiguousarray(prices, dtype=np.float64)
    v_arr = np.ascontiguousarray(volumes, dtype=np.float64)
    if not np.all(np.isfinite(p_arr)) or not np.all(np.isfinite(v_arr)):
        return None

    out_arr = np.zeros(n, dtype=np.float64)
    code = lib.monika_tick_rule_cvd_f64(
        p_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        v_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(n),
        out_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return out_arr


def find_swings_f64(
    highs: np.ndarray,
    lows: np.ndarray,
    window: int,
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """
    Detect fractal swing highs and swing lows using Rust kernel.
    Returns (swing_high_indices, swing_low_indices) as 1D uint64 arrays.
    """
    lib = _load_library()
    if lib is None:
        return None
    n = len(highs)
    w = max(1, window)
    if n < 2 * w + 1 or n != len(lows):
        return None

    h_arr = np.ascontiguousarray(highs, dtype=np.float64)
    l_arr = np.ascontiguousarray(lows, dtype=np.float64)
    if not np.all(np.isfinite(h_arr)) or not np.all(np.isfinite(l_arr)):
        return None

    h_mask = np.zeros(n, dtype=np.uint8)
    l_mask = np.zeros(n, dtype=np.uint8)

    code = lib.monika_find_swings_f64(
        h_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        l_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(n),
        ctypes.c_size_t(w),
        h_mask.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        l_mask.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
    )
    if code != 0:
        return None

    sh_idx = np.flatnonzero(h_mask)
    sl_idx = np.flatnonzero(l_mask)
    return sh_idx, sl_idx


def find_swing_pivots_f64(
    highs: np.ndarray,
    lows: np.ndarray,
    order: int,
) -> Optional[list[dict[str, Any]]]:
    """Detect alternating swing pivots using Rust kernel."""
    lib = _load_library()
    if lib is None:
        return None
    n = len(highs)
    ord_val = max(1, order)
    if n <= 2 * ord_val or n != len(lows):
        return None

    h_arr = np.ascontiguousarray(highs, dtype=np.float64)
    l_arr = np.ascontiguousarray(lows, dtype=np.float64)
    if not np.all(np.isfinite(h_arr)) or not np.all(np.isfinite(l_arr)):
        return None

    out_indices = np.zeros(n, dtype=np.uintp)
    out_types = np.zeros(n, dtype=np.uint8)
    out_prices = np.zeros(n, dtype=np.float64)

    count = lib.monika_find_swing_pivots_f64(
        h_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        l_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(n),
        ctypes.c_size_t(ord_val),
        out_indices.ctypes.data_as(ctypes.POINTER(ctypes.c_size_t)),
        out_types.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        out_prices.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if count < 0:
        return None

    result: list[dict[str, Any]] = []
    for k in range(int(count)):
        p_type = "high" if out_types[k] == 1 else "low"
        result.append(
            {
                "index": int(out_indices[k]),
                "type": p_type,
                "price": float(out_prices[k]),
            }
        )
    return result


def eval_equity_paths_f64(
    sampled_matrix: np.ndarray,
    initial_equity: float,
    ruin_drawdown_pct: float,
) -> Optional[tuple[np.ndarray, np.ndarray, int]]:
    """
    Evaluate equity paths, max drawdowns, and ruin occurrences using Rust kernel.
    sampled_matrix shape: (num_simulations, n_trades).
    Returns (max_drawdowns_pct, final_equities, ruin_count).
    """
    lib = _load_library()
    if lib is None:
        return None
    if sampled_matrix.ndim != 2:
        return None
    num_simulations, n_trades = sampled_matrix.shape
    if num_simulations == 0 or n_trades == 0:
        return None
    if initial_equity <= 0.0 or not math.isfinite(initial_equity):
        return None

    mat_arr = np.ascontiguousarray(sampled_matrix, dtype=np.float64)
    if not np.all(np.isfinite(mat_arr)):
        return None

    out_max_dds = np.zeros(num_simulations, dtype=np.float64)
    out_final_eqs = np.zeros(num_simulations, dtype=np.float64)
    out_ruin_count = ctypes.c_size_t(0)

    code = lib.monika_eval_equity_paths_f64(
        mat_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(num_simulations),
        ctypes.c_size_t(n_trades),
        ctypes.c_double(initial_equity),
        ctypes.c_double(ruin_drawdown_pct),
        out_max_dds.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        out_final_eqs.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(out_ruin_count),
    )
    if code != 0:
        return None

    return out_max_dds, out_final_eqs, int(out_ruin_count.value)


def cscv_pbo_from_chunks_f64(
    chunk_sums: np.ndarray,
    chunk_sq_sums: np.ndarray,
    chunk_counts: np.ndarray,
    selected_combos: np.ndarray,
) -> Optional[tuple[int, np.ndarray]]:
    """
    Compute CSCV Combinatorial Purged Cross-Validation PBO using Rust kernel.
    Returns (underperforming_count, oos_ranks_array).
    """
    lib = _load_library()
    if lib is None:
        return None
    if chunk_sums.ndim != 2 or chunk_sq_sums.ndim != 2 or selected_combos.ndim != 2:
        return None

    n_partitions, n_strats = chunk_sums.shape
    n_combos, half_s = selected_combos.shape
    if n_partitions < 2 or n_strats == 0 or n_combos == 0:
        return None

    sums_arr = np.ascontiguousarray(chunk_sums, dtype=np.float64)
    sq_sums_arr = np.ascontiguousarray(chunk_sq_sums, dtype=np.float64)
    counts_arr = np.ascontiguousarray(chunk_counts, dtype=np.uintp)
    combos_arr = np.ascontiguousarray(selected_combos, dtype=np.uintp)

    if not np.all(np.isfinite(sums_arr)) or not np.all(np.isfinite(sq_sums_arr)):
        return None

    out_ranks = np.zeros(n_combos, dtype=np.float64)

    underperforming = lib.monika_cscv_pbo_from_chunks_f64(
        sums_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        sq_sums_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        counts_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_size_t)),
        ctypes.c_size_t(n_partitions),
        ctypes.c_size_t(n_strats),
        combos_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_size_t)),
        ctypes.c_size_t(n_combos),
        ctypes.c_size_t(half_s),
        out_ranks.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if underperforming < 0:
        return None

    return int(underperforming), out_ranks


def monte_carlo_simulate_f64(
    returns: np.ndarray,
    num_simulations: int,
    initial_equity: float,
    ruin_drawdown_pct: float,
    mode_code: int = 0,
    block_size: int = 5,
    seed: int = 42,
) -> Optional[tuple[np.ndarray, np.ndarray, int]]:
    """
    Run high-speed Monte Carlo simulations (IID bootstrap or stationary block bootstrap) in Rust.
    Returns (out_max_dds, out_final_eqs, ruin_count) or None if unavailable.
    """
    lib = _load_library()
    if lib is None:
        return None
    if returns.ndim != 1 or len(returns) == 0 or num_simulations == 0:
        return None
    if initial_equity <= 0.0 or not math.isfinite(initial_equity):
        return None

    ret_arr = np.ascontiguousarray(returns, dtype=np.float64)
    if not np.all(np.isfinite(ret_arr)):
        return None

    out_max_dds = np.zeros(num_simulations, dtype=np.float64)
    out_final_eqs = np.zeros(num_simulations, dtype=np.float64)
    out_ruin_count = ctypes.c_size_t(0)

    code = lib.monika_monte_carlo_simulate_f64(
        ret_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(len(ret_arr)),
        ctypes.c_size_t(num_simulations),
        ctypes.c_double(initial_equity),
        ctypes.c_double(ruin_drawdown_pct),
        ctypes.c_uint32(mode_code),
        ctypes.c_size_t(block_size),
        ctypes.c_uint64(seed),
        out_max_dds.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        out_final_eqs.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(out_ruin_count),
    )
    if code != 0:
        return None

    return out_max_dds, out_final_eqs, int(out_ruin_count.value)


def ts_rank_f64(arr: np.ndarray, window: int) -> Optional[np.ndarray]:
    """
    Rolling time-series rank percentile in [0, 1] within a window.
    Returns 1D np.ndarray or None if Rust accelerator unavailable.
    """
    lib = _load_library()
    if lib is None:
        return None
    if arr.ndim != 1 or window < 1 or len(arr) < window:
        return None

    inp_arr = np.ascontiguousarray(arr, dtype=np.float64)
    out_arr = np.empty_like(inp_arr)

    code = lib.monika_ts_rank_f64(
        inp_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(len(inp_arr)),
        ctypes.c_size_t(window),
        out_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return out_arr


def decay_linear_f64(arr: np.ndarray, window: int) -> Optional[np.ndarray]:
    """
    Linear decay-weighted moving average with weights 1..window normalized.
    Returns 1D np.ndarray or None if Rust accelerator unavailable.
    """
    lib = _load_library()
    if lib is None:
        return None
    if arr.ndim != 1 or window < 1 or len(arr) < window:
        return None

    inp_arr = np.ascontiguousarray(arr, dtype=np.float64)
    out_arr = np.empty_like(inp_arr)

    code = lib.monika_decay_linear_f64(
        inp_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(len(inp_arr)),
        ctypes.c_size_t(window),
        out_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return out_arr


def rolling_corr_f64(x: np.ndarray, y: np.ndarray, window: int) -> Optional[np.ndarray]:
    """
    Rolling Pearson correlation between two 1D series with min_periods=window.
    Returns 1D np.ndarray or None if Rust accelerator unavailable.
    """
    lib = _load_library()
    if lib is None:
        return None
    if x.ndim != 1 or y.ndim != 1 or len(x) != len(y) or window < 2 or len(x) < window:
        return None

    x_arr = np.ascontiguousarray(x, dtype=np.float64)
    y_arr = np.ascontiguousarray(y, dtype=np.float64)
    out_arr = np.empty_like(x_arr)

    code = lib.monika_rolling_corr_f64(
        x_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        y_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(len(x_arr)),
        ctypes.c_size_t(window),
        out_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return out_arr


def sma_f64(arr: np.ndarray, period: int) -> Optional[np.ndarray]:
    """
    Simple Moving Average (SMA) using compiled Rust kernel.
    Returns 1D np.ndarray with leading NaNs, or None if unavailable.
    """
    lib = _load_library()
    if lib is None:
        return None
    if arr.ndim != 1 or period < 1 or len(arr) < period:
        return None

    inp_arr = np.ascontiguousarray(arr, dtype=np.float64)
    out_arr = np.empty_like(inp_arr)

    code = lib.monika_sma_f64(
        inp_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(len(inp_arr)),
        ctypes.c_size_t(period),
        out_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return out_arr


def ema_f64(arr: np.ndarray, period: int) -> Optional[np.ndarray]:
    """
    Exponential Moving Average (EMA) using compiled Rust kernel.
    Returns 1D np.ndarray with leading NaNs, or None if unavailable.
    """
    lib = _load_library()
    if lib is None:
        return None
    if arr.ndim != 1 or period < 1 or len(arr) < period:
        return None

    inp_arr = np.ascontiguousarray(arr, dtype=np.float64)
    out_arr = np.empty_like(inp_arr)

    code = lib.monika_ema_f64(
        inp_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(len(inp_arr)),
        ctypes.c_size_t(period),
        out_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return out_arr


def rsi_f64(arr: np.ndarray, period: int) -> Optional[np.ndarray]:
    """
    Relative Strength Index (RSI) using compiled Rust kernel.
    Returns 1D np.ndarray in [0, 100] with leading NaNs, or None if unavailable.
    """
    lib = _load_library()
    if lib is None:
        return None
    if arr.ndim != 1 or period < 1 or len(arr) < period:
        return None

    inp_arr = np.ascontiguousarray(arr, dtype=np.float64)
    out_arr = np.empty_like(inp_arr)

    code = lib.monika_rsi_f64(
        inp_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(len(inp_arr)),
        ctypes.c_size_t(period),
        out_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return out_arr


def atr_f64(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int) -> Optional[np.ndarray]:
    """
    Average True Range (ATR) using compiled Rust kernel.
    Returns 1D np.ndarray with leading 0.0s, or None if unavailable.
    """
    lib = _load_library()
    if lib is None:
        return None
    n = len(highs)
    if n < period or period < 1 or len(lows) != n or len(closes) != n:
        return None

    h_arr = np.ascontiguousarray(highs, dtype=np.float64)
    l_arr = np.ascontiguousarray(lows, dtype=np.float64)
    c_arr = np.ascontiguousarray(closes, dtype=np.float64)
    out_arr = np.empty_like(h_arr)

    code = lib.monika_atr_f64(
        h_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        l_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        c_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(n),
        ctypes.c_size_t(period),
        out_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return out_arr


def bollinger_bands_f64(
    arr: np.ndarray,
    period: int,
    num_std: float = 2.0,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """
    Bollinger Bands (middle, upper, lower) using compiled Rust kernel.
    Returns tuple of 3 1D np.ndarrays with leading NaNs, or None if unavailable.
    """
    lib = _load_library()
    if lib is None:
        return None
    if arr.ndim != 1 or period < 1 or len(arr) < period:
        return None

    inp_arr = np.ascontiguousarray(arr, dtype=np.float64)
    mid_arr = np.empty_like(inp_arr)
    upper_arr = np.empty_like(inp_arr)
    lower_arr = np.empty_like(inp_arr)

    code = lib.monika_bollinger_bands_f64(
        inp_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(len(inp_arr)),
        ctypes.c_size_t(period),
        ctypes.c_double(num_std),
        mid_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        upper_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        lower_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
    )
    if code != 0:
        return None
    return mid_arr, upper_arr, lower_arr


def find_fvg_f64(
    highs: np.ndarray,
    lows: np.ndarray,
    atr: np.ndarray,
    min_atr_factor: float = 0.3,
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """
    Fair Value Gap (FVG) detection using compiled Rust kernel.
    Returns (formed_indices, types, gap_highs, gap_lows, filled_indices) or None.
    types: 1=bullish, 2=bearish. filled_indices: index of fill candle or -1.
    """
    lib = _load_library()
    if lib is None:
        return None
    n = len(highs)
    if n < 3 or len(lows) != n or len(atr) != n:
        return None

    h_arr = np.ascontiguousarray(highs, dtype=np.float64)
    l_arr = np.ascontiguousarray(lows, dtype=np.float64)
    atr_arr = np.ascontiguousarray(atr, dtype=np.float64)

    out_indices = np.zeros(n, dtype=np.uint64)
    out_types = np.zeros(n, dtype=np.uint8)
    out_gap_high = np.zeros(n, dtype=np.float64)
    out_gap_low = np.zeros(n, dtype=np.float64)
    out_filled_idx = np.zeros(n, dtype=np.int64)

    count = lib.monika_find_fvg_f64(
        h_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        l_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        atr_arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_size_t(n),
        ctypes.c_double(min_atr_factor),
        out_indices.ctypes.data_as(ctypes.POINTER(ctypes.c_size_t)),
        out_types.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        out_gap_high.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        out_gap_low.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        out_filled_idx.ctypes.data_as(ctypes.POINTER(ctypes.c_ssize_t)),
    )
    if count < 0:
        return None

    k = int(count)
    return (
        out_indices[:k],
        out_types[:k],
        out_gap_high[:k],
        out_gap_low[:k],
        out_filled_idx[:k],
    )
