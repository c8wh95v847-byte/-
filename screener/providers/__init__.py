"""プロバイダのレジストリ。config.yaml の providers.price / providers.fundamentals の名前で選ぶ。"""
from __future__ import annotations

from .base import Fundamentals, FundamentalsProvider, PriceProvider


def make_price_provider(name: str, market: str) -> PriceProvider:
    if name == "yfinance":
        from .yfinance_provider import YFinancePriceProvider
        return YFinancePriceProvider(market)
    if name == "fake":
        from .fake import FakePriceProvider
        return FakePriceProvider(market)
    if name == "jquants":
        from .jquants import JQuantsPriceProvider
        return JQuantsPriceProvider(market)
    raise ValueError(f"unknown price provider: {name}")


def make_fundamentals_provider(name: str, market: str) -> FundamentalsProvider:
    if name == "yfinance":
        from .yfinance_provider import YFinanceFundamentalsProvider
        return YFinanceFundamentalsProvider(market)
    if name == "fake":
        from .fake import FakeFundamentalsProvider
        return FakeFundamentalsProvider(market)
    if name == "edinet":
        from .edinet import EdinetFundamentalsProvider
        return EdinetFundamentalsProvider(market)
    if name == "edgar":
        from .edgar import EdgarFundamentalsProvider
        return EdgarFundamentalsProvider(market)
    raise ValueError(f"unknown fundamentals provider: {name}")


__all__ = [
    "Fundamentals", "FundamentalsProvider", "PriceProvider",
    "make_price_provider", "make_fundamentals_provider",
]
