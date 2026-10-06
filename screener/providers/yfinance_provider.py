"""yfinance による株価・財務データ取得（APIキー不要）。"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

from .base import PRICE_COLUMNS, Fundamentals, FundamentalsProvider, PriceProvider

log = logging.getLogger(__name__)

CHUNK = 50  # 一括ダウンロードの銘柄数


def to_yahoo_symbol(code: str, market: str) -> str:
    """内部コード → Yahoo Finance のシンボル。"""
    if market == "JP":
        return f"{code}.T"
    return code.replace(".", "-")  # BRK.B → BRK-B


class YFinancePriceProvider(PriceProvider):
    name = "yfinance"

    def __init__(self, market: str):
        self.market = market

    def get_history(self, codes: Iterable[str], lookback_days: int) -> dict[str, pd.DataFrame]:
        import yfinance as yf

        codes = list(codes)
        start = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        out: dict[str, pd.DataFrame] = {}
        for i in range(0, len(codes), CHUNK):
            chunk = codes[i:i + CHUNK]
            sym2code = {to_yahoo_symbol(c, self.market): c for c in chunk}
            data = None
            for attempt in range(3):
                try:
                    data = yf.download(
                        list(sym2code), start=start, auto_adjust=True, group_by="ticker",
                        threads=True, progress=False,
                    )
                    break
                except Exception as e:  # noqa: BLE001
                    log.warning("download failed (attempt %d): %s", attempt + 1, e)
                    time.sleep(5 * (attempt + 1))
            if data is None or data.empty:
                continue
            for sym, code in sym2code.items():
                try:
                    df = data[sym] if isinstance(data.columns, pd.MultiIndex) else data
                except KeyError:
                    continue
                df = df[[c for c in PRICE_COLUMNS if c in df.columns]].dropna(subset=["Close"])
                if len(df) == 0:
                    continue
                df.index = pd.to_datetime(df.index).tz_localize(None)
                out[code] = df.sort_index()
        log.info("price: %d/%d symbols fetched", len(out), len(codes))
        return out


# yfinance の財務諸表の行名（上から優先）
_ROWS = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported", "EBIT"],
    "net_income": ["Net Income Common Stockholders", "Net Income",
                   "Net Income From Continuing Operation Net Minority Interest"],
    "operating_cf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "total_assets": ["Total Assets"],
    "equity": ["Stockholders Equity", "Common Stock Equity",
               "Total Equity Gross Minority Interest"],
}


def _clean(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _row(df: pd.DataFrame, names: list[str], cols: list) -> list[float | None]:
    for n in names:
        if df is not None and n in df.index:
            s = df.loc[n]
            return [_clean(s.get(c)) for c in cols]
    return [None] * len(cols)


class YFinanceFundamentalsProvider(FundamentalsProvider):
    name = "yfinance"

    def __init__(self, market: str, pause: float = 0.3):
        self.market = market
        self.pause = pause

    def get_fundamentals(self, code: str) -> Fundamentals:
        import yfinance as yf

        t = yf.Ticker(to_yahoo_symbol(code, self.market))
        for attempt in range(3):
            try:
                inc, bal, cf = t.income_stmt, t.balance_sheet, t.cashflow
                break
            except Exception as e:  # noqa: BLE001
                log.warning("%s fundamentals failed (attempt %d): %s", code, attempt + 1, e)
                time.sleep(3 * (attempt + 1))
        else:
            return Fundamentals(code=code, source=self.name)
        time.sleep(self.pause)
        if inc is None or inc.empty:
            return Fundamentals(code=code, source=self.name)

        # 損益計算書の期（全NaN列は除外）を基準に、新しい順に揃える
        inc = inc.dropna(axis=1, how="all")
        cols = sorted(inc.columns, reverse=True)
        f = Fundamentals(code=code, source=self.name,
                         fiscal_years=[pd.Timestamp(c).strftime("%Y-%m-%d") for c in cols])
        f.revenue = _row(inc, _ROWS["revenue"], cols)
        f.operating_income = _row(inc, _ROWS["operating_income"], cols)
        f.net_income = _row(inc, _ROWS["net_income"], cols)
        f.operating_cf = _row(cf, _ROWS["operating_cf"], cols)
        f.total_assets = _row(bal, _ROWS["total_assets"], cols)
        f.equity = _row(bal, _ROWS["equity"], cols)
        return f
