"""SEC EDGAR（XBRL companyfacts API）による米国株の財務プロバイダ。APIキー不要。

SEC は連絡先入りの User-Agent を要求するため、環境変数 SEC_USER_AGENT
（例: "my-screener you@example.com"）を設定して使う。
config.yaml の markets.US.providers.fundamentals を edgar に変更すると有効になる。
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from .base import Fundamentals, FundamentalsProvider

_TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "operating_cf": ["NetCashProvidedByUsedInOperatingActivities"],
    "total_assets": ["Assets"],
    "equity": ["StockholdersEquity"],
}


class EdgarFundamentalsProvider(FundamentalsProvider):
    name = "edgar"

    def __init__(self, market: str, years: int = 4):
        if market != "US":
            raise ValueError("EDGAR は米国株専用です")
        self.ua = os.environ.get("SEC_USER_AGENT", "stock-screener admin@example.com")
        self.years = years
        self._cik: dict[str, int] | None = None

    def _get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": self.ua})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        time.sleep(0.15)  # SEC のレート制限（10 req/s）に配慮
        return data

    def _cik_of(self, code: str) -> int | None:
        if self._cik is None:
            data = self._get("https://www.sec.gov/files/company_tickers.json")
            self._cik = {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}
        return self._cik.get(code.upper().replace(".", "-"))

    def get_fundamentals(self, code: str) -> Fundamentals:
        cik = self._cik_of(code)
        if cik is None:
            return Fundamentals(code=code, source=self.name)
        facts = self._get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        gaap = facts.get("facts", {}).get("us-gaap", {})

        series: dict[str, dict[str, float]] = {}
        for key, tags in _TAGS.items():
            vals: dict[str, float] = {}
            for tag in tags:
                for unit in gaap.get(tag, {}).get("units", {}).values():
                    for e in unit:
                        # 年次（10-K、通期）の値のみ
                        if e.get("form") == "10-K" and e.get("fp") == "FY" and e.get("end"):
                            vals.setdefault(e["end"], e["val"])
                if vals:
                    break
            series[key] = vals

        ends = sorted(series["revenue"] or series["net_income"], reverse=True)[: self.years]
        f = Fundamentals(code=code, fiscal_years=ends, source=self.name)
        for key in _TAGS:
            setattr(f, key, [series[key].get(e) for e in ends])
        return f
