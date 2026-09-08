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
│   ├── hou_adapter.py            # 実houへの依存はここに閉じ込める（hython専用、CIでは検証不可）
│   └── houdini_panel_launch.py   # PySide6パネルの実Houdiniドッキング（同上、CIでは検証不可）
├── checks/
│   ├── geometry.py       # 非多様体・N-gon・ゼロ面積
│   ├── naming.py         # 命名規則違反・リネーム候補
│   └── nodes.py          # 未接続・未使用（バイパス）ノード
├── ui/
│   ├── panel_view_model.py  # DCC非依存: SceneReport→表示行データの変換・フィルタ・ソート
│   └── panel.py              # PySide6のQDockWidget。houは一切importしない（DI疎結合）
├── rules.py               # 命名規則YAML読込
└── report.py              # CSV/JSON出力
scene_doctor_cli.py         # hythonから起動するCLIエントリポイント
```

HDA（パラメータUIのみ）に加え、Houdini本体にドッキングするリッチなPySide6カスタムパネル
（違反一覧のツリー表示・クリックでのノード選択ジャンプ・severity/categoryフィルタ）を
`scene_doctor/ui/`に実装している。GUI層にもPorts & Adaptersと同じ思想を適用し、
`panel_view_model.py`（DCC非依存の純粋関数）と`panel.py`（PySide6のみ、houは不使用）を
コールバック注入で疎結合にすることで、`QT_QPA_PLATFORM=offscreen`のヘッドレス環境でも
本物のPySide6ウィジェットとして`pytest-qt`でTDDできる（[ADR-0007](docs/adr/0007-pyside6-panel-ports-and-adapters.md)）。

## 技術スタック

- Python 3.11+ / hython（Houdini 22.0 Indie同梱で実機検証済み。仕様書上のターゲットは20.5だが、22.0でも動作を確認）
- PyYAML（`yaml.safe_load`のみ使用）
- PySide6（Houdini同梱の`hou.qt`経由で実機利用、開発・テストは`pip install PySide6`で導入）
- pytest / pytest-cov / pytest-qt（`QT_QPA_PLATFORM=offscreen`でPySide6ウィジェットをヘッドレステスト） / mypy(strict, adaptersのみhouスタブ不在のため一部緩和) / black / isort / flake8 / pip-audit

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

### PySide6カスタムパネルの起動（実機・Houdini本体専用）

Houdiniの Python Shell、または shelf tool のスクリプトから以下を実行するとパネルが起動する。

```python
from scene_doctor.adapters.houdini_panel_launch import launch_panel

panel = launch_panel()
```

`launch_panel()`は`hou.qt.mainWindow()`を親にした`SceneDoctorPanel`（`QDockWidget`）を
フローティング表示する。パネル上の「Run Checks」で現在の`/obj`配下の対象geoノードを検証し、
違反一覧をツリー表示する。行をクリックすると対象ノードを選択・カレント化し、
ネットワークエディタでフレーミングする。「Export CSV / Export JSON」で
`export_path_edit`に入力したパス（空の場合は`$HIP/scene_doctor_report`）へ出力する。

### 実機検証結果（2026-09-07実施、TC-023 / TC-024）

`hython`ネイティブ実行（Houdini 22.0.429、RPC非経由）で`tornado_00.hiplc` / `spiderweb_v1.hip` / `spiderweb_v2.hip`に対して実行し、以下3件の実データ特有のバグを発見・修正した。

| 発見箇所 | 症状 | 原因 | 対応 |
|---|---|---|---|
| `is_display_flag_set`等 | `AttributeError: 'DopNode' object has no attribute 'isRenderFlagSet'` | DOP Network SOP配下のDOPノードにSOP専用フラグメソッドを呼んでいた | 対象ノードがメソッドを持たない場合はFalseを返す（`hou_adapter.py`） |
| `children()`の再帰 | DOPネットワーク内部への再帰で実質ハング（120秒経っても未完了） | ノードカテゴリ境界（Sop/Dop等）を意識せず無制限に再帰していた | ルート確定時のカテゴリを境界として、異なるカテゴリの子は辿らない |
| `measured_area()` | `hou.OperationFailed`（`attribValue("measuredarea")`） | `measuredarea`はアトリビュートではなくintrinsic | `intrinsicValue("measuredarea")`に修正 |
| `output_connections()` | `AttributeError: 'NoneType' object has no attribute 'childTypeCategory'` | `c.outputNode()`がNoneを返すケースがあった | Noneを除外 |

修正後、`spiderweb_v1.hip`（62,749プリム）に対し**build_report: 2.12秒**で完走し、56,788件の違反（大半はzero_area。糸状ジオメトリのため多くのプリミティブが実質面積を持たない、想定通りの結果）を検出。`spiderweb_v2.hip`も同一件数を検出し、v1/v2比較が正しく機能することを確認した。

62,749プリムを人間が1件ずつビューポートで目視チェックすることは現実的に不可能な規模であり（1件1秒でも17時間以上）、この規模のシーンではScene Doctorのような自動検出が実務上ほぼ唯一の現実的な手段になる。

このリポジトリのCI自体にはHoudiniを含められないため、上記はローカルでの手動検証であり自動化されていない。同じ手順を再現する場合:

```bash
HYTHON="/path/to/Houdini/Resources/bin/hython"
cd scene_doctor
"$HYTHON" -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(0, '.venv/lib/python3.12/site-packages')  # PyYAMLをhython側から見えるようにする
from scene_doctor.adapters.hou_adapter import load_scene
from scene_doctor_cli import build_report, validate_target_is_sop_network
from pathlib import Path

hip_path = Path('/path/to/scene.hip')
geo, network = load_scene(hip_path)
validate_target_is_sop_network(network)
report = build_report(str(hip_path), geo, network, naming_rules=[])
print(report.violation_count)
"
```

### HDA実機検証結果（2026-09-07実施）

`hda/SceneDoctor.hdalc`をHoudini 22.0上で実際に構築し、Run All Checks / Export CSV/JSON / Apply Rename Candidatesの全ボタンを動作確認した（`hda/scene_doctor_demo.hip`にテストシーンを保存）。

**重要な設計変更**: 当初`null`SOPをベースにHDA化しようとしたが、`node.canCreateDigitalAsset()`が`False`を返し変換不能だった（Houdiniの制約上、リーフ型のSOPはHDA化できず、`subnet`のようなコンテナ型のみが変換可能）。`subnet`ベースに変更して解決した（[ADR-0005](docs/adr/0005-hda-subnet-base.md)）。

さらに実機検証で2件のバグを発見・修正した。

| 発見箇所 | 症状 | 原因 | 対応 |
|---|---|---|---|
| `Run All Checks`ボタン | `No module named 'yaml'` | hython同梱Pythonにpyyaml未同梱 | PythonModuleが`.venv`のsite-packagesをフォールバックで検索するように変更（本番運用では`hython -m pip install pyyaml`を推奨） |
| 同一バッチ内の複数naming違反 | `box1`と`box2`が両方とも`geo_001`を提案（実際の適用時はHoudini側のunique_name機構で衝突は避けられるが、レポート上の表示が不正確） | `generate_rename_candidate`が「既存ノード名」のみを避け、「このバッチ内で既に提案済みの候補」を考慮していなかった | 提案するたびに候補名を`reserved_names`集合へ追加し、以降の候補生成で回避するよう修正（`checks/naming.py`、テストケース追加済み） |

`Apply Rename Candidates`実行後、`box1`→`geo_001`、`box2_unconnected`→`geo_002`と重複なくリネームされたことを実機で確認した。

`hda/python_module_source.py`にPythonModuleセクションの可読コピーを同梱している（`.hdalc`本体はバイナリのためdiffが読めないことへの対策）。

### PDGバッチ処理

`pdg/batch_topnet.hip`にTOPsネットワークを構築済み（仕様書§10.1準拠）。

```
[File Pattern TOP: hip_files] --*.hip*をglob--> [Python Script TOP: run_scene_doctor]
    --hython scene_doctor_cli.pyをサブプロセス起動(固定引数のみ、SEC-002)--> [Wait For All TOP]
    --> [Python Script TOP: aggregate_reports] --個別JSONを集約-->
        pdg/reports/aggregate_report.json / .csv
```

`File Pattern`単体のcook（`~/3dcg-dev/houdini_dev/spiderweb_v1.hip`1件の検出・cook成功）は
実機で確認できたが、`houdini_mcp`（RPCブリッジ、検証専用ツール）経由での
`cookOutputWorkItems()`等によるネットワーク全体の自動cookは、下流ノードへの
ワークアイテム伝播が機能せず断念した（PDGの非同期cook処理がRPC越しの同期呼び出しと
相性が悪いためと推定、[ADR-0006](docs/adr/0006-pdg-manual-cook-only.md)）。

**そのため、バッチ処理全体の動作確認にはHoudini UI上での手動cook実行が必要**（TOPネットワーク
ペインを開き、`aggregate_reports`ノードを選択して「Cook Output Node」を実行する）。
`pdg/run_scene_doctor_source.py` / `pdg/aggregate_reports_source.py`に各Python Script TOPの
可読コピーを同梱している。

## テスト

```bash
pytest --cov-fail-under=80
black --check . && isort --check . && flake8 scene_doctor/ scene_doctor_cli.py tests/ && mypy scene_doctor/ scene_doctor_cli.py
```

72テスト全pass、カバレッジ96%（`adapters/`はカバレッジ計測から除外、理由は[Design Decisions](#design-decisions)参照）。
`scene_doctor/ui/panel_view_model.py`・`scene_doctor/ui/panel.py`はいずれもカバレッジ100%。
`panel.py`は`QT_QPA_PLATFORM=offscreen`（`tests/conftest.py`）でヘッドレスQApplicationを起動し、
`pytest-qt`の`qtbot`で本物のPySide6ウィジェット（`SceneDoctorPanel`）に対しボタンクリック・
行選択・severity/categoryフィルタ変更など実際のシグナル/スロットを検証している
（`tests/test_panel.py`）。

## 既知の制限事項

- `pdg/batch_topnet.hip` はネットワーク構築済みだが、cook実行の自動E2E検証はできていない（Houdini UI上での手動実行が必要、[ADR-0006](docs/adr/0006-pdg-manual-cook-only.md)）
- ノード探索戦略（`/obj`配下でDisplayフラグが立つ最初のgeoノードを対象にする）は単純化した初期実装であり、複数geoノードを持つ複雑なシーンでの妥当性は未検証
- `adapters/hou_adapter.py`はtornado_00.hiplc / spiderweb_v1.hip / spiderweb_v2.hip / scene_doctor_demo.hipの4シーンで実機検証済みだが、それ以外の未知のノード構成（Solaris/LOPs、COP等）では同様の実データ特有の問題が起こりうる
- HDAのPythonModuleは開発中の事故防止のため毎回scene_doctorパッケージを強制リロードする（本番運用では削除しパフォーマンスを優先する余地あり）
- `adapters/houdini_panel_launch.py`は実機Houdini環境でのみ動作確認可能なため、このセッションでは自動テスト対象外（別セッションで実機検証予定）。`hou.qt.mainWindow()`を親にしたフローティング表示という簡易実装に留めており、`hou.ui.curDesktop()`経由の正式なタブドッキングへの統合可否・ネットワークエディタのフレーミング処理（`homeToSelection()`）の実際の挙動は未検証

## Design Decisions

- **Ports & Adaptersでhouへの依存を分離** — Houdiniなしでもロジックの大部分をテストできるようにするため（[ADR-0001](docs/adr/0001-ports-and-adapters.md)）
- **PDG（TOPs）でバッチ処理** — 依存関係グラフに基づくスケジューリングと失敗時の部分再実行を標準機能で実現するため（[ADR-0002](docs/adr/0002-pdg-for-batch-processing.md)）
- **自動修正は行わずリネーム候補の提示に留める** — ジオメトリの自動修正は意図しない形状変化のリスクが高いため（[ADR-0003](docs/adr/0003-no-auto-fix.md)）
- **非多様体判定は「3枚以上が共有するエッジ」のみを対象とする** — 実装当初は「2枚以外」を非多様体としていたが、TDDで開いた面（境界エッジ、1枚のみ共有）を含む正常なジオメトリのテストを書いたところ誤検出することが判明したため修正した。CGの標準用語でも境界エッジと非多様体エッジは区別されるべき、という判断
- **YAML読込は`yaml.safe_load`のみ使用** — 任意コード実行を防ぐ多層防御として（SEC-001）
- **PySide6パネルもPorts & Adaptersで分離** — `panel_view_model.py`（DCC非依存）と`panel.py`（PySide6のみ、houは不使用、コールバック注入）に分離することで、Houdiniなしでも本物のPySide6ウィジェットとしてTDDできるようにするため（[ADR-0007](docs/adr/0007-pyside6-panel-ports-and-adapters.md)）

## セキュリティに関する注意

Scene Doctorは検証対象の.hipファイルを「出所が既知の信頼済み入力」として扱います。Houdini自体がPythonノードや式を含む.hipファイルを開いた時点でコードを実行しうるため、出所不明の.hipファイルは開かないでください。Scene Doctor自身は以下を一切行いません。

- `yaml.safe_load`以外でのYAML読込
- `exec`/`eval`による動的コード実行
- シーンファイルの暗黙的な書き換え（`Apply Rename Candidates`以外）

## ライセンス

MIT License（[LICENSE](LICENSE)参照）
