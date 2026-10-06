"""スクリーニング条件の評価。

各条件は Check（通過可否・実数値・閾値）を返し、銘柄ごとに根拠として出力する。
閾値はすべて config.yaml の markets.<市場>.swing / long から渡される。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import pandas as pd

from . import indicators as ind
from .providers.base import Fundamentals


@dataclass
class Check:
    key: str
    label: str
    passed: bool | None          # None = データ不足で判定不能
    value: str                   # 実数値（表示用）
    threshold: str               # 条件（表示用）

    def to_dict(self) -> dict:
        return asdict(self)


def _f(x, digits=1, suffix=""):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:,.{digits}f}{suffix}"


def _num(x):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else x


# ---------------------------------------------------------------- swing

def evaluate_swing(df: pd.DataFrame, conds: dict) -> tuple[list[Check], dict]:
    """日足から各スイング条件を評価する。戻り値: (checks, metrics)"""
    close, high, vol = df["Close"], df["High"], df["Volume"]
    last = _num(close.iloc[-1])
    checks: list[Check] = []
    m: dict = {"close": last}

    c = conds.get("trend", {})
    if c.get("enabled", True):
        s, l = c.get("short", 25), c.get("long", 75)
        ms, ml = _num(ind.sma(close, s).iloc[-1]), _num(ind.sma(close, l).iloc[-1])
        m[f"sma{s}"], m[f"sma{l}"] = ms, ml
        ok = None if ms is None or ml is None else (last > ms > ml)
        checks.append(Check("trend", f"{s}/{l}日線の上で順行", ok,
                            f"終値 {_f(last)} / {s}日 {_f(ms)} / {l}日 {_f(ml)}",
                            f"終値 > {s}日線 > {l}日線"))

    c = conds.get("ma_slope", {})
    if c.get("enabled", True):
        p, lb = c.get("period", 25), c.get("lookback", 5)
        ma = ind.sma(close, p)
        now, before = _num(ma.iloc[-1]), _num(ma.iloc[-1 - lb]) if len(ma) > lb else None
        slope = None if now is None or before is None else (now / before - 1) * 100
        m["ma_slope_pct"] = slope
        checks.append(Check("ma_slope", f"{p}日線が上向き", None if slope is None else slope > 0,
                            f"{lb}日前比 {_f(slope, 2, '%')}", "> 0%"))

    c = conds.get("deviation", {})
    if c.get("enabled", True):
        p, mx = c.get("period", 25), c.get("max_pct", 8.0)
        ma = _num(ind.sma(close, p).iloc[-1])
        dev = None if ma is None else (last / ma - 1) * 100
        m["deviation_pct"] = dev
        checks.append(Check("deviation", f"{p}日線乖離が過熱でない", None if dev is None else dev <= mx,
                            _f(dev, 1, "%"), f"≤ {mx:g}%"))

    c = conds.get("volume_surge", {})
    if c.get("enabled", True):
        ap, mr = c.get("avg_period", 20), c.get("min_ratio", 1.5)
        vr = _num(ind.volume_ratio(vol, ap).iloc[-1])
        m["volume_ratio"] = vr
        checks.append(Check("volume_surge", "出来高急増", None if vr is None else vr >= mr,
                            f"{_f(vr, 2)}倍（{ap}日平均比）", f"≥ {mr:g}倍"))

    c = conds.get("rsi", {})
    if c.get("enabled", True):
        p, lo, hi = c.get("period", 14), c.get("min", 50), c.get("max", 70)
        r = _num(ind.rsi(close, p).iloc[-1])
        m["rsi"] = r
        checks.append(Check("rsi", f"RSI({p})", None if r is None else lo <= r <= hi,
                            _f(r, 1), f"{lo:g}〜{hi:g}"))

    c = conds.get("breakout", {})
    if c.get("enabled", True):
        lb = c.get("lookback", 20)
        ph = _num(ind.prior_high(high, lb).iloc[-1])
        m["prior_high"] = ph
        checks.append(Check("breakout", f"直近{lb}日高値ブレイク", None if ph is None else last > ph,
                            f"終値 {_f(last)} / 高値 {_f(ph)}", f"終値 > 前日までの{lb}日高値"))
    return checks, m


# ----------------------------------------------------------------- long

def _at(xs: list, i: int):
    return _num(xs[i]) if xs and i < len(xs) else None


def evaluate_long(f: Fundamentals, conds: dict, currency: str = "JPY") -> tuple[list[Check], dict]:
    checks: list[Check] = []
    m: dict = {"fiscal_year": f.fiscal_years[0] if f.fiscal_years else None}

    c = conds.get("roe", {})
    if c.get("enabled", True):
        mn = c.get("min_pct", 8.0)
        ni, e0, e1 = _at(f.net_income, 0), _at(f.equity, 0), _at(f.equity, 1)
        if ni is not None and e0 is not None and e0 <= 0:
            # 債務超過（自己資本マイナス）では ROE が意味をなさないので不通過扱い
            m["roe_pct"] = None
            checks.append(Check("roe", "ROE", False, "算出不可（自己資本がマイナス）", f"≥ {mn:g}%"))
        else:
            avg_eq = (e0 + e1) / 2 if e0 is not None and e1 is not None and e1 > 0 else e0
            roe = None if ni is None or not avg_eq else ni / avg_eq * 100
            m["roe_pct"] = roe
            checks.append(Check("roe", "ROE", None if roe is None else roe >= mn,
                                _f(roe, 1, "%"), f"≥ {mn:g}%"))

    c = conds.get("operating_cf", {})
    if c.get("enabled", True):
        n = c.get("years", 3)
        vals = [_at(f.operating_cf, i) for i in range(n)]
        m["operating_cf"] = vals[0]
        ok = None if any(v is None for v in vals) else all(v > 0 for v in vals)
        if ok is None and any(v is not None and v <= 0 for v in vals):
            ok = False
        checks.append(Check("operating_cf", f"営業CFが{n}期連続プラス", ok,
                            " / ".join(_compact(v, currency) for v in vals) + "（新→旧）", f"{n}期すべて > 0"))

    c = conds.get("equity_ratio", {})
    if c.get("enabled", True):
        mn = c.get("min_pct", 40.0)
        e, a = _at(f.equity, 0), _at(f.total_assets, 0)
        er = None if e is None or not a else e / a * 100
        m["equity_ratio_pct"] = er
        checks.append(Check("equity_ratio", "自己資本比率", None if er is None else er >= mn,
                            _f(er, 1, "%"), f"≥ {mn:g}%"))

    c = conds.get("growth", {})
    if c.get("enabled", True):
        n, metric = c.get("years", 2), c.get("metric", "operating_income")
        prof = getattr(f, metric)
        label_p = "営業利益" if metric == "operating_income" else "純利益"
        rev = [_at(f.revenue, i) for i in range(n + 1)]
        pro = [_at(prof, i) for i in range(n + 1)]
        streak, known = 0, True
        for i in range(n):
            if None in (rev[i], rev[i + 1], pro[i], pro[i + 1]):
                known = False
                break
            if rev[i] > rev[i + 1] and pro[i] > pro[i + 1]:
                streak += 1
            else:
                break
        # データ不足で n 期分を確認できなければ判定不能（None）
        ok = True if streak >= n else (False if known else None)
        m["growth_streak"] = streak
        rg = _pct(rev[0], rev[1])
        pg = _pct(pro[0], pro[1])
        checks.append(Check("growth", f"増収増益が{n}期連続", ok,
                            f"{streak}期連続（直近 売上 {_f(rg, 1, '%')} / {label_p} {_f(pg, 1, '%')}）",
                            f"売上・{label_p}とも{n}期連続で前期比増"))
    return checks, m


def _pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1) * 100 * (1 if b > 0 else -1)


def _compact(v, currency: str = "JPY") -> str:
    """大きな金額を短く表示（通貨記号なし）。円: 1.2兆 / 345億、ドル: 12.3B / 456M。"""
    if v is None:
        return "—"
    a = abs(v)
    if currency != "JPY":
        for unit, d in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
            if a >= d:
                return f"{v / d:,.1f}{unit}"
        return f"{v:,.0f}"
    if a >= 1e12:
        return f"{v / 1e12:.2f}兆"
    if a >= 1e8:
        return f"{v / 1e8:,.0f}億"
    if a >= 1e4:
        return f"{v / 1e4:,.0f}万"
    return f"{v:,.0f}"


# --------------------------------------------------------------- judging

def judge(checks: list[Check], min_passed: int, required: list[str]) -> tuple[bool, int]:
    """候補になるか、および通過数。"""
    passed = sum(1 for c in checks if c.passed)
    req_ok = all(any(c.key == r and c.passed for c in checks) for r in required)
    return (req_ok and passed >= min(min_passed, len(checks))), passed
