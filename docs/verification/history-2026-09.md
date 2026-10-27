# 実機検証の履歴(2026-09)

README から移した、最初の実機検証(Houdini Indie 22.0.429、手動・RPC 経由)の記録。**当時の記録なので、現在の挙動とは違う箇所がある**(例: PyYAML は、いまは配布物に同梱する。HDA は、`hda/build_hda.py` で作る)。最新の検証は [houdini-22.0.466.md](houdini-22.0.466.md)。

## PySide6パネル 実機検証結果（2026-09-08実施）

Houdini本体（Houdini Indie 22.0.429）に実際にドッキングパネルを起動し、Run Checks・行クリックでの
ノード選択ジャンプ・severity/categoryフィルタ・Export CSV/JSONの全機能を動作確認した（houdini_mcpの
HTTPブリッジが接続不能だったため、hrpycへ直接rpyc接続し`hdefereval.executeInMainThreadWithResult()`
経由でHoudini本体のメインスレッド上でパネルを操作する形で検証した）。

| 発見箇所 | 症状 | 原因 | 対応 |
|---|---|---|---|
| `launch_panel()`の呼び出しスレッド | Houdini本体が応答不能になった（再起動が必要になった） | rpycのバックグラウンドディスパッチスレッドから直接`launch_panel()`を呼び出し、QWidgetをメインスレッド以外で生成・表示してしまった | `hdefereval.executeInMainThreadWithResult()`でメインスレッドにマーシャリングして呼び出すよう検証方法を修正。通常のユーザー操作（Python Shell/shelf toolからの実行）は元々メインスレッド上で実行されるため、この問題は発生しない。READMEに注意書きとして明記 |
| ノード探索範囲 | 意図的に壊した2つのgeoノードのうち、Displayフラグが立つ方（1つ）しか検査されなかった | 既知の制限事項として設計時から文書化済み（v1の単純化仕様）。実機で再現・再確認した | 対応不要（既知の制限として明記済み、[既知の制限事項](#既知の制限事項)参照） |

修正後、`/obj/geo1`配下に未接続ノード（`stray_sphere`）を仕込んだシーンで`Run Checks`を実行し、
1件の`unconnected_node`違反を正しく検出・ツリー表示した。違反行をクリックすると
`hou.selectedNodes()`が対象ノード1件を正しく返すことを確認し、`severity_filter`を`error`に
切り替えると該当0件（実際にerror severityの違反が存在しないため）、`All`に戻すと2件（2つ目の
未接続ノードを追加した状態）に正しく増減することを確認した。Export CSV/JSONも実際に
`/tmp/`へファイルを書き出し、内容が`report_to_csv_rows`/`report_to_json`の出力と一致することを
確認した。

## 実機検証結果（2026-09-07実施、TC-023 / TC-024）

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

## HDA実機検証結果（2026-09-07実施）

`hda/SceneDoctor.hdalc`をHoudini 22.0上で実際に構築し、Run All Checks / Export CSV/JSON / Apply Rename Candidatesの全ボタンを動作確認した（`hda/scene_doctor_demo.hip`にテストシーンを保存）。

**重要な設計変更**: 当初`null`SOPをベースにHDA化しようとしたが、`node.canCreateDigitalAsset()`が`False`を返し変換不能だった（Houdiniの制約上、リーフ型のSOPはHDA化できず、`subnet`のようなコンテナ型のみが変換可能）。`subnet`ベースに変更して解決した（[ADR-0005](docs/adr/0005-hda-subnet-base.md)）。

さらに実機検証で2件のバグを発見・修正した。

| 発見箇所 | 症状 | 原因 | 対応 |
|---|---|---|---|
| `Run All Checks`ボタン | `No module named 'yaml'` | hython同梱Pythonにpyyaml未同梱 | PythonModuleが`.venv`のsite-packagesをフォールバックで検索するように変更（本番運用では`hython -m pip install pyyaml`を推奨） |
| 同一バッチ内の複数naming違反 | `box1`と`box2`が両方とも`geo_001`を提案（実際の適用時はHoudini側のunique_name機構で衝突は避けられるが、レポート上の表示が不正確） | `generate_rename_candidate`が「既存ノード名」のみを避け、「このバッチ内で既に提案済みの候補」を考慮していなかった | 提案するたびに候補名を`reserved_names`集合へ追加し、以降の候補生成で回避するよう修正（`checks/naming.py`、テストケース追加済み） |

`Apply Rename Candidates`実行後、`box1`→`geo_001`、`box2_unconnected`→`geo_002`と重複なくリネームされたことを実機で確認した。

`hda/python_module_source.py`にPythonModuleセクションの可読コピーを同梱している（`.hdalc`本体はバイナリのためdiffが読めないことへの対策）。
