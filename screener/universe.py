"""対象銘柄（ユニバース）の読み込みと更新。

data/universe/*.csv（列: code,name）を正とし、`python -m screener.universe` で
最新の構成銘柄に更新する（失敗したら既存ファイルを維持）。
"""
from __future__ import annotations

import csv
import re
import unicodedata
import io
import logging
import sys
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (compatible; stock-screener/0.1)"
SOURCES = {
    "US": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "JP": "https://indexes.nikkei.co.jp/nkave/index/component?idx=nk225",
}


def clean_name(name: str) -> str:
    """全角英数を半角に、「（株）」などの法人格表記を除去。"""
    name = unicodedata.normalize("NFKC", str(name)).strip()
    name = re.sub(r"\((株|有|合)\)|株式会社", "", name)
    return re.sub(r"\s+", " ", name).strip()


def load_universe(path: str | Path, limit: int | None = None) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        rows = [{**r, "name": clean_name(r.get("name", ""))} for r in csv.DictReader(f) if r.get("code")]
    return rows[:limit] if limit else rows


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_sp500() -> list[dict]:
    import pandas as pd

    tables = pd.read_html(io.StringIO(_fetch(SOURCES["US"])), attrs={"id": "constituents"})
    df = tables[0]
    return [{"code": str(s).strip(), "name": str(n).strip()}
            for s, n in zip(df["Symbol"], df["Security"])]


def fetch_nikkei225() -> list[dict]:
    import pandas as pd

    rows = []
    for t in pd.read_html(io.StringIO(_fetch(SOURCES["JP"]))):
        cols = [str(c) for c in t.columns]
        code_col = next((c for c in cols if "コード" in c or "Code" in c), None)
        name_col = next((c for c in cols if "社名" in c or "Company" in c), None) \
            or next((c for c in cols if "銘柄" in c), None)
        if not code_col or not name_col:
            continue
        for code, name in zip(t[code_col], t[name_col]):
            code = str(code).strip().split(".")[0]
            if len(code) == 4:
                rows.append({"code": code, "name": clean_name(name)})
    return rows


def refresh(market: str, path: str | Path, min_count: int) -> bool:
    try:
        rows = fetch_sp500() if market == "US" else fetch_nikkei225()
    except Exception as e:  # noqa: BLE001
        log.warning("%s universe refresh failed: %s", market, e)
        return False
    seen, uniq = set(), []
    for r in rows:
        if r["code"] not in seen:
            seen.add(r["code"])
            uniq.append(r)
    if len(uniq) < min_count:
        log.warning("%s universe refresh returned only %d rows; keeping existing file", market, len(uniq))
        return False
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "name"])
        w.writeheader()
        w.writerows(uniq)
    log.info("%s universe updated: %d symbols", market, len(uniq))
    return True


def main(argv: list[str] | None = None) -> int:
    from .config import load_config

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()
    markets = argv or sys.argv[1:] or cfg["enabled_markets"]
    for m in markets:
        refresh(m, cfg["markets"][m]["universe"], min_count=200 if m == "JP" else 450)
    return 0  # 更新失敗は致命的ではない


if __name__ == "__main__":
    raise SystemExit(main())
