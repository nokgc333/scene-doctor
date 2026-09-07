# ADR-0006: PDGネットワークのcook実行はHoudini UI上での手動操作を前提とする

## Status
Accepted (2026-09-07)

## Context
`pdg/batch_topnet.hip`のネットワーク構成・各ノードのスクリプトは仕様書§10.1の設計通りに
Houdini上で構築した（File Pattern → Python Script(run_scene_doctor) → Wait For All →
Python Script(aggregate_reports)）。File Pattern単体のcook（ファイル検出）は正しく動作し、
1件のワークアイテムを検出・cook成功させることを確認した。

しかし、`houdini_mcp`（hrpycベースのRPCブリッジ、実装検証専用に使用しているツール）経由で
`cookOutputWorkItems()`等のPDG cook APIを呼び出しても、下流ノードへワークアイテムが
伝播しない（エラーは出ないが0件のまま）という事象に遭遇した。PDGのcook処理はHoudini内部で
非同期スケジューラ・イベントループを利用しており、RPC越しの同期呼び出しではこの非同期完了待ちが
正しく機能しない構造的な制約がある可能性が高いと判断した（HDAのボタン実行のような単純な
同期呼び出しでは問題が起きなかったことから、PDG特有の問題と考えられる）。

## Decision
`pdg/batch_topnet.hip`はネットワーク構成・スクリプトを完成させた状態で保存し、
実際のcook実行（バッチ処理の動作確認）はHoudini UI上でのTOPネットワークペインからの
手動操作（Cookボタンのクリック）を前提とする。これは仕様書§11.3 RB-002
「Houdini上でHDAが期待通り動かない場合」の運用方針、および要件定義書TC-018〜020が
そもそも「手動確認」に区分されていたことと整合する。

## Consequences
良い: ネットワーク設計・実装自体はscene_doctor_cli.pyの実行ロジックを流用しており、
      CLI単体（`hython scene_doctor_cli.py`のネイティブ実行）は既に実機検証済みのため、
      PDG層は「複数ファイルへのループ実行」という薄い制御層に過ぎず、リスクは限定的
悪い: PDGバッチ処理の自動E2Eテストが（このAI開発支援環境では）行えない。
      ユーザー自身がHoudini UIで一度cookを実行し、動作を確認する必要がある

## Alternatives Considered
- RPC経由でのcook追求を継続する: 複数のAPI（cookOutputWorkItems, generateStaticWorkItems,
  GraphContext.cook等）を試したが解決に至らず、時間対効果が見合わないと判断し中止した
- PDGを廃止しシェルループに置き換える: ADR-0002の判断根拠（依存関係グラフによる
  スケジューリング、失敗ワークアイテムの部分再実行）を失うため却下
