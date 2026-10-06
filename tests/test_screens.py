import numpy as np
import pandas as pd

from screener import indicators as ind
from screener.providers.base import Fundamentals
from screener.providers.fake import FakePriceProvider
from screener.screens import evaluate_long, evaluate_swing, judge

SWING = {
    "trend": {"short": 25, "long": 75}, "ma_slope": {"period": 25, "lookback": 5},
    "deviation": {"period": 25, "max_pct": 8.0}, "volume_surge": {"avg_period": 20, "min_ratio": 1.5},
    "rsi": {"period": 14, "min": 50, "max": 70}, "breakout": {"lookback": 20},
}
LONG = {"roe": {"min_pct": 8}, "operating_cf": {"years": 3}, "equity_ratio": {"min_pct": 40},
        "growth": {"years": 2, "metric": "operating_income"}}


def _df(close, vol=None):
    idx = pd.bdate_range("2025-01-01", periods=len(close))
    close = pd.Series(close, index=idx, dtype=float)
    vol = pd.Series(vol if vol is not None else [1000] * len(close), index=idx, dtype=float)
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": vol})


def test_sma_and_rsi_bounds():
    s = pd.Series(np.arange(1, 101, dtype=float))
    assert ind.sma(s, 5).iloc[-1] == 98.0
    assert ind.rsi(s, 14).iloc[-1] == 100.0          # 上昇のみ
    assert ind.rsi(-s, 14).iloc[-1] < 1e-9           # 下落のみ


def test_volume_ratio_excludes_today():
    v = pd.Series([100.0] * 20 + [300.0])
    assert ind.volume_ratio(v, 20).iloc[-1] == 3.0


def test_swing_uptrend_breakout_passes_all():
    close = list(np.linspace(100, 130, 119)) + [132.0]
    vol = [1000] * 119 + [2000]
    checks, m = evaluate_swing(_df(close, vol), SWING)
    by = {c.key: c for c in checks}
    assert by["trend"].passed and by["ma_slope"].passed and by["breakout"].passed
    assert by["volume_surge"].passed and m["volume_ratio"] == 2.0
    assert by["rsi"].passed is False  # 一本調子の上昇は RSI が高すぎる
    assert "倍" in by["volume_surge"].value


def test_swing_short_history_is_undetermined():
    checks, _ = evaluate_swing(_df(np.linspace(100, 110, 30)), SWING)
    assert {c.key: c.passed for c in checks}["trend"] is None


def test_judge_required_and_min():
    checks, _ = evaluate_swing(_df(list(np.linspace(130, 100, 120))), SWING)
    ok, passed = judge(checks, 1, ["trend"])
    assert not ok  # 下降トレンドは必須条件で除外


def _fund(**kw):
    base = dict(code="X", fiscal_years=["2025", "2024", "2023", "2022"],
                revenue=[130, 120, 110, 100], operating_income=[13, 12, 11, 10], net_income=[10, 9, 8, 7],
                operating_cf=[12, 11, 10, 9], total_assets=[200, 190, 180, 170], equity=[100, 90, 80, 70])
    base.update(kw)
    return Fundamentals(**base)


def test_long_all_pass():
    checks, m = evaluate_long(_fund(), LONG)
    assert all(c.passed for c in checks)
    assert round(m["roe_pct"], 2) == round(10 / 95 * 100, 2)
    assert m["equity_ratio_pct"] == 50.0
    assert judge(checks, 4, [])[0]


def test_long_failures_and_missing():
    checks, _ = evaluate_long(_fund(operating_cf=[12, -1, 10, 9], revenue=[130, 140, 110, 100]), LONG)
    by = {c.key: c.passed for c in checks}
    assert by["operating_cf"] is False and by["growth"] is False
    checks, _ = evaluate_long(_fund(revenue=[130, None, None, None]), LONG)
    assert {c.key: c.passed for c in checks}["growth"] is None
    checks, _ = evaluate_long(Fundamentals(code="X"), LONG)
    assert all(c.passed is None for c in checks)


def test_fake_provider_is_deterministic():
    a = FakePriceProvider("JP", end="2026-01-05").get_history(["7203"], 200)["7203"]
    b = FakePriceProvider("JP", end="2026-01-05").get_history(["7203"], 200)["7203"]
    pd.testing.assert_frame_equal(a, b)
