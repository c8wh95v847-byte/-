"""データ取得層のインターフェース。

スクリーニング側はここで定義した型だけに依存するので、
yfinance → J-Quants / EDINET / SEC EDGAR などへ差し替えても他のコードは変わらない。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Iterable

import pandas as pd

# 株価 DataFrame の列（DatetimeIndex 昇順）
PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


@dataclass
class Fundamentals:
    """年次財務データ。各リストは新しい期 → 古い期の順（index 0 = 直近期）。

    値が取れない期は None。単位は各市場の通貨（円 / ドル）。
    """

    code: str
    fiscal_years: list[str] = field(default_factory=list)   # 例: "2025-03-31"
    revenue: list[float | None] = field(default_factory=list)
    operating_income: list[float | None] = field(default_factory=list)
    net_income: list[float | None] = field(default_factory=list)
    operating_cf: list[float | None] = field(default_factory=list)
    total_assets: list[float | None] = field(default_factory=list)
    equity: list[float | None] = field(default_factory=list)  # 株主資本（親会社株主に帰属）
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Fundamentals":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})

    @property
    def is_empty(self) -> bool:
        return not self.fiscal_years


class PriceProvider(ABC):
    """日足株価の取得元。"""

    name: str = "base"

    @abstractmethod
    def get_history(self, codes: Iterable[str], lookback_days: int) -> dict[str, pd.DataFrame]:
        """銘柄コード → 日足 DataFrame（列は PRICE_COLUMNS、DatetimeIndex 昇順）。

        取得できなかった銘柄は結果に含めない。
        """


class FundamentalsProvider(ABC):
    """年次財務データの取得元。"""

    name: str = "base"

    @abstractmethod
    def get_fundamentals(self, code: str) -> Fundamentals:
        """1銘柄分の年次財務データ。取得できなければ空の Fundamentals を返す。"""
