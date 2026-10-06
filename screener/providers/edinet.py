"""EDINET（有価証券報告書 XBRL）用の財務プロバイダ（差し替え用の雛形）。

使い方（実装時）:
  1. GitHub Secrets に EDINET_API_KEY を登録
  2. 書類一覧 API で対象企業の有価証券報告書（docTypeCode=120）を探し、
     XBRL / CSV から売上高・営業利益・当期純利益・営業CF・総資産・株主資本を抽出
  3. Fundamentals（新しい期→古い期の順）に詰めて返す
  4. config.yaml の markets.JP.providers.fundamentals を edinet に変更
"""
from __future__ import annotations

import os

from .base import Fundamentals, FundamentalsProvider


class EdinetFundamentalsProvider(FundamentalsProvider):
    name = "edinet"

    def __init__(self, market: str):
        if market != "JP":
            raise ValueError("EDINET は日本株専用です")
        self.api_key = os.environ.get("EDINET_API_KEY")

    def get_fundamentals(self, code: str) -> Fundamentals:
        raise NotImplementedError(
            "EDINET プロバイダは未実装です。providers/edinet.py の docstring を参照してください。")
