"""
Low-level synchronous MT5 worker functions executed inside dedicated thread workers.
"""

import os
import sys
from datetime import datetime
from typing import Any, Optional

from .constants import MT5ProfileMismatchError, logger

_LAST_CONNECTED_TRADE_MODE: Optional[int] = None


def _market_book_add(symbol: str) -> bool:
    try:
        import MetaTrader5 as _mt5

        mt5: Any = _mt5
        return bool(mt5.market_book_add(symbol))
    except Exception as e:
        logger.debug(f"market_book_add error for {symbol}: {e}")
        return False


def _market_book_get(symbol: str) -> Any:
    try:
        import MetaTrader5 as _mt5

        mt5: Any = _mt5
        return mt5.market_book_get(symbol)
    except Exception as e:
        logger.debug(f"market_book_get error for {symbol}: {e}")
        return None


def _market_book_release(symbol: str) -> bool:
    try:
        import MetaTrader5 as _mt5

        mt5: Any = _mt5
        return bool(mt5.market_book_release(symbol))
    except Exception as e:
        logger.debug(f"market_book_release error for {symbol}: {e}")
        return False


def _connect(path: str, account: int, password: str, server: str, expected_trade_mode: Optional[str] = None) -> bool:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    logger.info(f"Initializing MT5: {path}")
    init_kwargs: dict[str, Any] = {}
    if path and (os.path.exists(path) or sys.platform == "win32"):
        init_kwargs["path"] = path
    elif path:
        logger.debug(f"Path '{path}' not found on host filesystem; connecting to running MT5 terminal instance.")

    if not mt5.initialize(**init_kwargs):
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False
    if not mt5.login(account, password=password, server=server):
        logger.error(f"MT5 login failed: {mt5.last_error()}")
        mt5.shutdown()
        return False
    info = mt5.account_info()
    if info is None:
        logger.error("MT5 account_info() returned None after login")
        mt5.shutdown()
        return False

    # Account Login Pinning Assertion
    logged_login = getattr(info, "login", 0)
    if account > 0 and logged_login != account:
        err_msg = (
            f"MT5 Login Pinning Violation: Terminal active account is {logged_login}, "
            f"but configured account is {account}. Immediate shutdown to prevent profile mismatch."
        )
        logger.critical(err_msg)
        mt5.shutdown()
        raise MT5ProfileMismatchError(err_msg)

    # Trade Mode Hard Assertion (0=DEMO, 1=CONTEST, 2=REAL)
    target_mode = (expected_trade_mode or os.getenv("MT5_EXPECTED_TRADE_MODE", "")).strip().upper()
    if target_mode:
        trade_mode = getattr(info, "trade_mode", None)
        mode_names = {0: "DEMO", 1: "CONTEST", 2: "REAL"}
        actual_mode = mode_names.get(int(trade_mode) if trade_mode is not None else -1, "UNKNOWN")
        if actual_mode != target_mode:
            err_msg = (
                f"MT5 Trade Mode Mismatch: Terminal is running in {actual_mode} mode (code={trade_mode}), "
                f"but expected {target_mode}! Immediate shutdown to prevent accidental live execution."
            )
            logger.critical(err_msg)
            mt5.shutdown()
            raise MT5ProfileMismatchError(err_msg)

    bal = getattr(info, "balance", 0.0) if info else 0.0
    curr = getattr(info, "currency", "USD") if info else "USD"
    global _LAST_CONNECTED_TRADE_MODE
    _LAST_CONNECTED_TRADE_MODE = getattr(info, "trade_mode", 0) if info else None

    logger.info(
        f"MT5 connected: {server} | Account {account} | "
        f"Balance={bal:.2f} {curr} | TradeMode={getattr(info, 'trade_mode', 'N/A')}"
    )
    return True


def _disconnect() -> None:
    global _LAST_CONNECTED_TRADE_MODE
    _LAST_CONNECTED_TRADE_MODE = None
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    mt5.shutdown()


def _is_connected() -> bool:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    info = mt5.account_info()
    return info is not None


def _get_account_info() -> Any:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    return mt5.account_info()


def _get_symbol_info(symbol: str) -> Any:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    return mt5.symbol_info(symbol)


def _copy_rates_from_pos(symbol: str, tf: int, start: int, count: int) -> Any:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    return mt5.copy_rates_from_pos(symbol, tf, start, count)


def _copy_rates_range(symbol: str, tf: int, date_from: Any, date_to: Any) -> Any:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    return mt5.copy_rates_range(symbol, tf, date_from, date_to)


def _get_last_tick(symbol: str) -> Any:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5
    return mt5.symbol_info_tick(symbol)


def _copy_ticks_range(symbol: str, date_from: datetime, date_to: datetime, flags: int = 1) -> list[dict[str, Any]]:
    import MetaTrader5 as _mt5
    import pandas as pd

    ticks = _mt5.copy_ticks_range(symbol, date_from, date_to, flags)
    if ticks is None or len(ticks) == 0:
        return []

    df = pd.DataFrame(ticks)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
    return df.to_dict(orient="records")


def _calculate_dom_vwap(symbol: str, direction: str, volume: float) -> dict[str, Any]:
    """
    Computes Level 2 DOM ladder walk VWAP for large orders using MT5 market depth.
    Walks bids (for sell) or asks (for buy) to compute weighted average execution price
    and expected slippage vs Top-of-Book BBO.
    """
    import MetaTrader5 as _mt5

    mt5: Any = _mt5

    book = mt5.market_book_get(symbol)
    if not book or len(book) == 0:
        return {"has_dom": False, "vwap": None, "slippage_pts": 0.0, "filled_pct": 1.0}

    is_buy = str(direction).lower().strip() == "buy"
    ladder = []
    for item in book:
        item_type = getattr(item, "type", None)
        if item_type is None and isinstance(item, (tuple, list)):
            item_type = item[0]
            item_price = float(item[1])
            item_vol = float(item[2])
        else:
            item_price = float(getattr(item, "price", 0.0))
            item_vol = float(getattr(item, "volume_dbl", getattr(item, "volume", 0.0)))

        if is_buy and item_type == 2:  # BOOK_TYPE_SELL (Asks)
            ladder.append((item_price, item_vol))
        elif not is_buy and item_type == 1:  # BOOK_TYPE_BUY (Bids)
            ladder.append((item_price, item_vol))

    if not ladder:
        return {"has_dom": False, "vwap": None, "slippage_pts": 0.0, "filled_pct": 1.0}

    ladder.sort(key=lambda x: x[0], reverse=not is_buy)
    bbo_price = ladder[0][0]

    remaining = float(volume)
    weighted_sum = 0.0
    filled_vol = 0.0

    for p, d in ladder:
        take = min(remaining, d)
        weighted_sum += take * p
        filled_vol += take
        remaining -= take
        if remaining <= 1e-6:
            break

    if filled_vol <= 0:
        return {"has_dom": True, "vwap": bbo_price, "slippage_pts": 0.0, "filled_pct": 0.0}

    vwap = weighted_sum / filled_vol
    info = mt5.symbol_info(symbol)
    point = float(getattr(info, "point", 0.00001) or 0.00001)
    digits = int(getattr(info, "digits", 5) or 5)
    slippage_pts = abs(vwap - bbo_price) / point

    return {
        "has_dom": True,
        "vwap": round(vwap, digits),
        "bbo_price": bbo_price,
        "slippage_pts": round(slippage_pts, 1),
        "filled_pct": round(filled_vol / volume, 2),
    }


MT5_RETCODE_DESCRIPTIONS: dict[int, str] = {
    10004: "Requote: Harga berubah cepat, ulangi order.",
    10006: "Order ditolak oleh broker/server.",
    10007: "Order dibatalkan oleh trader atau sistem.",
    10008: "Order ditempatkan (pending).",
    10009: "Order berhasil dieksekusi.",
    10011: "Error umum pemrosesan order oleh server broker.",
    10012: "Request timeout. Periksa latensi atau koneksi ke broker.",
    10013: "Request tidak valid. Periksa parameter order.",
    10014: "Volume/lot tidak valid (cek min/max/step lot simbol pada broker).",
    10015: "Harga order tidak valid (cek kuotasi harga terkini).",
    10016: "SL/TP tidak valid (jarak terlalu dekat dengan pasar / melanggar stop level broker).",
    10017: "Trading dinonaktifkan untuk simbol ini oleh broker.",
    10018: "Pasar sedang tutup untuk simbol ini.",
    10019: "Margin tidak mencukupi untuk membuka posisi (cek free margin & lot size).",
    10020: "Harga telah berubah (slippage melebihi deviation yang diizinkan).",
    10021: "Tidak ada kuotasi harga untuk memproses order.",
    10022: "Waktu kadaluarsa order pending tidak valid.",
    10023: "Status order telah berubah sebelum diproses.",
    10024: "Terlalu banyak request ke broker dalam waktu singkat (rate limited).",
    10025: "Tidak ada perubahan pada order/posisi yang diminta.",
    10026: "Auto-trading dinonaktifkan oleh server broker.",
    10027: "Algo Trading dinonaktifkan di terminal MT5 (aktifkan tombol Algo Trading di MT5).",
    10028: "Request diblokir karena operasi lain sedang diproses.",
    10029: "Order atau posisi dalam status beku (frozen).",
    10030: "Tipe pengisian (filling mode) tidak didukung untuk simbol ini.",
    10031: "Tidak ada koneksi ke server trading MT5.",
    10032: "Operasi hanya diperbolehkan untuk akun live/real.",
    10033: "Batas jumlah pending order pada broker telah tercapai.",
    10034: "Batas volume maksimum posisi untuk simbol ini telah tercapai.",
    10035: "Posisi sudah ditutup sebelumnya.",
}


def format_mt5_error(retcode: int, comment: str = "") -> str:
    """Format MT5 error retcode into human-actionable Indonesian explanation."""
    desc = MT5_RETCODE_DESCRIPTIONS.get(retcode, "Error broker tidak diketahui.")
    cmt_str = f" [{comment}]" if comment else ""
    return f"retcode={retcode}{cmt_str}: {desc}"


def _capture_chart_screenshot(symbol: str, tf: int, width: int, height: int, filepath: str) -> dict[str, Any]:
    import MetaTrader5 as _mt5

    mt5: Any = _mt5

    charts_fn = getattr(mt5, "charts_get", None)
    screenshot_fn = getattr(mt5, "chart_screenshot", None)
    open_fn = getattr(mt5, "chart_open", None)

    if not callable(screenshot_fn):
        return {
            "success": False,
            "error": "MT5 Python API does not provide GUI chart_screenshot. Use plot_price_chart or get_chart.",
        }

    charts = charts_fn() if callable(charts_fn) else []
    target_chart_id = None
    for c in charts:
        if getattr(c, "symbol", "") == symbol:
            target_chart_id = getattr(c, "chart_id", None) or getattr(c, "id", None)
            break

    if target_chart_id is None and callable(open_fn):
        target_chart_id = open_fn(symbol, tf)

    if target_chart_id is None:
        return {"success": False, "error": f"Could not find or open MT5 chart for {symbol}"}

    success = screenshot_fn(target_chart_id, filepath, width, height)
    if success:
        return {"success": True, "chart_id": target_chart_id, "symbol": symbol, "filepath": filepath}
    return {"success": False, "error": f"chart_screenshot returned False for chart_id {target_chart_id}"}
