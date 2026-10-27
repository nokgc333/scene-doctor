# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)、版は [Semantic Versioning](https://semver.org/) に従う。
タグ `vX.Y.Z` を打つと、リリース用ワークフローが zip を作って GitHub Releases に添付する。

## [0.2.0] - 2026-10-28

### Added
- 検査: UV の欠落・反転した法線・重複した点・存在しない/絶対パスのキャッシュ・古い HDA の版。
- USD(Solaris)のステージの検査(`--usd` は Houdini 不要、`--lop` は LOP ノード)。
- CLI: `--fail-on`、`--skip`、`--force`、`--redact-home`、`--list-rules`、`--format common`(共通レポート形式)。
- 実機(Houdini 22.0.466)での検証スクリプトと記録、大規模シーンの計測。
- 配布用の zip、Houdini package、インストーラー。

### Changed
- 終了コードを整理(15 = Houdini なし、16 = 出力先が既にある)。
- HDA と PDG のスクリプトから、特定の利用者のパスを取り除き、`SCENE_DOCTOR_HOME` で解決する。

## [0.1.0] - 2026-09

- 最初の版: ジオメトリ(ngon・ゼロ面積・非多様体)、ノード構造、命名規則の検査。CLI・HDA・PDG・PySide6 パネル。
