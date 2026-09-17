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
        
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = (df['High'] - df['Low']).abs()
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        return true_range.rolling(window=period).mean()

    def _calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series:
        return df['Close'].ewm(span=period, adjust=False).mean()
        
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
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
        """
        if df.empty or len(df) < 200:
            logger.warning("DataFrame is too small for accurate signal generation")
            df['Signal'] = 0
            df['ConfluenceScore'] = 0
            return df
            
        df = df.copy()
        
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
        
        # Confluence Score (simulated vectorized version)
        # 1. Trend Alignment (3 pts)
        # 2. RSI Pullback (2 pts)
        
        # Buy signals
        buy_cond = df['Trend_Up'] & (df['RSI'] < 40)
        
        # Sell signals
        sell_cond = df['Trend_Down'] & (df['RSI'] > 60)
        
        df['Signal'] = 0
        df.loc[buy_cond, 'Signal'] = 1
        df.loc[sell_cond, 'Signal'] = -1
        
        df['ConfluenceScore'] = 0
        df.loc[buy_cond, 'ConfluenceScore'] = 5  # Base score for this basic offline engine
        df.loc[sell_cond, 'ConfluenceScore'] = 5
        
        # Clean up temporary columns
        cols_to_drop = ['Trend_Up', 'Trend_Down', 'RSI_Oversold', 'RSI_Overbought']
        df = df.drop(columns=cols_to_drop)
        
        return df

    def calculate_stops_and_targets(self, df: pd.DataFrame, risk_reward_ratio: float = 2.0) -> pd.DataFrame:
        """
        Calculates Stop Loss and Take Profit levels for generated signals using ATR.
        """
        df = df.copy()
        
        # For Buy (Signal == 1)
        buy_mask = df['Signal'] == 1
        df.loc[buy_mask, 'StopLoss'] = df.loc[buy_mask, 'Close'] - (df.loc[buy_mask, 'ATR'] * 1.5)
        df.loc[buy_mask, 'TakeProfit'] = df.loc[buy_mask, 'Close'] + (df.loc[buy_mask, 'ATR'] * 1.5 * risk_reward_ratio)
        
        # For Sell (Signal == -1)
        sell_mask = df['Signal'] == -1
        df.loc[sell_mask, 'StopLoss'] = df.loc[sell_mask, 'Close'] + (df.loc[sell_mask, 'ATR'] * 1.5)
        df.loc[sell_mask, 'TakeProfit'] = df.loc[sell_mask, 'Close'] - (df.loc[sell_mask, 'ATR'] * 1.5 * risk_reward_ratio)
        
        # Hold (Signal == 0)
        hold_mask = df['Signal'] == 0
        df.loc[hold_mask, 'StopLoss'] = 0
        df.loc[hold_mask, 'TakeProfit'] = 0
        
        return df
