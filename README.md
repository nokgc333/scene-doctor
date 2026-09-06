# Scene Doctor

Houdiniシーンのジオメトリ欠陥（非多様体・N-gon・ゼロ面積）・ノード構造（未接続・未使用）・命名規則違反を自動検出するツール。

## 目的・背景

複数アーティストが触るHoudiniシーンは、非多様体ジオメトリ・ゼロ面積ポリゴン・未接続ノード・命名違反が静かに蓄積し、レンダー直前で発覚して手戻りを生みます。Scene Doctorはこれをバッチで自動検出・レポート化します。

詳細な要件定義・設計判断は [docs/要件定義書.md](docs/要件定義書.md) / [docs/仕様書.md](docs/仕様書.md) を参照してください。

> このツールは `~/3dcg-dev/houdini_dev` の `tornado_00.hiplc` / `spiderweb_v1.hip` / `v2.hip`（過去の習作HDA）を「検出対象の壊れたシーン」として再利用する設計です。同ディレクトリの `houdini-mcp`（`oculairmedia/houdini-mcp`のクローン）はScene Doctorの実装に一切使用していません。

## アーキテクチャ（Ports & Adapters）

検証ロジック（`checks/`, `rules.py`, `report.py`, CLIオーケストレーション）は `hou` に依存しない純粋なPythonで実装し、実`hou`呼び出しは `scene_doctor/adapters/hou_adapter.py` のみに閉じ込めています（[ADR-0001](docs/adr/0001-ports-and-adapters.md)）。これにより、**Houdiniがインストールされていない環境でも大部分のロジックをTDDで検証できます**。

```
scene_doctor/
├── interfaces.py        # GeometryLike / NodeLike Protocol
├── adapters/
│   └── hou_adapter.py   # 実houへの依存はここに閉じ込める（hython専用、CIでは検証不可）
├── checks/
│   ├── geometry.py       # 非多様体・N-gon・ゼロ面積
│   ├── naming.py         # 命名規則違反・リネーム候補
│   └── nodes.py          # 未接続・未使用（バイパス）ノード
├── rules.py               # 命名規則YAML読込
└── report.py              # CSV/JSON出力
scene_doctor_cli.py         # hythonから起動するCLIエントリポイント
```

## 技術スタック

- Python 3.11+ / hython（Houdini 20.5 Indie/Education同梱）
- PyYAML（`yaml.safe_load`のみ使用）
- pytest / pytest-cov / mypy(strict, adaptersのみhouスタブ不在のため一部緩和) / black / isort / flake8 / pip-audit

## インストール（開発・テスト用、Houdini不要）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest --cov-fail-under=80
```

## 使用方法（実機・hython専用）

```bash
hython scene_doctor_cli.py --hip path/to/scene.hip --rules rules/default.yaml --format both
```

終了コード: `0`=違反なし / `1`=違反あり / `10`〜`14`=エラー系（詳細は [docs/仕様書.md §5.6](docs/仕様書.md)）

### 実機での検証手順（このリポジトリのCIではカバーできない部分）

このリポジトリのCIはHoudini自体を含まないため、以下は実際のHoudini上での手動確認が必要です（要件定義書 TC-023, TC-024）。

1. Houdiniで `~/3dcg-dev/houdini_dev/tornado_00.hiplc` を開く
2. `hda/SceneDoctor.hdalc` を対象SOPネットワークに配置し、`Run All Checks` を実行
3. 既知の欠陥（非多様体等）が検出されることを確認し、検出件数を記録する
4. `spiderweb_v1.hip` と `spiderweb_v2.hip` を比較し、違反件数の差分をレポートできることを確認する

## テスト

```bash
pytest --cov-fail-under=80
black --check . && isort --check . && flake8 scene_doctor/ scene_doctor_cli.py tests/ && mypy scene_doctor/ scene_doctor_cli.py
```

39テスト全pass、カバレッジ94%（`adapters/`はカバレッジ計測から除外、理由は[Design Decisions](#design-decisions)参照）。

## 既知の制限事項

- `adapters/hou_adapter.py` の正しさは実機（Houdini）でのみ検証可能。この開発環境では検証できていない
- `hda/SceneDoctor.hdalc` と `pdg/batch_topnet.hip` は設計のみで、実際のHDA/TOPsネットワークはHoudini上で作成する必要がある
- ノード探索戦略（`/obj`配下でDisplayフラグが立つ最初のgeoノードを対象にする）は単純化した初期実装であり、複数geoノードを持つ複雑なシーンでの妥当性は未検証

## Design Decisions

- **Ports & Adaptersでhouへの依存を分離** — Houdiniなしでもロジックの大部分をテストできるようにするため（[ADR-0001](docs/adr/0001-ports-and-adapters.md)）
- **PDG（TOPs）でバッチ処理** — 依存関係グラフに基づくスケジューリングと失敗時の部分再実行を標準機能で実現するため（[ADR-0002](docs/adr/0002-pdg-for-batch-processing.md)）
- **自動修正は行わずリネーム候補の提示に留める** — ジオメトリの自動修正は意図しない形状変化のリスクが高いため（[ADR-0003](docs/adr/0003-no-auto-fix.md)）
- **非多様体判定は「3枚以上が共有するエッジ」のみを対象とする** — 実装当初は「2枚以外」を非多様体としていたが、TDDで開いた面（境界エッジ、1枚のみ共有）を含む正常なジオメトリのテストを書いたところ誤検出することが判明したため修正した。CGの標準用語でも境界エッジと非多様体エッジは区別されるべき、という判断
- **YAML読込は`yaml.safe_load`のみ使用** — 任意コード実行を防ぐ多層防御として（SEC-001）

## セキュリティに関する注意

Scene Doctorは検証対象の.hipファイルを「出所が既知の信頼済み入力」として扱います。Houdini自体がPythonノードや式を含む.hipファイルを開いた時点でコードを実行しうるため、出所不明の.hipファイルは開かないでください。Scene Doctor自身は以下を一切行いません。

- `yaml.safe_load`以外でのYAML読込
- `exec`/`eval`による動的コード実行
- シーンファイルの暗黙的な書き換え（`Apply Rename Candidates`以外）

## ライセンス

MIT License（[LICENSE](LICENSE)参照）
