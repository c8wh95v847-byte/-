"""J-Quants API 用の株価プロバイダ（差し替え用の雛形）。

使い方（実装時）:
  1. GitHub Secrets に JQUANTS_REFRESH_TOKEN（または API キー）を登録
  2. 日足四本値エンドポイントから取得し、列を PRICE_COLUMNS に合わせて返す
     （調整後価格 AdjustmentOpen/High/Low/Close/Volume を使うと分割の影響を受けない）
  3. config.yaml の markets.JP.providers.price を jquants に変更
"""
from __future__ import annotations

import os
from typing import Iterable

import pandas as pd

from .base import PriceProvider


class JQuantsPriceProvider(PriceProvider):
    name = "jquants"

    def __init__(self, market: str):
        if market != "JP":
            raise ValueError("J-Quants は日本株専用です")
        self.token = os.environ.get("JQUANTS_REFRESH_TOKEN")

    def get_history(self, codes: Iterable[str], lookback_days: int) -> dict[str, pd.DataFrame]:
        raise NotImplementedError(
            "J-Quants プロバイダは未実装です。providers/jquants.py の docstring を参照してください。")
