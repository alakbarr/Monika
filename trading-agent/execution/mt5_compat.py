# ==============================================================================
# File: execution/mt5_compat.py
# ==============================================================================

"""
MT5 Cross-Platform Compatibility & RPC Bridge Layer
===================================================

Menyediakan lapisan kompatibilitas transparan untuk MetaTrader 5 (MT5) di berbagai platform:
  1. Windows (Native): Menggunakan C-extension resmi `MetaTrader5` tanpa overhead.
  2. Linux VPS (RPC Bridge): Menggunakan `mt5linux` / RPyC bridge yang terhubung ke
     instance `terminal64.exe` & `mt5server.exe` yang berjalan di Wine atau container terisolasi.
  3. CI/Test/Mock Fallback: Menyediakan konstanta resmi MT5 lengkap dan interface fallback
     ketika terminal MT5 tidak aktif atau sedang dalam pengujian paper-trading.

Layer ini menginjeksikan dirinya ke dalam `sys.modules["MetaTrader5"]` sehingga seluruh
kode di dalam proyek (seperti `mt5_client.py`, `position_synchronizer.py`, `self_healing_executor.py`,
`startup_checks.py`, dll.) dapat menggunakan `import MetaTrader5 as mt5` tanpa perubahan kode.
"""

from __future__ import annotations

import logging
import os
import sys
import types
from typing import Any, Optional, Dict, Tuple

logger = logging.getLogger("TradingAgent.MT5Compat")

# ------------------------------------------------------------------------------
# Exhaustive Standard MetaTrader 5 Constants Dictionary
# ------------------------------------------------------------------------------
MT5_CONSTANTS: Dict[str, Any] = {
    "ACCOUNT_MARGIN_MODE_EXCHANGE": 1,
    "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING": 2,
    "ACCOUNT_MARGIN_MODE_RETAIL_NETTING": 0,
    "ACCOUNT_STOPOUT_MODE_MONEY": 1,
    "ACCOUNT_STOPOUT_MODE_PERCENT": 0,
    "ACCOUNT_TRADE_MODE_CONTEST": 1,
    "ACCOUNT_TRADE_MODE_DEMO": 0,
    "ACCOUNT_TRADE_MODE_REAL": 2,
    "BOOK_TYPE_BUY": 2,
    "BOOK_TYPE_BUY_MARKET": 4,
    "BOOK_TYPE_SELL": 1,
    "BOOK_TYPE_SELL_MARKET": 3,
    "COPY_TICKS_ALL": -1,
    "COPY_TICKS_INFO": 1,
    "COPY_TICKS_TRADE": 2,
    "DAY_OF_WEEK_FRIDAY": 5,
    "DAY_OF_WEEK_MONDAY": 1,
    "DAY_OF_WEEK_SATURDAY": 6,
    "DAY_OF_WEEK_SUNDAY": 0,
    "DAY_OF_WEEK_THURSDAY": 4,
    "DAY_OF_WEEK_TUESDAY": 2,
    "DAY_OF_WEEK_WEDNESDAY": 3,
    "DEAL_DIVIDEND": 15,
    "DEAL_DIVIDEND_FRANKED": 16,
    "DEAL_ENTRY_IN": 0,
    "DEAL_ENTRY_INOUT": 2,
    "DEAL_ENTRY_OUT": 1,
    "DEAL_ENTRY_OUT_BY": 3,
    "DEAL_REASON_CLIENT": 0,
    "DEAL_REASON_EXPERT": 3,
    "DEAL_REASON_MOBILE": 1,
    "DEAL_REASON_ROLLOVER": 7,
    "DEAL_REASON_SL": 4,
    "DEAL_REASON_SO": 6,
    "DEAL_REASON_SPLIT": 9,
    "DEAL_REASON_TP": 5,
    "DEAL_REASON_VMARGIN": 8,
    "DEAL_REASON_WEB": 2,
    "DEAL_TAX": 17,
    "DEAL_TYPE_BALANCE": 2,
    "DEAL_TYPE_BONUS": 6,
    "DEAL_TYPE_BUY": 0,
    "DEAL_TYPE_BUY_CANCELED": 13,
    "DEAL_TYPE_CHARGE": 4,
    "DEAL_TYPE_COMMISSION": 7,
    "DEAL_TYPE_COMMISSION_AGENT_DAILY": 10,
    "DEAL_TYPE_COMMISSION_AGENT_MONTHLY": 11,
    "DEAL_TYPE_COMMISSION_DAILY": 8,
    "DEAL_TYPE_COMMISSION_MONTHLY": 9,
    "DEAL_TYPE_CORRECTION": 5,
    "DEAL_TYPE_CREDIT": 3,
    "DEAL_TYPE_INTEREST": 12,
    "DEAL_TYPE_SELL": 1,
    "DEAL_TYPE_SELL_CANCELED": 14,
    "ORDER_FILLING_BOC": 3,
    "ORDER_FILLING_FOK": 0,
    "ORDER_FILLING_IOC": 1,
    "ORDER_FILLING_RETURN": 2,
    "ORDER_REASON_CLIENT": 0,
    "ORDER_REASON_EXPERT": 3,
    "ORDER_REASON_MOBILE": 1,
    "ORDER_REASON_SL": 4,
    "ORDER_REASON_SO": 6,
    "ORDER_REASON_TP": 5,
    "ORDER_REASON_WEB": 2,
    "ORDER_STATE_CANCELED": 2,
    "ORDER_STATE_EXPIRED": 6,
    "ORDER_STATE_FILLED": 4,
    "ORDER_STATE_PARTIAL": 3,
    "ORDER_STATE_PLACED": 1,
    "ORDER_STATE_REJECTED": 5,
    "ORDER_STATE_REQUEST_ADD": 7,
    "ORDER_STATE_REQUEST_CANCEL": 9,
    "ORDER_STATE_REQUEST_MODIFY": 8,
    "ORDER_STATE_STARTED": 0,
    "ORDER_TIME_DAY": 1,
    "ORDER_TIME_GTC": 0,
    "ORDER_TIME_SPECIFIED": 2,
    "ORDER_TIME_SPECIFIED_DAY": 3,
    "ORDER_TYPE_BUY": 0,
    "ORDER_TYPE_BUY_LIMIT": 2,
    "ORDER_TYPE_BUY_STOP": 4,
    "ORDER_TYPE_BUY_STOP_LIMIT": 6,
    "ORDER_TYPE_CLOSE_BY": 8,
    "ORDER_TYPE_SELL": 1,
    "ORDER_TYPE_SELL_LIMIT": 3,
    "ORDER_TYPE_SELL_STOP": 5,
    "ORDER_TYPE_SELL_STOP_LIMIT": 7,
    "POSITION_REASON_CLIENT": 0,
    "POSITION_REASON_EXPERT": 3,
    "POSITION_REASON_MOBILE": 1,
    "POSITION_REASON_WEB": 2,
    "POSITION_TYPE_BUY": 0,
    "POSITION_TYPE_SELL": 1,
    "RES_E_AUTH_FAILED": -6,
    "RES_E_AUTO_TRADING_DISABLED": -8,
    "RES_E_FAIL": -1,
    "RES_E_INTERNAL_FAIL": -10000,
    "RES_E_INTERNAL_FAIL_CONNECT": -10004,
    "RES_E_INTERNAL_FAIL_INIT": -10003,
    "RES_E_INTERNAL_FAIL_RECEIVE": -10002,
    "RES_E_INTERNAL_FAIL_SEND": -10001,
    "RES_E_INTERNAL_FAIL_TIMEOUT": -10005,
    "RES_E_INVALID_PARAMS": -2,
    "RES_E_INVALID_VERSION": -5,
    "RES_E_NOT_FOUND": -4,
    "RES_E_NO_MEMORY": -3,
    "RES_E_UNSUPPORTED": -7,
    "RES_S_OK": 1,
    "SYMBOL_CALC_MODE_CFD": 2,
    "SYMBOL_CALC_MODE_CFDINDEX": 3,
    "SYMBOL_CALC_MODE_CFDLEVERAGE": 4,
    "SYMBOL_CALC_MODE_EXCH_BONDS": 37,
    "SYMBOL_CALC_MODE_EXCH_BONDS_MOEX": 39,
    "SYMBOL_CALC_MODE_EXCH_FUTURES": 33,
    "SYMBOL_CALC_MODE_EXCH_OPTIONS": 34,
    "SYMBOL_CALC_MODE_EXCH_OPTIONS_MARGIN": 36,
    "SYMBOL_CALC_MODE_EXCH_STOCKS": 32,
    "SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX": 38,
    "SYMBOL_CALC_MODE_FOREX": 0,
    "SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE": 5,
    "SYMBOL_CALC_MODE_FUTURES": 1,
    "SYMBOL_CALC_MODE_SERV_COLLATERAL": 64,
    "SYMBOL_CHART_MODE_BID": 0,
    "SYMBOL_CHART_MODE_LAST": 1,
    "SYMBOL_OPTION_MODE_AMERICAN": 1,
    "SYMBOL_OPTION_MODE_EUROPEAN": 0,
    "SYMBOL_OPTION_RIGHT_CALL": 0,
    "SYMBOL_OPTION_RIGHT_PUT": 1,
    "SYMBOL_ORDERS_DAILY": 1,
    "SYMBOL_ORDERS_DAILY_NO_STOPS": 2,
    "SYMBOL_ORDERS_GTC": 0,
    "SYMBOL_SWAP_MODE_CURRENCY_DEPOSIT": 4,
    "SYMBOL_SWAP_MODE_CURRENCY_MARGIN": 3,
    "SYMBOL_SWAP_MODE_CURRENCY_SYMBOL": 2,
    "SYMBOL_SWAP_MODE_DISABLED": 0,
    "SYMBOL_SWAP_MODE_INTEREST_CURRENT": 5,
    "SYMBOL_SWAP_MODE_INTEREST_OPEN": 6,
    "SYMBOL_SWAP_MODE_POINTS": 1,
    "SYMBOL_SWAP_MODE_REOPEN_BID": 8,
    "SYMBOL_SWAP_MODE_REOPEN_CURRENT": 7,
    "SYMBOL_TRADE_EXECUTION_EXCHANGE": 3,
    "SYMBOL_TRADE_EXECUTION_INSTANT": 1,
    "SYMBOL_TRADE_EXECUTION_MARKET": 2,
    "SYMBOL_TRADE_EXECUTION_REQUEST": 0,
    "SYMBOL_TRADE_MODE_CLOSEONLY": 3,
    "SYMBOL_TRADE_MODE_DISABLED": 0,
    "SYMBOL_TRADE_MODE_FULL": 4,
    "SYMBOL_TRADE_MODE_LONGONLY": 1,
    "SYMBOL_TRADE_MODE_SHORTONLY": 2,
    "TICK_FLAG_ASK": 4,
    "TICK_FLAG_BID": 2,
    "TICK_FLAG_BUY": 32,
    "TICK_FLAG_LAST": 8,
    "TICK_FLAG_SELL": 64,
    "TICK_FLAG_VOLUME": 16,
    "TIMEFRAME_D1": 16408,
    "TIMEFRAME_H1": 16385,
    "TIMEFRAME_H12": 16396,
    "TIMEFRAME_H2": 16386,
    "TIMEFRAME_H3": 16387,
    "TIMEFRAME_H4": 16388,
    "TIMEFRAME_H6": 16390,
    "TIMEFRAME_H8": 16392,
    "TIMEFRAME_M1": 1,
    "TIMEFRAME_M10": 10,
    "TIMEFRAME_M12": 12,
    "TIMEFRAME_M15": 15,
    "TIMEFRAME_M2": 2,
    "TIMEFRAME_M20": 20,
    "TIMEFRAME_M3": 3,
    "TIMEFRAME_M30": 30,
    "TIMEFRAME_M4": 4,
    "TIMEFRAME_M5": 5,
    "TIMEFRAME_M6": 6,
    "TIMEFRAME_MN1": 49153,
    "TIMEFRAME_W1": 32769,
    "TRADE_ACTION_CLOSE_BY": 10,
    "TRADE_ACTION_DEAL": 1,
    "TRADE_ACTION_MODIFY": 7,
    "TRADE_ACTION_PENDING": 5,
    "TRADE_ACTION_REMOVE": 8,
    "TRADE_ACTION_SLTP": 6,
    "TRADE_RETCODE_CANCEL": 10007,
    "TRADE_RETCODE_CLIENT_DISABLES_AT": 10027,
    "TRADE_RETCODE_CLOSE_ONLY": 10044,
    "TRADE_RETCODE_CLOSE_ORDER_EXIST": 10039,
    "TRADE_RETCODE_CONNECTION": 10031,
    "TRADE_RETCODE_DONE": 10009,
    "TRADE_RETCODE_DONE_PARTIAL": 10010,
    "TRADE_RETCODE_ERROR": 10011,
    "TRADE_RETCODE_FIFO_CLOSE": 10045,
    "TRADE_RETCODE_FROZEN": 10029,
    "TRADE_RETCODE_INVALID": 10013,
    "TRADE_RETCODE_INVALID_CLOSE_VOLUME": 10038,
    "TRADE_RETCODE_INVALID_EXPIRATION": 10022,
    "TRADE_RETCODE_INVALID_FILL": 10030,
    "TRADE_RETCODE_INVALID_ORDER": 10035,
    "TRADE_RETCODE_INVALID_PRICE": 10015,
    "TRADE_RETCODE_INVALID_STOPS": 10016,
    "TRADE_RETCODE_INVALID_VOLUME": 10014,
    "TRADE_RETCODE_LIMIT_ORDERS": 10033,
    "TRADE_RETCODE_LIMIT_POSITIONS": 10040,
    "TRADE_RETCODE_LIMIT_VOLUME": 10034,
    "TRADE_RETCODE_LOCKED": 10028,
    "TRADE_RETCODE_LONG_ONLY": 10042,
    "TRADE_RETCODE_MARKET_CLOSED": 10018,
    "TRADE_RETCODE_NO_CHANGES": 10025,
    "TRADE_RETCODE_NO_MONEY": 10019,
    "TRADE_RETCODE_ONLY_REAL": 10032,
    "TRADE_RETCODE_ORDER_CHANGED": 10023,
    "TRADE_RETCODE_PLACED": 10008,
    "TRADE_RETCODE_POSITION_CLOSED": 10036,
    "TRADE_RETCODE_PRICE_CHANGED": 10020,
    "TRADE_RETCODE_PRICE_OFF": 10021,
    "TRADE_RETCODE_REJECT": 10006,
    "TRADE_RETCODE_REJECT_CANCEL": 10041,
    "TRADE_RETCODE_REQUOTE": 10004,
    "TRADE_RETCODE_SERVER_DISABLES_AT": 10026,
    "TRADE_RETCODE_SHORT_ONLY": 10043,
    "TRADE_RETCODE_TIMEOUT": 10012,
    "TRADE_RETCODE_TOO_MANY_REQUESTS": 10024,
    "TRADE_RETCODE_TRADE_DISABLED": 10017,
}


def is_native_mt5_available() -> bool:
    """Mengecek apakah paket resmi MetaTrader5 native Windows tersedia dan dapat diimpor."""
    if sys.platform != "win32":
        return False
    try:
        import MetaTrader5  # type: ignore # noqa: F401
        return True
    except (ImportError, Exception):
        return False


def is_mt5linux_available() -> bool:
    """Mengecek apakah paket RPC bridge (rpyc, pymt5linux, atau mt5linux) tersedia."""
    try:
        import rpyc  # type: ignore # noqa: F401
        return True
    except (ImportError, SyntaxError, Exception):
        pass

    try:
        import pymt5linux  # type: ignore # noqa: F401
        return True
    except (ImportError, SyntaxError, Exception):
        pass

    try:
        import mt5linux  # type: ignore # noqa: F401
        return True
    except (ImportError, SyntaxError, Exception):
        return False


class MT5BridgeProxy:
    """
    Proxy adaptor untuk jembatan RPyC / pymt5linux / mt5linux RPC.
    Meneruskan panggilan metode ke terminal MT5 yang berjalan di Wine/Windows
    serta menyediakan konstanta resmi MT5.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or os.getenv("MT5_LINUX_HOST", "127.0.0.1")
        self.port = int(port or os.getenv("MT5_LINUX_PORT", "18812"))
        self._bridge_client: Optional[Any] = None
        self._is_connected: bool = False
        self._last_error: Tuple[int, str] = (1, "Success")
        self.__version__ = "5.0.45-linux-bridge"
        self.__author__ = "Monika MT5 Linux Bridge Adapter"

    def _ensure_client(self) -> Any:
        """Membuat instance jembatan RPyC / pymt5linux / mt5linux jika belum tersedia."""
        if self._bridge_client is not None:
            return self._bridge_client

        # 1. Direct RPyC classic client (universal, zero external quirks)
        try:
            import rpyc
            conn = rpyc.classic.connect(self.host, self.port)
            self._bridge_client = conn.modules.MetaTrader5
            logger.info(f"[MT5Bridge] Connected via direct RPyC MetaTrader5 proxy -> {self.host}:{self.port}")
            return self._bridge_client
        except Exception:
            pass

        # 2. Try pymt5linux (modern, maintained)
        try:
            from pymt5linux import MetaTrader5 as PyMT5LinuxBridge
            self._bridge_client = PyMT5LinuxBridge(host=self.host, port=self.port)
            logger.info(f"[MT5Bridge] Initialized pymt5linux client -> {self.host}:{self.port}")
            return self._bridge_client
        except (ImportError, SyntaxError, Exception):
            pass

        # 3. Try mt5linux (legacy)
        try:
            from mt5linux import MetaTrader5 as MT5LinuxBridge
            self._bridge_client = MT5LinuxBridge(host=self.host, port=self.port)
            logger.info(f"[MT5Bridge] Initialized mt5linux client -> {self.host}:{self.port}")
            return self._bridge_client
        except (ImportError, SyntaxError, Exception):
            pass

        msg = (
            f"Unable to connect to MT5 RPC Bridge at {self.host}:{self.port}. "
            "Ensure MT5 terminal and mt5server (or RPyC server) are running on the target host/container."
        )
        logger.error(f"[MT5Bridge] {msg}")
        raise ConnectionError(msg)

    def initialize(self, path: Optional[str] = None, **kwargs) -> bool:
        """
        Inisialisasi koneksi ke MetaTrader 5 melalui RPC bridge.
        Di Linux, jika path yang diberikan tidak ada di sistem Linux lokal (misalnya path Wine C:/...),
        path akan dilepas agar MT5 terhubung langsung ke terminal yang sedang berjalan.
        """
        try:
            client = self._ensure_client()
            init_kwargs = dict(kwargs)
            if path:
                if os.path.exists(path) or sys.platform == "win32":
                    init_kwargs["path"] = path
                else:
                    logger.debug(f"[MT5Bridge] Stripped non-existent host path '{path}' for Wine initialization.")

            result = client.initialize(**init_kwargs)
            self._is_connected = bool(result)
            if not self._is_connected:
                self._last_error = getattr(client, "last_error", lambda: (-1, "Bridge init failed"))()
            return self._is_connected
        except Exception as e:
            logger.error(f"[MT5Bridge] Connection to MT5 server {self.host}:{self.port} failed: {e}")
            self._is_connected = False
            self._last_error = (-10004, str(e))
            return False

    def login(self, login: int, password: str = "", server: str = "", **kwargs) -> bool:
        """Otentikasi ke broker MT5 melalui RPC bridge."""
        try:
            client = self._ensure_client()
            res = client.login(login=int(login), password=password, server=server, **kwargs)
            self._is_connected = bool(res)
            return self._is_connected
        except Exception as e:
            logger.error(f"[MT5Bridge] Login error: {e}")
            self._last_error = (-1, str(e))
            return False

    def shutdown(self) -> None:
        """Memutuskan koneksi MT5 RPC."""
        if self._bridge_client:
            try:
                self._bridge_client.shutdown()
            except Exception as e:
                logger.debug(f"[MT5Bridge] Shutdown exception (ignored): {e}")
        self._is_connected = False

    def last_error(self) -> Tuple[int, str]:
        """Mengembalikan kode error terakhir."""
        if self._is_connected and self._bridge_client:
            try:
                err = self._bridge_client.last_error()
                if isinstance(err, (tuple, list)) and len(err) >= 2:
                    return (int(err[0]), str(err[1]))
            except Exception:
                pass
        return self._last_error

    def __getattr__(self, name: str) -> Any:
        # 1. First check if it's a standard MT5 constant
        if name in MT5_CONSTANTS:
            return MT5_CONSTANTS[name]

        # 2. Forward method call to remote bridge client
        if self._bridge_client is not None:
            try:
                return getattr(self._bridge_client, name)
            except AttributeError:
                pass

        # If client not initialized yet, try initializing and getting attribute
        try:
            client = self._ensure_client()
            return getattr(client, name)
        except Exception:
            raise AttributeError(f"MetaTrader5 object has no attribute '{name}'")


class MT5FallbackModule:
    """
    Modul fallback yang digunakan ketika MT5 native maupun bridge RPC belum/tidak terhubung.
    Menyediakan seluruh konstanta MT5 resmi agar impor dan evaluasi statis tidak crash.
    """

    def __init__(self):
        self.__version__ = "5.0.45-fallback"
        self.__author__ = "Monika MT5 Fallback"

    def initialize(self, *args, **kwargs) -> bool:
        logger.warning(
            "[MT5Fallback] MetaTrader5 is not connected natively or via mt5linux bridge. "
            "Running in simulation / fallback mode."
        )
        return False

    def login(self, *args, **kwargs) -> bool:
        return False

    def shutdown(self) -> None:
        pass

    def last_error(self) -> Tuple[int, str]:
        return (-1, "MT5 library not available on this platform. Use mt5linux for Linux VPS.")

    def account_info(self) -> Optional[Any]:
        return None

    def terminal_info(self) -> Optional[Any]:
        return None

    def symbol_info(self, symbol: str) -> Optional[Any]:
        return None

    def symbol_info_tick(self, symbol: str) -> Optional[Any]:
        return None

    def positions_get(self, *args, **kwargs) -> Optional[tuple]:
        return ()

    def orders_get(self, *args, **kwargs) -> Optional[tuple]:
        return ()

    def history_deals_get(self, *args, **kwargs) -> Optional[tuple]:
        return ()

    def history_orders_get(self, *args, **kwargs) -> Optional[tuple]:
        return ()

    def copy_rates_from_pos(self, *args, **kwargs) -> Optional[Any]:
        return None

    def copy_rates_range(self, *args, **kwargs) -> Optional[Any]:
        return None

    def order_send(self, *args, **kwargs) -> Optional[Any]:
        return None

    def market_book_add(self, symbol: str) -> bool:
        return False

    def market_book_get(self, symbol: str) -> Optional[Any]:
        return None

    def market_book_release(self, symbol: str) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:
        if name in MT5_CONSTANTS:
            return MT5_CONSTANTS[name]
        raise AttributeError(f"MetaTrader5 (Fallback) has no attribute '{name}'")


_active_mt5_module: Optional[Any] = None


def get_mt5_module(host: Optional[str] = None, port: Optional[int] = None) -> Any:
    """
    Mengembalikan instance atau modul MetaTrader5 yang tepat sesuai lingkungan runtime:
      - Windows: native MetaTrader5 module
      - Linux / Bridge: MT5BridgeProxy (menggunakan mt5linux)
      - Fallback: MT5FallbackModule
    """
    global _active_mt5_module
    if _active_mt5_module is not None:
        return _active_mt5_module

    # 1. Native Windows
    if is_native_mt5_available():
        try:
            import MetaTrader5 as native_mt5  # type: ignore
            _active_mt5_module = native_mt5
            logger.info("[MT5Compat] Using native MetaTrader5 C-extension on Windows.")
            return _active_mt5_module
        except Exception as e:
            logger.warning(f"[MT5Compat] Failed to load native MetaTrader5: {e}")

    # 2. Linux VPS Bridge (mt5linux)
    if is_mt5linux_available():
        _active_mt5_module = MT5BridgeProxy(host=host, port=port)
        logger.info(f"[MT5Compat] Using mt5linux RPC bridge proxy ({_active_mt5_module.host}:{_active_mt5_module.port}).")
        return _active_mt5_module

    # 3. Fallback Module
    _active_mt5_module = MT5FallbackModule()
    logger.info("[MT5Compat] Native MetaTrader5 and mt5linux unavailable. Using MT5FallbackModule.")
    return _active_mt5_module


def ensure_mt5_module(host: Optional[str] = None, port: Optional[int] = None) -> Any:
    """
    Memastikan modul `MetaTrader5` terdaftar di `sys.modules`.
    Jika belum ada, daftarkan modul/proxy yang sesuai ke `sys.modules['MetaTrader5']`.
    """
    if "MetaTrader5" in sys.modules and sys.modules["MetaTrader5"] is not None:
        return sys.modules["MetaTrader5"]

    mt5_inst = get_mt5_module(host=host, port=port)

    # Wrap proxy or fallback into a standard Python module if needed
    if not isinstance(mt5_inst, types.ModuleType):
        mod = types.ModuleType("MetaTrader5", "MetaTrader 5 Cross-Platform Compatibility Layer")
        for k, v in MT5_CONSTANTS.items():
            setattr(mod, k, v)
        for attr in dir(mt5_inst):
            if not attr.startswith("__"):
                setattr(mod, attr, getattr(mt5_inst, attr))
        # Ensure __getattr__ delegates dynamically
        mod.__getattr__ = mt5_inst.__getattr__  # type: ignore
        sys.modules["MetaTrader5"] = mod
        return mod

    sys.modules["MetaTrader5"] = mt5_inst
    return mt5_inst
