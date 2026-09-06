# ADR-0002: PDG（TOPs）によるバッチ処理

## Status
Accepted (2026-09-07)

## Context
複数の.hipファイルを一括検証する際、シェルスクリプトでのループ実行でも実現できるが、
依存関係グラフに基づくタスクスケジューリング・失敗時の部分再実行・進捗の可視化を
自前で実装するコストが大きい。

## Decision
PDG（TOPs）でバッチ処理ネットワークを構築する（`pdg/batch_topnet.hip`）。
File Pattern TOPで対象ファイルを列挙し、Python Script TOPが`hython scene_doctor_cli.py`を
サブプロセスとして起動する。ワークアイテム由来の文字列はサブプロセスの固定引数としてのみ
渡し、`exec`/`eval`には一切渡さない（SEC-002）。

## Consequences
良い: 依存関係グラフによるスケジューリング、失敗ワークアイテムのみの再Cookが標準機能で使える
悪い: PDGネットワーク自体の動作確認はHoudini実機でのみ可能（このリポジトリのCIではカバーできない）

## Alternatives Considered
- シェルスクリプト + GNU parallel: 依存関係表現が弱く、失敗時の部分再実行が自前実装になるため却下
