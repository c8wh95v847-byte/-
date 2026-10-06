"""1市場分のスクリーニングを実行して結果（dict）を返す。"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .config import ROOT
from .providers import Fundamentals, make_fundamentals_provider, make_price_provider
from .screens import evaluate_long, evaluate_swing, judge
from .universe import load_universe

log = logging.getLogger(__name__)


class FundamentalsCache:
    """財務データのキャッシュ（data/cache/fundamentals_<market>.json）。"""

    def __init__(self, path: Path, max_age_days: int):
        self.path, self.max_age = path, max_age_days
        self.data: dict = json.loads(path.read_text("utf-8")) if path.exists() else {}

    def get(self, code: str, provider: str) -> Fundamentals | None:
        e = self.data.get(code)
        if not e or e.get("provider") != provider:
            return None
        if date.fromisoformat(e["fetched"]) < date.today() - timedelta(days=self.max_age):
            return None
        return Fundamentals.from_dict(e["data"])

    def put(self, code: str, provider: str, f: Fundamentals) -> None:
        self.data[code] = {"provider": provider, "fetched": date.today().isoformat(), "data": f.to_dict()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, sort_keys=True, indent=0), "utf-8")


def run_market(cfg: dict, market: str, *, limit: int | None = None, provider_override: str | None = None,
               use_cache: bool = True) -> tuple[dict, dict[str, pd.DataFrame]]:
    mc = cfg["markets"][market]
    limit = limit if limit is not None else mc.get("limit")
    universe = load_universe(ROOT / mc["universe"], limit)
    names = {u["code"]: u["name"] for u in universe}
    codes = list(names)
    p_name = provider_override or mc["providers"]["price"]
    f_name = provider_override or mc["providers"]["fundamentals"]
    log.info("[%s] %d symbols, price=%s fundamentals=%s", market, len(codes), p_name, f_name)

    prices = make_price_provider(p_name, market).get_history(codes, mc.get("price_lookback_days", 400))
    if not prices:
        raise RuntimeError(f"[{market}] 株価を1銘柄も取得できませんでした")
    prices = drop_incomplete_bar(prices, mc)
    as_of = max(df.index[-1] for df in prices.values())

    fprov = make_fundamentals_provider(f_name, market)
    cache = FundamentalsCache(ROOT / cfg["cache"]["dir"] / f"fundamentals_{market.lower()}.json",
                              cfg["cache"].get("fundamentals_max_age_days", 7))

    swing_cfg, long_cfg = mc["swing"], mc["long"]
    min_turnover = mc.get("liquidity", {}).get("min_avg_turnover", 0)
    stocks, skipped = [], []
    for code in codes:
        df = prices.get(code)
        if df is None or len(df) < 80:
            skipped.append({"code": code, "reason": "株価データ不足"})
            continue
        if df.index[-1] < as_of:
            skipped.append({"code": code, "reason": f"最終取引日が古い（{df.index[-1]:%Y-%m-%d}）"})
            continue
        close = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        turnover = float((df["Close"] * df["Volume"]).tail(20).mean())

        s_checks, s_metrics = evaluate_swing(df, swing_cfg["conditions"])
        s_ok, s_passed = judge(s_checks, swing_cfg["min_passed"], swing_cfg.get("required", []))
        liquid = turnover >= min_turnover
        s_ok = s_ok and liquid

        f = cache.get(code, f_name) if use_cache else None
        if f is None:
            try:
                f = fprov.get_fundamentals(code)
            except NotImplementedError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] %s fundamentals error: %s", market, code, e)
                f = Fundamentals(code=code, source=f_name)
            if not f.is_empty:
                cache.put(code, f_name, f)
        l_checks, l_metrics = evaluate_long(f, long_cfg["conditions"], mc["currency"])
        l_ok, l_passed = judge(l_checks, long_cfg["min_passed"], long_cfg.get("required", []))

        stocks.append({
            "code": code, "name": names[code], "close": round(close, 2),
            "change_pct": round((close / prev - 1) * 100, 2),
            "avg_turnover": round(turnover), "liquid": liquid,
            "swing": {"candidate": s_ok, "passed": s_passed, "total": len(s_checks),
                      "metrics": _round(s_metrics), "checks": [c.to_dict() for c in s_checks]},
            "long": {"candidate": l_ok, "passed": l_passed, "total": len(l_checks),
                     "metrics": _round(l_metrics), "checks": [c.to_dict() for c in l_checks],
                     "fundamentals": None if f.is_empty else f.to_dict()},
        })
    if use_cache:
        cache.save()

    top_n = cfg["output"].get("top_n", 30)
    swing_rank = sorted((s for s in stocks if s["swing"]["candidate"]),
                        key=lambda s: (-s["swing"]["passed"], -(s["swing"]["metrics"].get("volume_ratio") or 0)))
    long_rank = sorted((s for s in stocks if s["long"]["candidate"]),
                       key=lambda s: (-s["long"]["passed"], -(s["long"]["metrics"].get("roe_pct") or 0)))
    result = {
        "market": market, "market_name": mc["name"], "currency": mc["currency"],
        "as_of": as_of.strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "providers": {"price": p_name, "fundamentals": f_name},
        "universe_size": len(codes), "evaluated": len(stocks), "skipped": skipped,
        "criteria": {"swing": swing_cfg, "long": long_cfg, "min_avg_turnover": min_turnover},
        "swing": [s["code"] for s in swing_rank[:top_n]],
        "long": [s["code"] for s in long_rank[:top_n]],
        "swing_total": len(swing_rank), "long_total": len(long_rank),
        "stocks": stocks,
    }
    log.info("[%s] as_of=%s evaluated=%d swing=%d long=%d", market, result["as_of"], len(stocks),
             len(swing_rank), len(long_rank))
    return result, prices


def drop_incomplete_bar(prices: dict[str, pd.DataFrame], mc: dict,
                        now: datetime | None = None) -> dict[str, pd.DataFrame]:
    """取引時間中（大引け＋settle_minutes 前）に実行した場合、当日の未確定の足を除く。"""
    tz = ZoneInfo(mc.get("timezone", "UTC"))
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    hh, mm = map(int, str(mc.get("close_time", "15:30")).split(":"))
    settled = now.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(
        minutes=mc.get("settle_minutes", 30))
    if now >= settled:
        return prices
    today = pd.Timestamp(now.date())
    out = {c: (df[df.index < today] if len(df) and df.index[-1] >= today else df) for c, df in prices.items()}
    log.info("取引時間中のため %s の未確定足を除外しました", today.date())
    return {c: df for c, df in out.items() if len(df)}


def _round(d: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}
