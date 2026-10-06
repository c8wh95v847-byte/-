"""CLI: python -m screener --market JP [--limit 10] [--provider fake] [--out docs]"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import ROOT, load_config
from .pipeline import run_market
from .report import write_index, write_market


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="screener", description="日本株・米国株スクリーナー")
    ap.add_argument("--market", action="append", choices=["JP", "US"],
                    help="対象市場（複数指定可。省略時は config.yaml の enabled_markets）")
    ap.add_argument("--limit", type=int, help="銘柄数の上限（config の limit を上書き）")
    ap.add_argument("--provider", help="価格・財務の両方をこのプロバイダで上書き（例: fake）")
    ap.add_argument("--out", help="出力ディレクトリ（既定: config の output.dir）")
    ap.add_argument("--no-cache", action="store_true", help="財務キャッシュを使わない")
    ap.add_argument("--config", help="設定ファイルのパス")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    cfg = load_config(a.config)
    out = ROOT / (a.out or cfg["output"]["dir"])
    failed = []
    for m in a.market or cfg["enabled_markets"]:
        try:
            r, prices = run_market(cfg, m, limit=a.limit, provider_override=a.provider,
                                   use_cache=not a.no_cache and not a.provider)
            write_market(cfg, r, prices, out)
        except Exception:
            logging.exception("[%s] failed", m)
            failed.append(m)
    write_index(cfg, out)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
