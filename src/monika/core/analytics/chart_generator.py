# ==============================================================================
# File: utils/chart_generator.py
# ==============================================================================

"""
Generator Grafik Candlestick Headless (PNG) menggunakan mplfinance.

Mendukung ekspor langsung ke in-memory buffer (io.BytesIO) untuk dikirim
melalui Telegram Bot via send_photo() tanpa perlu I/O disk.
Gaya tampilan gelap (dark theme) yang selaras dengan terminal trading.
"""

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import matplotlib

matplotlib.use("Agg")  # Headless mode — wajib sebelum import mplfinance
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd
import ta.trend

from monika.domain.indicators.technical import (
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
    compute_cvd_series,
    compute_donchian_channels,
    compute_ichimoku_series,
    compute_keltner_channels,
    compute_lag1_autocorrelation,
    compute_macd,
    compute_pivot_points,
    compute_rsi,
    compute_stochastic,
    compute_supertrend,
    compute_vwap,
    compute_wma,
    compute_yang_zhang_volatility,
    normalize_chart_workspace_config,
)

logger = logging.getLogger("TradingAgent.ChartGenerator")

DARK_STYLE = mpf.make_mpf_style(
    base_mpf_style="nightclouds",
    rc={
        "font.size": 8,
        "axes.titlesize": 10,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "figure.facecolor": "#131722",
        "axes.facecolor": "#131722",
    },
)


def generate_candlestick_chart(
    ohlcv_rows: list[dict],
    symbol: str,
    timeframe: str = "H1",
    show_volume: bool = True,
    show_ma: tuple = (20, 50),
    indicators: dict | None = None,
) -> io.BytesIO:
    """
    Menghasilkan gambar PNG candlestick dari daftar baris data OHLCV.

    Args:
        ohlcv_rows: List of dict dengan keys: timestamp, open, high, low, close, volume/tick_volume
        symbol: Simbol instrumen (contoh: 'XAUUSD', 'EURUSD')
        timeframe: Label timeframe (contoh: 'H1', 'H4', 'D1')
        show_volume: Menampilkan bar volume di panel bawah
        show_ma: Tuple periode moving average (contoh: (20, 50))
        indicators: Dict opsional untuk overlay indikator tambahan

    Returns:
        io.BytesIO buffer yang berisi binary PNG image (~40 - 90 KB).
    """
    if not ohlcv_rows or len(ohlcv_rows) < 2:
        raise ValueError(f"Insufficient OHLCV data for {symbol} ({len(ohlcv_rows) if ohlcv_rows else 0} candles)")

    df = pd.DataFrame(ohlcv_rows)

    # Standardize column names
    col_map = {}
    for col in df.columns:
        c_low = str(col).lower()
        if c_low in ["timestamp", "time", "date"]:
            col_map[col] = "Date"
        elif c_low == "open":
            col_map[col] = "Open"
        elif c_low == "high":
            col_map[col] = "High"
        elif c_low == "low":
            col_map[col] = "Low"
        elif c_low == "close":
            col_map[col] = "Close"
        elif c_low in ["volume", "tick_volume", "vol"]:
            col_map[col] = "Volume"

    df.rename(columns=col_map, inplace=True)

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
    elif not isinstance(df.index, pd.DatetimeIndex):
        # Fallback synthetic datetime index if timestamps missing
        df.index = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=len(df), freq="h")

    # Convert numeric columns to float
    for req_col in ["Open", "High", "Low", "Close"]:
        if req_col not in df.columns:
            raise ValueError(f"Missing required OHLC column '{req_col}' in dataset")
        df[req_col] = pd.to_numeric(df[req_col], errors="coerce")

    if "Volume" not in df.columns or df["Volume"].dropna().empty or bool((df["Volume"] == 0).all()):
        df["Volume"] = 0
        has_volume = False
    else:
        vol_s = pd.Series(pd.to_numeric(df["Volume"], errors="coerce"), index=df.index).fillna(0)
        df["Volume"] = vol_s
        has_volume = show_volume

    add_plots = []
    if indicators:
        for name, values in indicators.items():
            if len(values) == len(df):
                try:
                    s = pd.Series(values, index=df.index)
                    panel = 0 if any(k in name.lower() for k in ["ma", "ema", "sma", "band"]) else 2
                    color = "yellow" if "rsi" in name.lower() else "cyan"
                    add_plots.append(mpf.make_addplot(s, panel=panel, color=color, width=0.8))
                except Exception as e:
                    logger.debug(f"Failed to add indicator plot for {name}: {e}")

    buf = io.BytesIO()
    kwargs: dict[str, Any] = {
        "type": "candle",
        "style": DARK_STYLE,
        "title": f"\n{symbol}  •  {timeframe}  ({len(df)} candles)",
        "volume": has_volume,
        "savefig": dict(fname=buf, dpi=100, bbox_inches="tight", format="png"),
        "figsize": (9, 5.5),
    }

    if show_ma and len(df) >= max(show_ma):
        kwargs["mav"] = show_ma
    if add_plots:
        kwargs["addplot"] = add_plots

    try:
        mpf.plot(df, **kwargs)
        buf.seek(0)
        logger.debug(f"Candlestick chart generated: {symbol} {timeframe}, size={buf.getbuffer().nbytes} bytes")
        return buf
    finally:
        plt.close("all")


async def generate_candlestick_chart_async(
    ohlcv_rows: list[dict],
    symbol: str,
    timeframe: str = "H1",
    show_volume: bool = True,
    show_ma: tuple = (20, 50),
    indicators: dict | None = None,
) -> io.BytesIO:
    """Async wrapper non-blocking untuk eksekusi render grafik di thread terpisah."""
    import asyncio

    return await asyncio.to_thread(
        generate_candlestick_chart,
        ohlcv_rows,
        symbol,
        timeframe=timeframe,
        show_volume=show_volume,
        show_ma=show_ma,
        indicators=indicators,
    )


def generate_smc_candlestick_chart(
    ohlcv_rows: list[dict],
    symbol: str,
    timeframe: str = "H1",
    fvg_list: list[dict] | None = None,
    swing_points: list[dict] | None = None,
    order_blocks: list[dict] | None = None,
    volume_profile: dict | None = None,
    save_to_disk: bool = True,
) -> tuple[io.BytesIO, str | None]:
    """
    Renders dark-theme candlestick chart with SMC overlays:
    - Transparent Green/Red rectangles for Bullish/Bearish Fair Value Gaps (FVG)
    - Transparent Order Block rectangles (Demand=Green, Supply=Red)
    - Horizontal Volume Profile lines (POC, VAH, VAL)
    - Triangle markers for Swing Highs (red) and Swing Lows (green)
    Returns: (BytesIO buffer, Optional filepath on disk)
    """
    import os
    from pathlib import Path

    import matplotlib.patches as patches

    if not ohlcv_rows or len(ohlcv_rows) < 2:
        raise ValueError(f"Insufficient OHLCV data for {symbol}")

    df = pd.DataFrame(ohlcv_rows)
    col_map = {}
    for col in df.columns:
        c_low = str(col).lower()
        if c_low in ["timestamp", "time", "date"]:
            col_map[col] = "Date"
        elif c_low == "open":
            col_map[col] = "Open"
        elif c_low == "high":
            col_map[col] = "High"
        elif c_low == "low":
            col_map[col] = "Low"
        elif c_low == "close":
            col_map[col] = "Close"
        elif c_low in ["volume", "tick_volume", "vol"]:
            col_map[col] = "Volume"

    df.rename(columns=col_map, inplace=True)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=len(df), freq="h")

    for req_col in ["Open", "High", "Low", "Close"]:
        if req_col in df.columns:
            df[req_col] = pd.to_numeric(df[req_col], errors="coerce")

    has_volume = False
    if "Volume" in df.columns:
        vol_s = pd.Series(pd.to_numeric(df["Volume"], errors="coerce"), index=df.index).fillna(0)
        df["Volume"] = vol_s
        has_volume = not bool((vol_s == 0).all())

    fig, axlist = mpf.plot(
        df,
        type="candle",
        style=DARK_STYLE,
        title=f"\n{symbol}  •  {timeframe}  (SMC Structure & Order Blocks)",
        volume=has_volume,
        figsize=(10, 6),
        returnfig=True,
    )
    main_ax = axlist[0]

    # Overlay FVGs
    if fvg_list:
        for fvg in fvg_list:
            top = float(fvg.get("top", fvg.get("high", 0)))
            bottom = float(fvg.get("bottom", fvg.get("low", 0)))
            fvg_type = str(fvg.get("type", "bullish")).lower()
            height = abs(top - bottom)
            y_min = min(top, bottom)
            is_bull = "bull" in fvg_type
            color = "#00e676" if is_bull else "#ff1744"
            alpha = 0.22

            rect = patches.Rectangle(
                (0, y_min), len(df), height, linewidth=1, edgecolor=color, facecolor=color, alpha=alpha, linestyle="--"
            )
            main_ax.add_patch(rect)

    # Overlay Order Blocks (Q040)
    if order_blocks:
        for ob in order_blocks:
            top = float(ob.get("high", ob.get("price_high", 0)))
            bottom = float(ob.get("low", ob.get("price_low", 0)))
            direction = str(ob.get("direction", "bullish")).lower()
            height = abs(top - bottom)
            y_min = min(top, bottom)
            is_bull = "bull" in direction or "demand" in direction
            color = "#00e676" if is_bull else "#ff1744"
            rect = patches.Rectangle(
                (0, y_min), len(df), height, linewidth=1.2, edgecolor=color, facecolor=color, alpha=0.25, linestyle="-"
            )
            main_ax.add_patch(rect)

    # Overlay Volume Profile levels (POC, VAH, VAL) (Q043)
    if volume_profile and isinstance(volume_profile, dict):
        poc = volume_profile.get("poc")
        vah = volume_profile.get("vah")
        val = volume_profile.get("val")
        if poc:
            main_ax.axhline(float(poc), color="#ffd700", linestyle="-", linewidth=1.5, alpha=0.85, label="POC")
        if vah:
            main_ax.axhline(float(vah), color="#42a5f5", linestyle=":", linewidth=1.2, alpha=0.75, label="VAH")
        if val:
            main_ax.axhline(float(val), color="#42a5f5", linestyle=":", linewidth=1.2, alpha=0.75, label="VAL")

    # Overlay Swing Points
    if swing_points:
        for sp in swing_points:
            p_type = str(sp.get("type", "")).lower()
            price = float(sp.get("price", 0))
            idx = sp.get("index", None)
            if idx is None and "time" in sp:
                try:
                    t_val = pd.to_datetime(sp["time"])
                    if t_val in df.index:
                        idx = df.index.get_loc(t_val)
                except Exception:
                    pass

            if idx is not None:
                int_idx = int(idx) if isinstance(idx, (int, float)) else (idx.start if isinstance(idx, slice) else None)
                if int_idx is not None and 0 <= int_idx < len(df):
                    if "high" in p_type or "top" in p_type or "peak" in p_type:
                        main_ax.scatter(int_idx, price, marker="v", color="#ff5252", s=70, zorder=6)
                    else:
                        main_ax.scatter(int_idx, price, marker="^", color="#69f0ae", s=70, zorder=6)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)

    saved_path = None
    if save_to_disk:
        out_dir = Path("results/charts")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = str(out_dir / f"{symbol}_{timeframe}_{ts_str}.png")
        with open(saved_path, "wb") as f:
            f.write(buf.getvalue())

    plt.close(fig)
    return buf, saved_path


def generate_equity_curve_chart(
    records: list[dict],
    title: str = "Monika Portfolio Equity Curve",
    save_to_disk: bool = True,
) -> tuple[io.BytesIO, str | None]:
    """
    Renders a dark-themed portfolio equity curve with drawdown fill band.
    """
    from pathlib import Path

    if not records:
        fig, ax = plt.subplots(figsize=(10, 5), facecolor="#131722")
        ax.set_facecolor("#131722")
        ax.text(0.5, 0.5, "No closed trades recorded yet", color="#888888", ha="center", va="center")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)
        return buf, None

    df = pd.DataFrame(records)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values("time").reset_index(drop=True)
    else:
        df["time"] = range(len(df))

    if "equity" not in df.columns and "pnl" in df.columns:
        initial = 10000.0
        df["equity"] = initial + df["pnl"].cumsum()

    equity = df["equity"].values
    peak = pd.Series(equity).cummax()
    dd_pct = (equity - peak) / peak * 100.0

    fig, (ax_eq, ax_dd) = plt.subplots(
        2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]}, facecolor="#131722"
    )
    ax_eq.set_facecolor("#131722")
    ax_dd.set_facecolor("#131722")

    x_vals = df["time"] if "time" in df.columns else range(len(df))

    # Plot Equity
    ax_eq.plot(x_vals, equity, color="#00e676", lw=1.8, label="Portfolio Equity ($)")
    ax_eq.plot(x_vals, peak, color="#ffffff", lw=0.8, ls="--", alpha=0.5, label="High Watermark")
    ax_eq.fill_between(x_vals, equity, peak, color="#ff5252", alpha=0.15)
    ax_eq.set_title(title, color="#ffffff", fontsize=11, fontweight="bold", pad=10)
    ax_eq.grid(True, color="#2a2e39", linestyle=":", alpha=0.6)
    ax_eq.tick_params(colors="#b2b5be", labelsize=8)
    ax_eq.legend(loc="upper left", facecolor="#1e222d", edgecolor="#2a2e39", labelcolor="#ffffff", fontsize=8)

    # Plot Drawdown
    ax_dd.plot(x_vals, dd_pct, color="#ff5252", lw=1.2)
    ax_dd.fill_between(x_vals, dd_pct, 0, color="#ff5252", alpha=0.35)
    ax_dd.set_ylabel("Drawdown %", color="#b2b5be", fontsize=8)
    ax_dd.grid(True, color="#2a2e39", linestyle=":", alpha=0.6)
    ax_dd.tick_params(colors="#b2b5be", labelsize=8)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)

    saved_path = None
    if save_to_disk:
        out_dir = Path("results/charts")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = str(out_dir / f"equity_curve_{ts_str}.png")
        with open(saved_path, "wb") as f:
            f.write(buf.getvalue())

    plt.close(fig)
    return buf, saved_path


def generate_configured_workspace_chart(
    ohlcv_rows: list[dict],
    symbol: str,
    timeframe: str = "H4",
    workspace_config: Optional[dict[str, Any]] = None,
    fvg_zones: Optional[list[dict]] = None,
    order_blocks: Optional[list[dict]] = None,
    structure_breaks: Optional[list[dict]] = None,
    volume_profile: Optional[dict] = None,
    timesfm_cone: Optional[dict] = None,
    save_to_disk: bool = False,
) -> tuple[io.BytesIO, Optional[str]]:
    """
    Renders dark-theme multi-panel chart configured by canonical workspace presets.
    Overlays: EMA, SMA, WMA, Bollinger, Keltner, Donchian, VWAP, Supertrend, Ichimoku,
              Pivot Points, Order Blocks, FVGs, Structure Breaks, Volume Profile, TimesFM Cone.
    Oscillators: Dedicated subpanels for Volume, RSI, MACD, Stochastic, ADX, ATR, CVD / Volatility.
    """
    if not ohlcv_rows or len(ohlcv_rows) < 2:
        raise ValueError(f"Insufficient OHLCV data for {symbol} ({len(ohlcv_rows) if ohlcv_rows else 0} candles)")

    df = pd.DataFrame(ohlcv_rows)
    col_map: dict[str, str] = {}
    for col in df.columns:
        c_low = str(col).lower()
        if c_low in ["timestamp", "time", "date"]:
            col_map[col] = "Date"
        elif c_low == "open":
            col_map[col] = "Open"
        elif c_low == "high":
            col_map[col] = "High"
        elif c_low == "low":
            col_map[col] = "Low"
        elif c_low == "close":
            col_map[col] = "Close"
        elif c_low in ["volume", "tick_volume", "vol"]:
            col_map[col] = "Volume"

    df.rename(columns=col_map, inplace=True)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=len(df), freq="h")

    for req_col in ["Open", "High", "Low", "Close"]:
        if req_col not in df.columns:
            raise ValueError(f"Missing required OHLC column '{req_col}' in dataset")
        df[req_col] = pd.to_numeric(df[req_col], errors="coerce")

    if "Volume" not in df.columns:
        vol_s = pd.Series(0.0, index=df.index, dtype=float)
    else:
        vol_s = pd.Series(pd.to_numeric(df["Volume"], errors="coerce"), index=df.index, dtype=float).fillna(0.0)
    df["Volume"] = vol_s

    open_s = pd.Series(df["Open"], index=df.index, dtype=float)
    high_s = pd.Series(df["High"], index=df.index, dtype=float)
    low_s = pd.Series(df["Low"], index=df.index, dtype=float)
    close_s = pd.Series(df["Close"], index=df.index, dtype=float)

    cfg = normalize_chart_workspace_config(workspace_config)
    overlays = cfg.get("overlays", {})
    oscillators = cfg.get("oscillators", {})

    add_plots: list[Any] = []

    # --- Overlays on Panel 0 ---
    # EMA
    ema_cfg = overlays.get("ema", {})
    if ema_cfg.get("enabled", False):
        ema_colors = ["#00e5ff", "#ffeb3b", "#ff9800", "#e040fb", "#76ff03", "#ff5252"]
        periods = ema_cfg.get("periods", [20, 50, 200])
        for idx, p in enumerate(periods):
            if len(df) >= p:
                ema_s = ta.trend.ema_indicator(close_s, window=p, fillna=False)
                color = ema_colors[idx % len(ema_colors)]
                add_plots.append(mpf.make_addplot(ema_s, panel=0, color=color, width=1.0))

    # SMA
    sma_cfg = overlays.get("sma", {})
    if sma_cfg.get("enabled", False):
        sma_colors = ["#80d8ff", "#ffff8d", "#ffcc80"]
        periods = sma_cfg.get("periods", [20, 50])
        for idx, p in enumerate(periods):
            if len(df) >= p:
                sma_s = ta.trend.sma_indicator(close_s, window=p, fillna=False)
                color = sma_colors[idx % len(sma_colors)]
                add_plots.append(mpf.make_addplot(sma_s, panel=0, color=color, width=1.0, linestyle="--"))

    # WMA
    wma_cfg = overlays.get("wma", {})
    if wma_cfg.get("enabled", False):
        periods = wma_cfg.get("periods", [20])
        for p in periods:
            if len(df) >= p:
                wma_s = compute_wma(close_s, period=p)
                add_plots.append(mpf.make_addplot(wma_s, panel=0, color="#b388ff", width=1.0))

    # Bollinger Bands
    bb_cfg = overlays.get("bollinger", {})
    if bb_cfg.get("enabled", False):
        p = bb_cfg.get("period", 20)
        dev = bb_cfg.get("std_dev", 2.0)
        if len(df) >= p:
            bb_u, bb_m, bb_l, _, _ = compute_bollinger_bands(close_s, period=p, std_dev=dev)
            add_plots.append(mpf.make_addplot(bb_u, panel=0, color="#787b86", linestyle="--", width=0.8))
            add_plots.append(mpf.make_addplot(bb_m, panel=0, color="#ff9800", linestyle="-", width=0.8))
            add_plots.append(mpf.make_addplot(bb_l, panel=0, color="#787b86", linestyle="--", width=0.8))

    # Keltner Channels
    kc_cfg = overlays.get("keltner", {})
    if kc_cfg.get("enabled", False):
        w = kc_cfg.get("window", 20)
        w_atr = kc_cfg.get("window_atr", 10)
        mult = kc_cfg.get("multiplier", 2.0)
        if len(df) >= max(w, w_atr):
            kc_u, kc_m, kc_l = compute_keltner_channels(
                high_s, low_s, close_s, window=w, window_atr=w_atr, multiplier=mult
            )
            add_plots.append(mpf.make_addplot(kc_u, panel=0, color="#29b6f6", linestyle="--", width=0.8))
            add_plots.append(mpf.make_addplot(kc_m, panel=0, color="#0288d1", linestyle="-", width=0.8))
            add_plots.append(mpf.make_addplot(kc_l, panel=0, color="#29b6f6", linestyle="--", width=0.8))

    # Donchian Channels
    dc_cfg = overlays.get("donchian", {})
    if dc_cfg.get("enabled", False):
        w = dc_cfg.get("window", 20)
        if len(df) >= w:
            dc_u, dc_m, dc_l = compute_donchian_channels(high_s, low_s, close_s, window=w)
            add_plots.append(mpf.make_addplot(dc_u, panel=0, color="#ab47bc", linestyle=":", width=0.8))
            add_plots.append(mpf.make_addplot(dc_m, panel=0, color="#7b1fa2", linestyle="-", width=0.8))
            add_plots.append(mpf.make_addplot(dc_l, panel=0, color="#ab47bc", linestyle=":", width=0.8))

    # VWAP
    vwap_cfg = overlays.get("vwap", {})
    if vwap_cfg.get("enabled", False):
        vwap_s = compute_vwap(high_s, low_s, close_s, vol_s, window=vwap_cfg.get("window"))
        add_plots.append(mpf.make_addplot(vwap_s, panel=0, color="#ff4081", linestyle="-", width=1.2))

    # Supertrend
    st_cfg = overlays.get("supertrend", {})
    if st_cfg.get("enabled", False):
        p = st_cfg.get("period", 10)
        mult = st_cfg.get("multiplier", 3.0)
        if len(df) >= p:
            st_s, st_dir = compute_supertrend(high_s, low_s, close_s, period=p, multiplier=mult)
            st_bull = pd.Series(np.where(st_dir == 1, st_s, np.nan), index=df.index)
            st_bear = pd.Series(np.where(st_dir == -1, st_s, np.nan), index=df.index)
            add_plots.append(mpf.make_addplot(st_bull, panel=0, color="#00e676", width=1.3))
            add_plots.append(mpf.make_addplot(st_bear, panel=0, color="#ff1744", width=1.3))

    # Ichimoku
    ichi_cfg = overlays.get("ichimoku", {})
    if ichi_cfg.get("enabled", False):
        tk = ichi_cfg.get("tenkan", 9)
        kj = ichi_cfg.get("kijun", 26)
        sb = ichi_cfg.get("senkou_b", 52)
        if len(df) >= max(tk, kj):
            ichi = compute_ichimoku_series(
                high_s, low_s, close_s, tenkan_period=tk, kijun_period=kj, senkou_b_period=sb
            )
            add_plots.append(mpf.make_addplot(ichi["tenkan_sen"], panel=0, color="#00bcd4", width=0.8))
            add_plots.append(mpf.make_addplot(ichi["kijun_sen"], panel=0, color="#e91e63", width=0.8))
            if len(df) >= sb:
                add_plots.append(
                    mpf.make_addplot(ichi["senkou_span_a"], panel=0, color="#4caf50", linestyle="--", width=0.7)
                )
                add_plots.append(
                    mpf.make_addplot(ichi["senkou_span_b"], panel=0, color="#f44336", linestyle="--", width=0.7)
                )

    # --- Oscillators Subpanels ---
    curr_panel = 1

    # 1. Volume
    vol_cfg = oscillators.get("volume", {})
    if vol_cfg.get("enabled", False):
        p_vol = curr_panel
        curr_panel += 1
        vol_colors = ["#00e676" if c >= o else "#ff1744" for c, o in zip(close_s, open_s)]
        add_plots.append(mpf.make_addplot(vol_s, type="bar", panel=p_vol, color=vol_colors, width=0.8, ylabel="Vol"))
        ma_p = vol_cfg.get("ma_period", 20)
        if len(df) >= ma_p:
            vol_ma = pd.Series(vol_s.rolling(ma_p).mean(), index=df.index)
            add_plots.append(mpf.make_addplot(vol_ma, panel=p_vol, color="#ffeb3b", width=0.9))

    # 2. RSI
    rsi_cfg = oscillators.get("rsi", {})
    if rsi_cfg.get("enabled", False):
        p_rsi = curr_panel
        curr_panel += 1
        p = rsi_cfg.get("period", 14)
        if len(df) >= p:
            rsi_s = compute_rsi(close_s, period=p)
            add_plots.append(mpf.make_addplot(rsi_s, panel=p_rsi, color="#ab47bc", width=1.1, ylabel="RSI"))
            ob = float(rsi_cfg.get("overbought", 70.0))
            os_ = float(rsi_cfg.get("oversold", 30.0))
            add_plots.append(
                mpf.make_addplot(pd.Series(ob, index=df.index), panel=p_rsi, color="#ef5350", linestyle="--", width=0.7)
            )
            add_plots.append(
                mpf.make_addplot(
                    pd.Series(os_, index=df.index), panel=p_rsi, color="#26a69a", linestyle="--", width=0.7
                )
            )

    # 3. MACD
    macd_cfg = oscillators.get("macd", {})
    if macd_cfg.get("enabled", False):
        p_macd = curr_panel
        curr_panel += 1
        fast = macd_cfg.get("fast", 12)
        slow = macd_cfg.get("slow", 26)
        sig = macd_cfg.get("signal", 9)
        if len(df) >= slow:
            m_line, m_sig, m_hist = compute_macd(close_s, fast=fast, slow=slow, signal=sig)
            add_plots.append(mpf.make_addplot(m_line, panel=p_macd, color="#29b6f6", width=1.0, ylabel="MACD"))
            add_plots.append(mpf.make_addplot(m_sig, panel=p_macd, color="#ff9800", width=0.9))
            m_hist_s = pd.Series(m_hist, dtype=float).fillna(0.0)
            hist_colors = ["#00e676" if v >= 0 else "#ff1744" for v in m_hist_s]
            add_plots.append(mpf.make_addplot(m_hist_s, type="bar", panel=p_macd, color=hist_colors, width=0.6))

    # 4. Stochastic
    stoch_cfg = oscillators.get("stochastic", {})
    if stoch_cfg.get("enabled", False):
        p_stoch = curr_panel
        curr_panel += 1
        k_p = stoch_cfg.get("k_period", 14)
        d_p = stoch_cfg.get("d_period", 3)
        if len(df) >= k_p:
            stoch_k, stoch_d = compute_stochastic(high_s, low_s, close_s, k_period=k_p, d_period=d_p)
            add_plots.append(mpf.make_addplot(stoch_k, panel=p_stoch, color="#29b6f6", width=1.0, ylabel="Stoch"))
            add_plots.append(mpf.make_addplot(stoch_d, panel=p_stoch, color="#ff7043", width=0.9))
            add_plots.append(
                mpf.make_addplot(
                    pd.Series(80.0, index=df.index), panel=p_stoch, color="#787b86", linestyle=":", width=0.6
                )
            )
            add_plots.append(
                mpf.make_addplot(
                    pd.Series(20.0, index=df.index), panel=p_stoch, color="#787b86", linestyle=":", width=0.6
                )
            )

    # 5. ADX
    adx_cfg = oscillators.get("adx", {})
    if adx_cfg.get("enabled", False):
        p_adx = curr_panel
        curr_panel += 1
        p = adx_cfg.get("period", 14)
        if len(df) >= p:
            adx_v, p_di, m_di = compute_adx(high_s, low_s, close_s, period=p)
            add_plots.append(mpf.make_addplot(adx_v, panel=p_adx, color="#ffd54f", width=1.1, ylabel="ADX"))
            add_plots.append(mpf.make_addplot(p_di, panel=p_adx, color="#00e676", linestyle="--", width=0.8))
            add_plots.append(mpf.make_addplot(m_di, panel=p_adx, color="#ff1744", linestyle="--", width=0.8))
            add_plots.append(
                mpf.make_addplot(
                    pd.Series(25.0, index=df.index), panel=p_adx, color="#787b86", linestyle=":", width=0.6
                )
            )

    # 6. ATR
    atr_cfg = oscillators.get("atr", {})
    if atr_cfg.get("enabled", False):
        p_atr = curr_panel
        curr_panel += 1
        p = atr_cfg.get("period", 14)
        if len(df) >= p:
            atr_s = compute_atr(high_s, low_s, close_s, period=p)
            add_plots.append(mpf.make_addplot(atr_s, panel=p_atr, color="#26c6da", width=1.0, ylabel="ATR"))

    # 7. CVD / Volatility
    cvd_cfg = oscillators.get("cvd_volatility", {})
    if cvd_cfg.get("enabled", False):
        p_cvd = curr_panel
        curr_panel += 1
        mode = cvd_cfg.get("mode", "cvd")
        w = cvd_cfg.get("window", 20)
        if mode == "yang_zhang":
            yz_s = compute_yang_zhang_volatility(df, window=w)
            add_plots.append(mpf.make_addplot(yz_s, panel=p_cvd, color="#ab47bc", width=1.0, ylabel="YZ Vol"))
        elif mode == "ac1":
            ac1_s = compute_lag1_autocorrelation(close_s, window=w)
            add_plots.append(mpf.make_addplot(ac1_s, panel=p_cvd, color="#26a69a", width=1.0, ylabel="AC1"))
        else:  # cvd
            cvd_s = compute_cvd_series(open_s, high_s, low_s, close_s, vol_s)
            add_plots.append(mpf.make_addplot(cvd_s, panel=p_cvd, color="#ffb74d", width=1.0, ylabel="CVD"))

    num_subpanels = curr_panel - 1
    if num_subpanels > 0:
        panel_ratios = (4.0, *([1.2] * num_subpanels))
        fig_h = max(6.0, 4.5 + (num_subpanels * 1.5))
    else:
        panel_ratios = None
        fig_h = 6.0

    plot_kwargs: dict[str, Any] = {
        "type": "candle",
        "style": DARK_STYLE,
        "volume": False,
        "figsize": (11, fig_h),
        "returnfig": True,
    }
    if add_plots:
        plot_kwargs["addplot"] = add_plots
    if panel_ratios is not None:
        plot_kwargs["panel_ratios"] = panel_ratios

    fig, axlist = mpf.plot(df, **plot_kwargs)
    main_ax = axlist[0]

    # --- Render SMC Structures & Levels on main_ax ---
    # Order Blocks
    if overlays.get("smc_order_blocks", True) and order_blocks:
        for ob in order_blocks:
            top = float(ob.get("high", ob.get("price_high", 0)))
            bottom = float(ob.get("low", ob.get("price_low", 0)))
            direction = str(ob.get("direction", "bullish")).lower()
            height = abs(top - bottom)
            y_min = min(top, bottom)
            is_bull = "bull" in direction or "demand" in direction
            color = "#00e676" if is_bull else "#ff1744"
            rect = patches.Rectangle(
                (0, y_min), len(df), height, linewidth=1.2, edgecolor=color, facecolor=color, alpha=0.22
            )
            main_ax.add_patch(rect)

    # FVG Zones
    if overlays.get("smc_fvg", True) and fvg_zones:
        for fvg in fvg_zones:
            top = float(fvg.get("top", fvg.get("high", 0)))
            bottom = float(fvg.get("bottom", fvg.get("low", 0)))
            fvg_type = str(fvg.get("type", "bullish")).lower()
            height = abs(top - bottom)
            y_min = min(top, bottom)
            is_bull = "bull" in fvg_type
            color = "#00e676" if is_bull else "#ff1744"
            rect = patches.Rectangle(
                (0, y_min), len(df), height, linewidth=1.0, edgecolor=color, facecolor=color, alpha=0.18, linestyle="--"
            )
            main_ax.add_patch(rect)

    # Structure Breaks (BOS / CHoCH)
    if overlays.get("smc_bos", True) and structure_breaks:
        for sb in structure_breaks:
            lvl = float(sb.get("price", sb.get("level", 0)))
            sb_type = str(sb.get("type", "BOS")).upper()
            sb_color = "#00e5ff" if "BOS" in sb_type else "#ffea00"
            if lvl > 0:
                main_ax.axhline(lvl, color=sb_color, linestyle="--", linewidth=1.0, alpha=0.8)

    # Pivot Points
    pp_ov = overlays.get("pivot_points", {})
    if pp_ov.get("enabled", False) and len(df) >= 2:
        method = pp_ov.get("method", "classic")
        bar = df.iloc[-2]
        pp = compute_pivot_points(float(bar["High"]), float(bar["Low"]), float(bar["Close"]), method=method)
        if "pivot" in pp:
            main_ax.axhline(pp["pivot"], color="#ffffff", linestyle="-", linewidth=1.0, alpha=0.7)
        for k, color in [("r1", "#ef5350"), ("r2", "#ef5350"), ("s1", "#26a69a"), ("s2", "#26a69a")]:
            if k in pp:
                main_ax.axhline(pp[k], color=color, linestyle=":", linewidth=0.8, alpha=0.65)

    # Volume Profile
    if overlays.get("volume_profile", True) and volume_profile and isinstance(volume_profile, dict):
        poc = volume_profile.get("poc")
        vah = volume_profile.get("vah")
        val = volume_profile.get("val")
        if poc:
            main_ax.axhline(float(poc), color="#ffd700", linestyle="-", linewidth=1.4, alpha=0.9, label="POC")
        if vah:
            main_ax.axhline(float(vah), color="#42a5f5", linestyle=":", linewidth=1.1, alpha=0.8, label="VAH")
        if val:
            main_ax.axhline(float(val), color="#42a5f5", linestyle=":", linewidth=1.1, alpha=0.8, label="VAL")

    # TimesFM Cone
    if overlays.get("timesfm_cone", True) and timesfm_cone and isinstance(timesfm_cone, dict):
        q10 = timesfm_cone.get("q10", [])
        q50 = timesfm_cone.get("q50", [])
        q90 = timesfm_cone.get("q90", [])
        if q10 and q90:
            horizon = min(len(q10), len(q90))
            start_x = len(df) - 1
            x_indices = np.arange(start_x, start_x + horizon)
            main_ax.fill_between(x_indices, q10[:horizon], q90[:horizon], color="#7c4dff", alpha=0.25)
            if q50:
                main_ax.plot(x_indices, q50[:horizon], color="#b388ff", linestyle="-.", linewidth=1.5)

    # --- Title & Subtitle Banner ---
    active_overlays: list[str] = []
    if overlays.get("ema", {}).get("enabled"):
        active_overlays.append(f"EMA{overlays['ema']['periods']}")
    if overlays.get("sma", {}).get("enabled"):
        active_overlays.append(f"SMA{overlays['sma']['periods']}")
    if overlays.get("wma", {}).get("enabled"):
        active_overlays.append(f"WMA{overlays['wma']['periods']}")
    if overlays.get("bollinger", {}).get("enabled"):
        active_overlays.append(f"BB({overlays['bollinger'].get('period', 20)})")
    if overlays.get("keltner", {}).get("enabled"):
        active_overlays.append(f"KC({overlays['keltner'].get('window', 20)})")
    if overlays.get("donchian", {}).get("enabled"):
        active_overlays.append(f"DC({overlays['donchian'].get('window', 20)})")
    if overlays.get("vwap", {}).get("enabled"):
        active_overlays.append("VWAP")
    if overlays.get("supertrend", {}).get("enabled"):
        active_overlays.append(f"ST({overlays['supertrend'].get('period', 10)})")
    if overlays.get("ichimoku", {}).get("enabled"):
        active_overlays.append("Ichimoku")
    if overlays.get("pivot_points", {}).get("enabled"):
        active_overlays.append(f"Pivot({overlays['pivot_points'].get('method', 'classic')})")
    if overlays.get("smc_order_blocks", False) and order_blocks:
        active_overlays.append(f"OB({len(order_blocks)})")
    if overlays.get("smc_fvg", False) and fvg_zones:
        active_overlays.append(f"FVG({len(fvg_zones)})")
    if overlays.get("volume_profile", False) and volume_profile:
        active_overlays.append("VP")
    if overlays.get("timesfm_cone", False) and timesfm_cone:
        active_overlays.append("TimesFM")

    active_oscillators: list[str] = []
    if oscillators.get("volume", {}).get("enabled"):
        active_oscillators.append("Volume")
    if oscillators.get("rsi", {}).get("enabled"):
        active_oscillators.append(f"RSI({oscillators['rsi'].get('period', 14)})")
    if oscillators.get("macd", {}).get("enabled"):
        active_oscillators.append("MACD")
    if oscillators.get("stochastic", {}).get("enabled"):
        active_oscillators.append("Stoch")
    if oscillators.get("adx", {}).get("enabled"):
        active_oscillators.append(f"ADX({oscillators['adx'].get('period', 14)})")
    if oscillators.get("atr", {}).get("enabled"):
        active_oscillators.append(f"ATR({oscillators['atr'].get('period', 14)})")
    if oscillators.get("cvd_volatility", {}).get("enabled"):
        active_oscillators.append(str(oscillators["cvd_volatility"].get("mode", "cvd")).upper())

    preset_label = str(cfg.get("preset_id", "custom")).upper()
    ov_str = ", ".join(active_overlays) if active_overlays else "None"
    osc_str = ", ".join(active_oscillators) if active_oscillators else "None"

    title_text = (
        f"{symbol}  •  {timeframe}  [{preset_label}]  ({len(df)} candles)\n"
        f"Overlays: {ov_str}  |  Oscillators: {osc_str}"
    )
    fig.suptitle(title_text, color="#ffffff", fontsize=9, fontweight="bold", y=0.985)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)

    saved_path = None
    if save_to_disk:
        out_dir = Path("results/charts")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = str(out_dir / f"{symbol}_{timeframe}_{preset_label.lower()}_{ts_str}.png")
        with open(saved_path, "wb") as f:
            f.write(buf.getvalue())

    plt.close(fig)
    return buf, saved_path


async def generate_configured_workspace_chart_async(
    ohlcv_rows: list[dict],
    symbol: str,
    timeframe: str = "H4",
    workspace_config: Optional[dict[str, Any]] = None,
    fvg_zones: Optional[list[dict]] = None,
    order_blocks: Optional[list[dict]] = None,
    structure_breaks: Optional[list[dict]] = None,
    volume_profile: Optional[dict] = None,
    timesfm_cone: Optional[dict] = None,
    save_to_disk: bool = False,
) -> tuple[io.BytesIO, Optional[str]]:
    """Async wrapper non-blocking running workspace chart generation in a worker thread."""
    import asyncio

    return await asyncio.to_thread(
        generate_configured_workspace_chart,
        ohlcv_rows,
        symbol,
        timeframe=timeframe,
        workspace_config=workspace_config,
        fvg_zones=fvg_zones,
        order_blocks=order_blocks,
        structure_breaks=structure_breaks,
        volume_profile=volume_profile,
        timesfm_cone=timesfm_cone,
        save_to_disk=save_to_disk,
    )
