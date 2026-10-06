import json

from screener.__main__ import main


def test_fake_run_writes_pages(tmp_path, monkeypatch):
    out = tmp_path / "site"
    monkeypatch.setattr("screener.__main__.ROOT", tmp_path)
    assert main(["--market", "JP", "--market", "US", "--limit", "10", "--provider", "fake",
                 "--out", str(out)]) == 0
    for m in ("jp", "us"):
        r = json.loads((out / m / "latest.json").read_text())
        assert r["evaluated"] == 10
        assert (out / m / "index.html").exists() and (out / m / "history.html").exists()
        for code in set(r["swing"] + r["long"]):
            assert (out / m / "stocks" / f"{code.replace('.', '-')}.html").exists()
    assert (out / "index.html").exists() and (out / "assets" / "style.css").exists()
