# Houdini 22.0.466(Indie)での実機検証

> 実施日: 2026-10-28
> 環境: macOS(Apple Silicon)/ Steam 版 Houdini Indie 22.0.466 の `hython`(Python 3.13.10)
> 対象: アダプタ(`scene_doctor/adapters/hou_adapter.py`)・CLI・HDA の PythonModule・共通レポート形式

## 手順(チェックリスト)

1. Steam を起動する(Houdini Indie は、Steam が無いとライセンスを取れない)
2. PyYAML を、`hython` の Python が読める場所に置く(例: `PYTHONPATH=<venv>/lib/python3.12/site-packages`。`hython` には PyYAML が入っていない。配布物は、同梱する)
3. 実行: `PYTHONPATH=... hython scripts/verify_houdini.py`
4. 出力の `CHECK` 行が、すべて `PASS` であることを確かめる(出力が終わっても `hython` が終了しないことがある。手で止めてよい)
5. `hda/SceneDoctor.hdalc` を作り直したときは、先に `hython hda/build_hda.py` を実行する

スクリプトが、一時フォルダに、次のシーンを作って検査する: `geo`(`BadGeoName`)の中に、`box`・8 角形の `circle`(N-gon)・`merge`(表示フラグ)・未接続の `null`・規則に合わない名前の `xform`(`TransformBad`)。

## 期待する結果と、実際の結果

| 項目 | 期待 | 結果 |
| --- | --- | --- |
| CLI の終了コード | 違反があるので 1 | PASS |
| N-gon・未接続ノード・命名の違反を検出 | 3 種類とも検出される | PASS |
| 命名違反に、リネーム候補がある | 候補がある | PASS |
| 共通レポート(`--format common`) | `schema_version` `tool` `findings` を持つ | PASS |
| 既存のレポートを上書きしない | `--force` なしで終了コード 16 | PASS |
| HDA の `Run All Checks` | `violation_count` に件数が入り、`results` に一覧が出る | PASS |
| HDA に、特定の利用者のパスが無い | `/Users/` を含まない | PASS |

## 実行ログ

```text
HOUDINI_VERSION 22.0.466
PYTHON_VERSION 3.13.10
CHECK cli_exits_with_violations_found PASS exit=1
CHECK ngon_is_detected PASS ['naming', 'ngon', 'unconnected_node']
CHECK unconnected_node_is_detected PASS 
CHECK naming_violation_has_a_rename_candidate PASS 
CHECK common_report_has_the_shared_shape PASS <tmp>/scene.hip
CHECK existing_report_is_not_overwritten_without_force PASS exit=16
CHECK hda_run_checks_fills_the_count PASS count=5
CHECK hda_results_text_lists_violations PASS 5 violation(s) found in /obj/BadGeoName
CHECK hda_has_no_hardcoded_user_path PASS 
```

## 検証した版の一覧

| Houdini | Python | 実施 | 結果 |
| --- | --- | --- | --- |
| 22.0.466 | 3.13.10 | 2026-10-28 | 16/16 PASS(この記録。追加した品質・参照・LOP の検査を含む) |
| 22.0.429 | 3.13 | 2026-09(README「実機検証結果」) | 手動で、ジオメトリ・ノード・命名・HDA・PDG・パネルを確認 |
| 19.5 / 20.0 / 20.5 / 21.0 | - | 未実施 | この環境に、インストールされていない。版を足すときは、上の手順を実行し、このフォルダに `houdini-<版>.md` を追加し、この表に 1 行足す |

## 見つかったこと

1. **`hda/SceneDoctor.hdalc` に、パラメーターが無かった**: リポジトリの HDA は、パラメーターインターフェース(トグル・ボタン・結果)を持たず、PythonModule のコールバックが `evalParm` で失敗した。`hda/build_hda.py` で、パラメーターとボタンつきの HDA を、一から作り直せるようにした(HDA はバイナリで差分が読めないため、作るスクリプトを正本にする)。
2. **`hython` に PyYAML が入っていない**: 開発中は、リポジトリの venv の場所を決め打ちして回避していた(利用者のパスが HDA に埋め込まれていた)。配布物は、PyYAML を同梱する(SD-06)。
3. **HDA の PythonModule と PDG のスクリプトに、特定の利用者のホームフォルダが書かれていた**: 環境変数 `SCENE_DOCTOR_HOME` と、`$HFS/bin/hython` に置き換えた(テストで、`/Users/` を含まないことを強制)。
4. **`PYTHONPATH` に `usd-core` を含む venv を渡すと、Houdini の `pxr` と衝突する**: `RuntimeError: extension class wrapper for base class ... UsdTyped has not been created yet` になり、`--lop` が失敗した。`hython` には、PyYAML だけを置いたフォルダを渡す(`pxr` は Houdini のものを使う)。
5. **`defaultPrim` が存在しない Prim を指していても、`HasDefaultPrim()` は真になる**: サンプルの USD で見つかり、検査を足した(`usd_default_prim`)。

## 追加した検査の実機結果(品質・参照・LOP)

`scripts/verify_houdini.py` の後半。UV を削除した 2 つの box の結合(重複した点)、存在しないキャッシュを指す `file` ノード、`/stage/sphere1`(LOP)で確かめた。

```
CHECK quality_cli_exits_with_violations_found PASS exit=1
CHECK missing_uv_is_detected PASS ['duplicate_point', 'hardcoded_path', 'missing_file', 'missing_uv', 'unconnected_node']
CHECK duplicate_point_is_detected PASS
CHECK missing_cache_file_is_detected PASS
CHECK lop_stage_is_inspected PASS exit=1 ['usd_default_prim']
CHECK lop_default_prim_is_checked PASS
```
