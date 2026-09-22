import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class OfflineSignalEngine:
    """
    Vectorized version of structure.py and confluence_calculator.py
    using Pandas DataFrames for fast offline backtesting.
    Expects OHLCV data with DatetimeIndex.
    """
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        
    def _normalize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        col_map = {}
        for c in df.columns:
            c_lower = str(c).lower()
            if c_lower == 'open': col_map[c] = 'Open'
            elif c_lower == 'high': col_map[c] = 'High'
            elif c_lower == 'low': col_map[c] = 'Low'
            elif c_lower == 'close': col_map[c] = 'Close'
            elif c_lower == 'volume': col_map[c] = 'Volume'
        if col_map:
            df = df.rename(columns=col_map)
        return df

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        df = self._normalize_df(df)
        high_low = (df['High'] - df['Low']).abs()
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        return true_range.rolling(window=period).mean()

    def _calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series:
        df = self._normalize_df(df)
        return df['Close'].ewm(span=period, adjust=False).mean()
        
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        df = self._normalize_df(df)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generates buy/sell signals based on technical confluence.
        Adds columns: 'Signal' (1 for buy, -1 for sell, 0 for hold),
        'ConfluenceScore', 'ATR', 'EMA_50', 'EMA_200', 'RSI'
        Applies 1-bar shift to prevent look-ahead bias on signal generation.
        """
        if df.empty or len(df) < 200:
            logger.warning("DataFrame is too small for accurate signal generation")
            df = df.copy()
            df['Signal'] = 0
            df['ConfluenceScore'] = 0
            return df
            
        df = self._normalize_df(df)
        
        # Calculate indicators
        df['ATR'] = self._calculate_atr(df)
        df['EMA_50'] = self._calculate_ema(df, 50)
        df['EMA_200'] = self._calculate_ema(df, 200)
        df['RSI'] = self._calculate_rsi(df)
        
        # Trend condition
        df['Trend_Up'] = df['EMA_50'] > df['EMA_200']
        df['Trend_Down'] = df['EMA_50'] < df['EMA_200']
        
        # RSI conditions
        df['RSI_Oversold'] = df['RSI'] < 30
        df['RSI_Overbought'] = df['RSI'] > 70
        
        # Buy signals at bar close
        buy_cond = df['Trend_Up'] & (df['RSI'] < 40)
        
        # Sell signals at bar close
        sell_cond = df['Trend_Down'] & (df['RSI'] > 60)
        
        raw_signal = pd.Series(0, index=df.index, dtype=int)
        raw_signal.loc[buy_cond] = 1
        raw_signal.loc[sell_cond] = -1
        
        raw_confluence = pd.Series(0, index=df.index, dtype=int)
        raw_confluence.loc[buy_cond] = 5
        raw_confluence.loc[sell_cond] = 5

        # Suppress duplicate signals: once a signal fires, block same-direction for min_bars_between_signals bars
        min_bars_gap = self.settings.get('backtest', {}).get('min_bars_between_signals', 10)
        clean_signal = pd.Series(0, index=df.index, dtype=int)
        clean_confluence = pd.Series(0, index=df.index, dtype=int)
        cooldown = 0
        for i in range(len(raw_signal)):
            if cooldown > 0:
                cooldown -= 1
                continue
            if raw_signal.iloc[i] != 0:
                clean_signal.iloc[i] = raw_signal.iloc[i]
                clean_confluence.iloc[i] = raw_confluence.iloc[i]
                cooldown = min_bars_gap
        raw_signal = clean_signal
        raw_confluence = clean_confluence

        # Shift signals by 1 bar: signal on close of bar t is actionable at bar t+1 (no look-ahead)
        df['Signal'] = raw_signal.shift(1).fillna(0).astype(int)
        df['ConfluenceScore'] = raw_confluence.shift(1).fillna(0).astype(int)
        
        # Clean up temporary columns
        cols_to_drop = ['Trend_Up', 'Trend_Down', 'RSI_Oversold', 'RSI_Overbought']
        df = df.drop(columns=cols_to_drop)
        
        return df

    def calculate_stops_and_targets(self, df: pd.DataFrame, risk_reward_ratio: float = 2.0) -> pd.DataFrame:
        """
        Calculates Stop Loss and Take Profit levels for generated signals using ATR.
        Uses Open price of the execution bar (or Close fallback) to match shifted execution.
        """
        df = self._normalize_df(df)
        exec_price = df['Open'] if 'Open' in df.columns else df['Close']

        # Shift ATR by 1 bar to prevent look-ahead bias: at execution Open of bar t+1,
        # only ATR computed from bars <= t is available
        if 'ATR' in df.columns:
            df['ATR'] = df['ATR'].shift(1)
        
        # For Buy (Signal == 1)
        buy_mask = df['Signal'] == 1
        df.loc[buy_mask, 'StopLoss'] = exec_price[buy_mask] - (df.loc[buy_mask, 'ATR'] * 1.5)
        df.loc[buy_mask, 'TakeProfit'] = exec_price[buy_mask] + (df.loc[buy_mask, 'ATR'] * 1.5 * risk_reward_ratio)
        
        # For Sell (Signal == -1)
        sell_mask = df['Signal'] == -1
        df.loc[sell_mask, 'StopLoss'] = exec_price[sell_mask] + (df.loc[sell_mask, 'ATR'] * 1.5)
        df.loc[sell_mask, 'TakeProfit'] = exec_price[sell_mask] - (df.loc[sell_mask, 'ATR'] * 1.5 * risk_reward_ratio)
        
        # Hold (Signal == 0)
        hold_mask = df['Signal'] == 0
        df.loc[hold_mask, 'StopLoss'] = 0.0
        df.loc[hold_mask, 'TakeProfit'] = 0.0
        
        return df
