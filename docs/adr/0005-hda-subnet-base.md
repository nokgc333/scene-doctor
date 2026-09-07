# ADR-0005: HDAのベースノードにsubnetを使用する

## Status
Accepted (2026-09-07)

## Context
Scene DoctorのHDAを`null`ノード（パラメータのみ持つ軽量なユーティリティノード）ベースで
作成しようとしたが、実機（Houdini 22.0）で`node.canCreateDigitalAsset()`が`False`を返し、
`createDigitalAsset()`が`hou.OperationFailed: The specified node cannot be converted to a
digital asset.`で失敗した。

## Decision
`subnet`（コンテナ型のSOPノード、内部に子ネットワークを持てる）をベースノードとして採用する。
`canCreateDigitalAsset()`で`True`が返ることを確認した上でHDA化した。

## Consequences
良い: Houdiniの標準的なHDA作成パターン（コンテナ型ノードをベースにする）に沿っている
悪い: `null`ベースより内部構造がわずかに複雑になる（今回は内部ネットワークを実質空のまま使用）

## Alternatives Considered
- `null`ベース: 実機検証で`canCreateDigitalAsset() == False`と判明し不可能だった
- `python`ベース（Python SOP）: 検討したが、subnetの方がHDAの標準的な作法に近いため採用しなかった
