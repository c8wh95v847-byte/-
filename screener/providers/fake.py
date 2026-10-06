"""オフライン用のダミーデータ（テスト・ネットワーク不通時の動作確認用）。

銘柄コードから決まる乱数シードで生成するため、毎回同じ結果になる。
"""
from __future__ import annotations

import hashlib
from typing import Iterable

import numpy as np
import pandas as pd

from .base import Fundamentals, FundamentalsProvider, PriceProvider


def _rng(code: str, salt: str = "") -> np.random.Generator:
    seed = int(hashlib.sha256(f"{code}{salt}".encode()).hexdigest()[:8], 16)
    return np.random.default_rng(seed)


class FakePriceProvider(PriceProvider):
    name = "fake"

    def __init__(self, market: str, end: str | None = None):
        self.market = market
        self.end = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()

    def get_history(self, codes: Iterable[str], lookback_days: int) -> dict[str, pd.DataFrame]:
        out = {}
        idx = pd.bdate_range(end=self.end, periods=int(lookback_days * 5 / 7))
        for code in codes:
            r = _rng(code)
            n = len(idx)
            drift = r.normal(0.0006, 0.0015)
            ret = r.normal(drift, 0.018, n)
            # 終盤に上昇＋出来高増の銘柄を混ぜる
            if r.random() < 0.4:
                ret[-15:] += 0.006
            base = 3000 if self.market == "JP" else 150
            close = base * np.exp(np.cumsum(ret))
            high = close * (1 + np.abs(r.normal(0, 0.008, n)))
            low = close * (1 - np.abs(r.normal(0, 0.008, n)))
            open_ = (high + low) / 2
            vol = r.lognormal(14 if self.market == "JP" else 15, 0.3, n)
            if r.random() < 0.5:
                vol[-1] *= 2.2
            out[code] = pd.DataFrame(
                {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=idx)
        return out


class FakeFundamentalsProvider(FundamentalsProvider):
    name = "fake"

    def __init__(self, market: str):
        self.market = market

    def get_fundamentals(self, code: str) -> Fundamentals:
        r = _rng(code, "fund")
        years = ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"]
        g = r.normal(0.06, 0.08)
        rev0 = r.uniform(1e11, 5e12)
        revenue = [rev0 / (1 + g + r.normal(0, 0.03)) ** i for i in range(4)]
        margin = r.uniform(0.03, 0.2)
        op = [x * (margin + r.normal(0, 0.01)) for x in revenue]
        ni = [x * 0.65 for x in op]
        ocf = [x * r.uniform(0.6, 1.6) * (1 if r.random() > 0.1 else -1) for x in ni]
        assets = [x * r.uniform(1.0, 2.0) for x in revenue]
        eq = [a * r.uniform(0.2, 0.7) for a in assets]
        return Fundamentals(code=code, fiscal_years=years, revenue=revenue, operating_income=op,
                            net_income=ni, operating_cf=ocf, total_assets=assets, equity=eq,
                            source=self.name)
