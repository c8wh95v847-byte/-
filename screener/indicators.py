"""テクニカル指標。すべて終値ベースの pandas Series を返す。"""
from __future__ import annotations

import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder の RSI。"""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0)


def volume_ratio(volume: pd.Series, avg_period: int = 20) -> pd.Series:
    """当日出来高 / 前日までの N 日平均出来高。"""
    avg = volume.shift(1).rolling(avg_period, min_periods=avg_period).mean()
    return volume / avg


def prior_high(high: pd.Series, lookback: int) -> pd.Series:
    """前日までの N 日間の高値（当日を含まない）。"""
    return high.shift(1).rolling(lookback, min_periods=lookback).max()
