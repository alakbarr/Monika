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
from typing import Optional, Any
from datetime import datetime

import matplotlib
matplotlib.use('Agg')  # Headless mode — wajib sebelum import mplfinance
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

logger = logging.getLogger("TradingAgent.ChartGenerator")

DARK_STYLE = mpf.make_mpf_style(
    base_mpf_style='nightclouds',
    rc={
        'font.size': 8,
        'axes.titlesize': 10,
        'axes.labelsize': 8,
        'xtick.labelsize': 7,
        'ytick.labelsize': 7,
        'figure.facecolor': '#131722',
        'axes.facecolor': '#131722',
    }
)


def generate_candlestick_chart(
    ohlcv_rows: list[dict],
    symbol: str,
    timeframe: str = "H1",
    show_volume: bool = True,
    show_ma: tuple = (20, 50),
    indicators: Optional[dict] = None,
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
        df.index = pd.date_range(end=pd.Timestamp.now(tz='UTC'), periods=len(df), freq='h')

    # Convert numeric columns to float
    for req_col in ["Open", "High", "Low", "Close"]:
        if req_col not in df.columns:
            raise ValueError(f"Missing required OHLC column '{req_col}' in dataset")
        df[req_col] = pd.to_numeric(df[req_col], errors='coerce')

    if "Volume" not in df.columns or df["Volume"].dropna().empty or (df["Volume"] == 0).all():
        df["Volume"] = 0
        has_volume = False
    else:
        df["Volume"] = pd.to_numeric(df["Volume"], errors='coerce').fillna(0)
        has_volume = show_volume

    add_plots = []
    if indicators:
        for name, values in indicators.items():
            if len(values) == len(df):
                try:
                    s = pd.Series(values, index=df.index)
                    panel = 0 if any(k in name.lower() for k in ["ma", "ema", "sma", "band"]) else 2
                    color = 'yellow' if 'rsi' in name.lower() else 'cyan'
                    add_plots.append(mpf.make_addplot(s, panel=panel, color=color, width=0.8))
                except Exception as e:
                    logger.debug(f"Failed to add indicator plot for {name}: {e}")

    buf = io.BytesIO()
    kwargs: dict[str, Any] = {
        "type": "candle",
        "style": DARK_STYLE,
        "title": f"\n{symbol}  •  {timeframe}  ({len(df)} candles)",
        "volume": has_volume,
        "savefig": dict(fname=buf, dpi=100, bbox_inches='tight', format='png'),
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
        plt.close('all')


async def generate_candlestick_chart_async(
    ohlcv_rows: list[dict],
    symbol: str,
    timeframe: str = "H1",
    show_volume: bool = True,
    show_ma: tuple = (20, 50),
    indicators: Optional[dict] = None,
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
    fvg_list: Optional[list[dict]] = None,
    swing_points: Optional[list[dict]] = None,
    order_blocks: Optional[list[dict]] = None,
    volume_profile: Optional[dict] = None,
    save_to_disk: bool = True,
) -> tuple[io.BytesIO, Optional[str]]:
    """
    Renders dark-theme candlestick chart with SMC overlays:
    - Transparent Green/Red rectangles for Bullish/Bearish Fair Value Gaps (FVG)
    - Transparent Order Block rectangles (Demand=Green, Supply=Red)
    - Horizontal Volume Profile lines (POC, VAH, VAL)
    - Triangle markers for Swing Highs (red) and Swing Lows (green)
    Returns: (BytesIO buffer, Optional filepath on disk)
    """
    import matplotlib.patches as patches
    from pathlib import Path
    import os

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
        df.index = pd.date_range(end=pd.Timestamp.now(tz='UTC'), periods=len(df), freq='h')

    for req_col in ["Open", "High", "Low", "Close"]:
        if req_col in df.columns:
            df[req_col] = pd.to_numeric(df[req_col], errors='coerce')

    has_volume = "Volume" in df.columns and not (pd.to_numeric(df["Volume"], errors='coerce').fillna(0) == 0).all()
    if has_volume:
        df["Volume"] = pd.to_numeric(df["Volume"], errors='coerce').fillna(0)

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
                (0, y_min), len(df), height,
                linewidth=1, edgecolor=color, facecolor=color, alpha=alpha, linestyle="--"
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
                (0, y_min), len(df), height,
                linewidth=1.2, edgecolor=color, facecolor=color, alpha=0.25, linestyle="-"
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

            if idx is not None and 0 <= idx < len(df):
                if "high" in p_type or "top" in p_type or "peak" in p_type:
                    main_ax.scatter(idx, price, marker="v", color="#ff5252", s=70, zorder=6)
                else:
                    main_ax.scatter(idx, price, marker="^", color="#69f0ae", s=70, zorder=6)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
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
) -> tuple[io.BytesIO, Optional[str]]:
    """
    Renders a dark-themed portfolio equity curve with drawdown fill band.
    """
    from pathlib import Path
    if not records:
        fig, ax = plt.subplots(figsize=(10, 5), facecolor='#131722')
        ax.set_facecolor('#131722')
        ax.text(0.5, 0.5, "No closed trades recorded yet", color="#888888", ha="center", va="center")
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
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
        2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [3, 1]},
        facecolor='#131722'
    )
    ax_eq.set_facecolor('#131722')
    ax_dd.set_facecolor('#131722')

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
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
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

