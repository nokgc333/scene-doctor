# サンプル

`broken_asset.usda` は、わざと壊した USD(存在しない既定 Prim・解決できない参照・マテリアルと UV の無いメッシュ)。Houdini なしで検査できる。

```bash
python scene_doctor_cli.py --usd docs/samples/broken_asset.usda --out docs/samples/broken_asset_report --format all --force --redact-home
```

`broken_asset_report.{csv,json,common.json}` が、その出力(自分のホームフォルダは `~` に置き換えてある)。
