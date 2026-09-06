# ADR-0001: Ports & Adapters によるhou依存の分離

## Status
Accepted (2026-09-07)

## Context
Scene DoctorはHoudini上で動作するツールだが、検証ロジック（非多様体判定・命名規則照合等）自体は
Houdiniの`hou`モジュールに依存しない純粋なアルゴリズムである。しかし`hou`はHoudini同梱の
Python（hython）でしかimportできず、通常のpytest/venv環境では利用できない。

## Decision
`interfaces.py`にGeometryLike/NodeLikeのProtocol（構造的部分型）を定義し、
`checks/`配下のモジュールはこのProtocolのみに依存させる。実`hou`への依存は
`adapters/hou_adapter.py`に完全に閉じ込め、CLIエントリポイント（`scene_doctor_cli.py`）の
`main()`内でのみ遅延importする。

## Consequences
良い: `checks/`・`rules.py`・`report.py`・CLIのオーケストレーションロジックは、
      Houdiniがインストールされていない環境（このリポジトリのCI含む）でも
      `tests/fakes.py`の純粋Pythonフェイクを使って完全にテストできる
悪い: `adapters/hou_adapter.py`自体はCIで検証できず、実際のHoudini上での手動確認
      （TC-023, TC-024）に頼らざるを得ない

## Alternatives Considered
- hou全体をモック化するテストフレームワークの導入: モックの保守コストが高く、
  実際のhou APIとの乖離（モックのズレ）に気づきにくいため却下
