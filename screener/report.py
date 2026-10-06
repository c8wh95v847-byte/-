"""結果を docs/ に HTML と JSON で書き出す（GitHub Pages 用）。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .chart import build_chart
from .config import ROOT
from .screens import _compact

TEMPLATES = ROOT / "templates"
SHORT = {"JP": "🇯🇵 日本株", "US": "🇺🇸 米国株"}


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]),
                       trim_blocks=True, lstrip_blocks=True)


def _price_fmt(currency: str):
    def f(v):
        return f"¥{v:,.0f}" if currency == "JPY" else f"${v:,.2f}"
    return f


def _money_fmt(currency: str):
    def f(v):
        return ("¥" if currency == "JPY" else "$") + _compact(v)
    return f


def _criteria(r: dict, kind: str) -> dict:
    cfg = r["criteria"][kind]
    sample = next((s[kind]["checks"] for s in r["stocks"]), [])
    labels = {c["key"]: c["label"] for c in sample}
    return {"min_passed": cfg["min_passed"],
            "required": cfg.get("required", []),
            "required_labels": "・".join(labels.get(k, k) for k in cfg.get("required", [])),
            "lines": [f'{c["label"]}: {c["threshold"]}' for c in sample]}


def _fin_table(f: dict | None, currency: str) -> dict | None:
    if not f or not f.get("fiscal_years"):
        return None
    rows = [("売上高", "revenue"), ("営業利益", "operating_income"), ("純利益", "net_income"),
            ("営業CF", "operating_cf"), ("総資産", "total_assets"), ("自己資本", "equity")]
    return {"source": f.get("source", ""), "years": [y[:7] for y in f["fiscal_years"]],
            "rows": [(label, [_compact(v) for v in f.get(key) or []]) for label, key in rows]}


def _history_entry(r: dict, by_code: dict) -> dict:
    def pick(kind):
        return [{"code": c, "name": by_code[c]["name"], "close": by_code[c]["close"],
                 "passed": by_code[c][kind]["passed"], "total": by_code[c][kind]["total"],
                 "checks": by_code[c][kind]["checks"]} for c in r[kind]]
    return {"market": r["market"], "as_of": r["as_of"], "generated_at": r["generated_at"],
            "providers": r["providers"], "swing": pick("swing"), "long": pick("long")}


def write_market(cfg: dict, r: dict, prices: dict[str, pd.DataFrame], out_dir: Path) -> None:
    env = _env()
    m = r["market"]
    mdir = out_dir / m.lower()
    (mdir / "history").mkdir(parents=True, exist_ok=True)
    by_code = {s["code"]: s for s in r["stocks"]}
    cur = r["currency"]
    common = {"fmt_price": _price_fmt(cur), "fmt_money": _money_fmt(cur),
              "providers_note": f'株価 {r["providers"]["price"]} / 財務 {r["providers"]["fundamentals"]}'}
    nav = [{"market": k, "dir": k.lower(), "short": SHORT.get(k, k)} for k in cfg["markets"]]

    # JSON
    (mdir / "latest.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), "utf-8")
    entry = _history_entry(r, by_code)
    (mdir / "history" / f'{r["as_of"]}.json').write_text(json.dumps(entry, ensure_ascii=False, indent=1), "utf-8")

    # ランキング
    crit = {"swing": _criteria(r, "swing"), "long": _criteria(r, "long"),
            "turnover": _money_fmt(cur)(r["criteria"]["min_avg_turnover"])}
    html = env.get_template("market.html.j2").render(r=r, by_code=by_code, crit=crit, nav=nav, root="../", **common)
    (mdir / "index.html").write_text(html, "utf-8")

    # 銘柄ページ（候補銘柄のみ）
    sdir = mdir / "stocks"
    sdir.mkdir(exist_ok=True)
    days = cfg["output"].get("chart_days", 120)
    trend = r["criteria"]["swing"]["conditions"].get("trend", {})
    written = set()
    for code in dict.fromkeys(r["swing"] + r["long"]):
        s = by_code[code]
        chart = build_chart(prices[code], days, trend.get("short", 25), trend.get("long", 75))
        fname = f'{code.replace(".", "-")}.html'
        html = env.get_template("stock.html.j2").render(
            r=r, s=s, chart=chart, fin=_fin_table(s["long"]["fundamentals"], cur), root="../../", **common)
        (sdir / fname).write_text(html, "utf-8")
        written.add(fname)
    for p in sdir.glob("*.html"):
        if p.name not in written:
            p.unlink()

    # 履歴ページ
    items = []
    for p in sorted((mdir / "history").glob("????-??-??.json"), reverse=True)[: cfg["output"].get("history_days", 90)]:
        h = json.loads(p.read_text("utf-8"))
        items.append({"as_of": h["as_of"],
                      "swing": [f'{x["name"]}({x["code"]})' for x in h["swing"]],
                      "long": [f'{x["name"]}({x["code"]})' for x in h["long"]]})
    html = env.get_template("history.html.j2").render(market_name=r["market_name"], items=items, root="../", **common)
    (mdir / "history.html").write_text(html, "utf-8")


def write_index(cfg: dict, out_dir: Path) -> None:
    """トップページ（各市場の最新サマリー）と共通アセット。"""
    env = _env()
    adir = out_dir / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    for p in (TEMPLATES / "assets").iterdir():
        shutil.copy(p, adir / p.name)
    (out_dir / ".nojekyll").touch()
    markets = []
    for m in cfg["markets"]:
        p = out_dir / m.lower() / "latest.json"
        if p.exists():
            r = json.loads(p.read_text("utf-8"))
            markets.append({"dir": m.lower(), "market_name": r["market_name"], "as_of": r["as_of"],
                            "swing_total": r["swing_total"], "long_total": r["long_total"],
                            "evaluated": r["evaluated"]})
    html = env.get_template("index.html.j2").render(markets=markets, root="", providers_note="yfinance ほか")
    (out_dir / "index.html").write_text(html, "utf-8")
