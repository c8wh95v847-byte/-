"""銘柄別の簡易チャート（株価＋移動平均、出来高）をインライン SVG で生成する。

外部ライブラリ不要・軽量でスマホでもそのまま表示できる。
色は CSS 変数（--series-1..3, --grid 等）で指定し、ライト/ダークはページ側の CSS で切り替える。
価格と出来高は別パネル（2軸は使わない）。
"""
from __future__ import annotations

import json
import math

import pandas as pd

from . import indicators as ind

W, H_PRICE, H_VOL = 640, 260, 70
PAD_L, PAD_R, PAD_T, PAD_B = 8, 64, 10, 20


def _nice_ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=raw)
    start = math.ceil(lo / step) * step
    ticks, v = [], start
    while v <= hi + 1e-9:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _fmt_tick(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}".rstrip("0").rstrip(".")


def build_chart(df: pd.DataFrame, days: int, short: int = 25, long: int = 75) -> dict:
    """チャートの SVG とホバー用データを返す。"""
    close = df["Close"]
    s_ma, l_ma = ind.sma(close, short), ind.sma(close, long)
    d = df.tail(days)
    s_ma, l_ma, vol = s_ma.loc[d.index], l_ma.loc[d.index], d["Volume"]
    n = len(d)
    plot_w = W - PAD_L - PAD_R
    x = lambda i: PAD_L + (plot_w * (i + 0.5) / n)  # noqa: E731

    series = [("close", "終値", d["Close"], "var(--series-1)"),
              ("sma_s", f"{short}日線", s_ma, "var(--series-2)"),
              ("sma_l", f"{long}日線", l_ma, "var(--series-3)")]
    vals = pd.concat([d["Close"], s_ma, l_ma]).dropna()
    lo, hi = float(vals.min()), float(vals.max())
    pad = (hi - lo) * 0.06 or hi * 0.02
    lo, hi = lo - pad, hi + pad
    ph = H_PRICE - PAD_T - PAD_B
    y = lambda v: PAD_T + ph * (1 - (v - lo) / (hi - lo))  # noqa: E731

    parts = [f'<svg class="chart" viewBox="0 0 {W} {H_PRICE + H_VOL}" role="img" '
             f'aria-label="株価と移動平均（直近{n}日）" preserveAspectRatio="none">']
    # グリッドと価格目盛り
    for t in _nice_ticks(lo, hi):
        yy = y(t)
        parts.append(f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="tick" x="{W - PAD_R + 6}" y="{yy + 4:.1f}">{_fmt_tick(t)}</text>')
    # 月の区切り（x軸ラベル）
    prev_m = None
    for i, ts in enumerate(d.index):
        if ts.month != prev_m and prev_m is not None:
            parts.append(f'<text class="tick" x="{x(i):.1f}" y="{H_PRICE - 4}" text-anchor="middle">'
                         f'{ts.month}月</text>')
        prev_m = ts.month
    # 線（移動平均 → 終値の順で終値を最前面に）
    for key, _label, s, color in reversed(series):
        pts = [f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(s) if not pd.isna(v)]
        if len(pts) > 1:
            parts.append(f'<polyline class="line" style="stroke:{color}" points="{" ".join(pts)}"/>')
    # 終値の最終点
    lx, ly = x(n - 1), y(float(d["Close"].iloc[-1]))
    parts.append(f'<circle class="end" cx="{lx:.1f}" cy="{ly:.1f}" r="4" style="fill:var(--series-1)"/>')

    # 出来高パネル
    vmax = float(vol.max()) or 1.0
    vb = H_PRICE + H_VOL - 4
    bw = max(1.0, plot_w / n - 1.5)
    for i, v in enumerate(vol):
        h = (H_VOL - 12) * float(v) / vmax
        parts.append(f'<rect class="vol" x="{x(i) - bw / 2:.1f}" y="{vb - h:.1f}" width="{bw:.1f}" '
                     f'height="{h:.1f}"/>')
    parts.append(f'<line class="axis" x1="{PAD_L}" x2="{W - PAD_R}" y1="{vb}" y2="{vb}"/>')
    parts.append(f'<text class="tick" x="{W - PAD_R + 6}" y="{H_PRICE + 12}">出来高</text>')
    # ホバー用
    parts.append(f'<line class="cross" x1="0" x2="0" y1="{PAD_T}" y2="{vb}" visibility="hidden"/>')
    parts.append(f'<rect class="hit" x="{PAD_L}" y="0" width="{plot_w}" height="{H_PRICE + H_VOL}"/>')
    parts.append("</svg>")

    def r(v):
        return None if pd.isna(v) else round(float(v), 2)

    data = {
        "x0": PAD_L, "pw": plot_w, "w": W, "ls": f"{short}日線", "ll": f"{long}日線",
        "dates": [ts.strftime("%Y-%m-%d") for ts in d.index],
        "close": [r(v) for v in d["Close"]],
        "sma_s": [r(v) for v in s_ma],
        "sma_l": [r(v) for v in l_ma],
        "vol": [int(v) if not pd.isna(v) else None for v in vol],
    }
    legend = [{"label": label, "color": color} for _k, label, _s, color in series]
    return {"svg": "".join(parts), "data": json.dumps(data, separators=(",", ":")), "legend": legend}
