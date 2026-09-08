# ADR-0007: PySide6カスタムパネルにもPorts & Adaptersを適用する

## Status
Accepted (2026-09-08)

## Context
既存のHDA（`hda/SceneDoctor.hdalc`）はパラメータUI（Run All Checks / Export /
Apply Renameのボタンのみ）であり、違反一覧をツリー表示してクリックでノード選択に
ジャンプできるような、実務のTA/パイプラインTDが作る本格的なカスタムUIではない。
Houdiniは`PySide6`を標準同梱しており（`hou.qt`モジュール経由）、これを使った
ドッキングパネルを追加することで、より実務に近いツール構成にする。

しかし`hou`と同様、`hou.qt`（およびHoudini本体へのドッキング処理）はHoudini同梱の
Pythonでしか動作せず、通常のpytest/venv環境では検証できない。一方でPySide6自体は
`pip install PySide6`で通常のvenvにも導入可能で、`QT_QPA_PLATFORM=offscreen`環境変数を
使えばヘッドレスでも実ウィジェットを生成・操作できる。

## Decision
GUI層を2段に分離する（ADR-0001のPorts & Adaptersと同じ思想）。

- `scene_doctor/ui/panel_view_model.py`: `SceneReport`を表示用の`ViolationRow`に変換する
  純粋関数・dataclassのみ。`PySide6`・`hou`いずれもimportしない。通常のpytestで
  100%近いカバレッジを狙う。
- `scene_doctor/ui/panel.py`: `PySide6`の`QDockWidget`サブクラス`SceneDoctorPanel`。
  `hou`は一切importせず、`run_checks_callback` / `select_node_callback` /
  `export_callback`の3つをコンストラクタで注入される設計にする。これにより
  `QT_QPA_PLATFORM=offscreen`のヘッドレスQApplication上で、本物のPySide6ウィジェットを
  pytest-qtの`qtbot`で操作しながらテストできる（フェイクのcallbackを注入するだけで
  Houdiniなしでもボタンクリック・行選択・フィルタ変更の実際の挙動を検証できる）。
- `scene_doctor/adapters/houdini_panel_launch.py`: `hou`・`hou.qt`への実依存をここに
  閉じ込める。`hou_adapter.py`と同じ理由でCIの単体テスト・カバレッジ・mypyの対象から
  除外し（`pyproject.toml`の`omit` / `exclude`に追加）、実機Houdini上でのみ検証可能とする。

パネルは出力先パスの決定にモーダルな`QFileDialog`を使わない（`export_path_edit`という
テキスト入力欄を持ち、空文字であれば呼び出し側のcallbackが既定パスを決める）。
`QFileDialog.getSaveFileName()`はネイティブの保存ダイアログを表示する同期呼び出しであり、
`QT_QPA_PLATFORM=offscreen`環境でクリックをシミュレートするテスト中に実際にハングすることを
このセッションの開発中に確認した（TDDのGREENフェーズで検出）。

## Consequences
良い: `panel_view_model.py`と`panel.py`の両方をHoudiniなしで、しかも`panel.py`は
      モックではなく本物のPySide6ウィジェットとしてTDDできる（このセッションで72テスト、
      `panel.py`/`panel_view_model.py`ともカバレッジ100%を達成）。
悪い: `houdini_panel_launch.py`自体（実際のドッキング処理・ノード選択・エクスポート）は
      実機Houdini上での手動確認に頼らざるを得ない（このセッションでは未実施、README
      「既知の制限事項」参照）。
      また`hou.qt`の正確なドッキングAPI（`hou.ui.curDesktop()`経由のタブ統合等）は
      バージョン差異があり、`launch_panel()`は`hou.qt.mainWindow()`を親にした
      フローティングウィンドウ表示という簡易な実装に留めている。

## Alternatives Considered
- `panel.py`もモック（`unittest.mock`）でQt呼び出しを検証する: 実際のシグナル/スロット
  接続やレイアウトの取りこぼしに気づけないため却下し、本物のウィジェット + `pytest-qt`を
  採用した（ADR-0001でhouモックを却下したのと同じ理由）。
- `QFileDialog`をそのまま使い、テストでは`monkeypatch`で差し替える: 可能だが、
  `panel.py`のインターフェースを不必要に複雑にするため、出力先はテキスト入力欄に
  委ねるシンプルな設計を優先した。
