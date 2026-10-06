# 株式スクリーナー（日本株・米国株）

日経225 / S&P500 から **スイング候補** と **長期候補** を毎日抽出し、
`docs/` に HTML と JSON で出力して GitHub Pages で公開します。

- 日本株: 平日 16:17 JST（大引け 15:30 以降）に実行
- 米国株: 日本時間の翌朝 7:23（火〜土）に実行
- 結果と履歴（`docs/<市場>/history/YYYY-MM-DD.json`）はリポジトリにコミット

## 設計

```
GitHub Actions (cron / 手動実行)
   │
   ▼
python -m screener --market JP|US
   │
   ├─ universe.py      … data/universe/*.csv（日経225 / S&P500）を読む（実行前に最新化を試行）
   ├─ providers/       … データ取得（差し替え可能）
   │     PriceProvider        get_history(codes) → 日足 DataFrame
   │     FundamentalsProvider get_fundamentals(code) → 年次財務（Fundamentals）
   ├─ screens.py       … 条件評価。各条件が「通過可否・実数値・閾値」(Check) を返す
   ├─ pipeline.py      … 流動性フィルタ → スイング評価 → 財務（キャッシュ付き）→ 長期評価 → ランキング
   └─ report.py/chart.py … HTML（ランキング・銘柄ページ・履歴）と JSON、SVG チャートを出力
   │
   ▼
docs/ をコミット → GitHub Pages
```

- **データ取得の差し替え**: `config.yaml` の `markets.<市場>.providers` を書き換えるだけ。
  スクリーニング以降は `providers/base.py` の型にしか依存しません。
  | 名前 | 用途 | 状態 |
  |---|---|---|
  | `yfinance` | 日米の株価・財務（APIキー不要） | 実装済み（既定） |
  | `edgar` | 米国の財務（SEC XBRL companyfacts） | 実装済み・要 `SEC_USER_AGENT` |
  | `jquants` | 日本の株価 | 雛形（`providers/jquants.py`） |
  | `edinet` | 日本の財務 | 雛形（`providers/edinet.py`） |
  | `fake` | オフライン用ダミーデータ（テスト用） | 実装済み |
- **閾値**: `config.yaml` の `markets.<市場>.swing / long` に市場別に記述。
  `min_passed`（有効条件のうち何個以上で候補とするか）と `required`（必須条件）で判定。
- **根拠表示**: 全条件について ✓（通過）/ ✗（不通過）/ –（データ不足で判定不能）と実数値・閾値を表示。
- **財務キャッシュ**: `data/cache/fundamentals_<市場>.json`。`fundamentals_max_age_days` 日ごとに再取得。

### スクリーニング条件（既定値）

| 区分 | 条件 | 日本 | 米国 |
|---|---|---|---|
| スイング | 終値 > 25日線 > 75日線（必須） | ✓ | ✓ |
| | 25日線が5日前より上向き | ✓ | ✓ |
| | 25日線乖離率 | ≤ 8% | ≤ 10% |
| | 出来高 / 20日平均 | ≥ 1.5倍 | ≥ 1.5倍 |
| | RSI(14) | 50〜70 | 50〜72 |
| | 終値が前日までの20日高値を上抜け | ✓ | ✓ |
| | 20日平均売買代金 | ≥ 10億円 | ≥ $50M |
| 長期 | ROE（純利益 / 平均自己資本） | ≥ 8% | ≥ 15% |
| | 営業CFが3期連続プラス | ✓ | ✓ |
| | 自己資本比率 | ≥ 40% | ≥ 25% |
| | 増収増益（売上・営業利益）2期連続 | ✓ | ✓ |

スイングは6条件中4つ以上（トレンド必須）、長期は4条件中4つで候補。

## フォルダ構成

```
config.yaml                 市場切替・データソース・閾値
requirements.txt
screener/
  __main__.py               CLI
  config.py
  universe.py               ユニバース読込・更新（python -m screener.universe）
  pipeline.py               1市場分の処理
  indicators.py             SMA / RSI / 出来高倍率 / 直近高値
  screens.py                条件評価（Check）と判定
  chart.py                  SVG チャート（株価＋25/75日線、出来高）
  report.py                 HTML / JSON 出力
  providers/
    base.py                 インターフェース
    yfinance_provider.py  edgar.py  jquants.py  edinet.py  fake.py
templates/                  Jinja2 テンプレートと CSS/JS
data/
  universe/                 jp_nikkei225.csv, us_sp500.csv
  cache/                    財務キャッシュ
docs/                       ← GitHub Pages
  index.html
  jp/ index.html  latest.json  history.html  history/YYYY-MM-DD.json  stocks/<code>.html
  us/ （同上）
tests/
.github/workflows/
  screen-jp.yml  screen-us.yml  _screen.yml（共通）  test.yml
```

## 使い方

```bash
pip install -r requirements.txt
python -m screener --market JP --limit 10        # 日本株10銘柄だけ
python -m screener                               # config の enabled_markets 全部
python -m screener --provider fake --out build   # ネットワーク不要の動作確認
python -m pytest -q
```

GitHub Actions の「screen JP / screen US」は手動実行（Run workflow）も可能で、`limit` を指定できます。

### GitHub Pages の有効化

Settings → Pages → Build and deployment で
**Source: Deploy from a branch / Branch: `master` / フォルダ: `/docs`** を選択。

## 注意

- yfinance は Yahoo Finance の非公式 API です。仕様変更や取得制限で失敗することがあります
  （失敗した銘柄はスキップし、ページ下部の JSON の `skipped` に記録されます）。
- 本ツールの出力は機械的なスクリーニング結果であり、投資判断を推奨するものではありません。
