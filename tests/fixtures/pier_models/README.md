# 境界節点モデルの完全入力サンプル

この2ファイルは通常の`schema_version: 1`入力です。既存の独立Excel検証fixtureから完全入力をコピーし、`出典.モデル検証サンプル`だけを追記しました。原PDFの実測値ではなく、独立試験条件からの変更サンプルです。既存のoracleは更新していません。

| ファイル | 元fixtureのケース | 確認する形状 |
|---|---|---|
| [parapet-asymmetric.json](parapet-asymmetric.json) | `reaction_excel_oracle.json`の`pedestal_nonzero` | H1=.4、B2=.25、B3=.6、W2=.3、W3=.9。偏心パラペットとB7≠B9・W7≠W9の非対称基礎 |
| [asymmetric-footing.json](asymmetric-footing.json) | 同`geometry_water` | H5=.6、H6=1.8、B7=.35/B9=.2、W7=.4/W9=.25。重心高Single=1.1779999732971191 m |

製品の計算parserはJSONに明示された数値B9を優先し、`0`やB7と異なる値も採用します。B9が欠落または`null`の場合だけB7を使用します。両サンプルをそのままCLIへ渡すとB7=.35/B9=.2が維持され、B7≠B9とW7≠W9の非対称形状を実際の計算経路で検証できます。

編集アプリのB9はB7からの自動更新欄です。例えばB7=.35/B9=.2のサンプルをGUIで開いて保存すると、保存されるB9は.35へ更新されます。B7≠B9の元サンプルを維持して検証する場合は、GUIで保存する前のJSONをCLIへ直接渡してください。GUIで編集する場合は先に作業コピーを作成し、保存によってこの寸法条件が変わることを確認してください。

過去のtyped adapterは、当時の入力で取得した元数式snapshotを照合する試験に限って使用します。サンプル本試験では原JSONを実際の0500/0600入力parserへ渡し、0610/0620と全段階CLIの出力を検証します。サンプルの形状や重心を確認するためにparserを置き換えたり、期待値をB9=B7の条件へ変更したりしません。

数値入力は元ケースと同じで、過去に保存されたA・D支点の合計も保持しています。現在の入力契約ではこれらを明示入力として使用します。従来の独立Excel数値と全荷重を比べる試験は`tests/legacy_reaction_oracle.py`で過去のA=B・D=C条件を別途再現します。このサンプルの試験では入力を変更せず、独立した形状・自重・重心値を照合します。

[expectations.json](expectations.json)には両方向の全節点・role・接続・断面・支持点・荷重参照・元行を固定しています。計画の寸法と明示的な合流表から独立に作成し、製品のモデル生成関数や計算器から逆生成していません。通常形、偏心H1、非対称基礎、H2/H3の0・正4構成、hG=0/基礎天端、中心H1、1e-12 m偏心H1を含みます。`geometry_overrides`は元ケースへ適用する寸法変更、`hg_override`は0600引継ぎの人工的な端点条件です。`directions.b`が0610、`directions.w`が0620です。

既定主幹の上からの高さは11.2/10.025/9.8/2/1/0 mです。パラペット条件では中心xがB=-.5 m、W=-3.375 m、上端y=11.6 m、断面積=.54 m²、断面二次モーメント=.0162/.03645 m⁴となります。非対称基礎サンプルをCLIへ直接渡した場合の主幹は11.6/10.425/10.2/2.4/1.1779999732971191/0 mです。フーチング重心高はB9=.2を採用した0600のSingle受渡し値`1.1779999732971191 m`を保持します。旧セルの左からの加算値（例:11.200000000000001）と実節点の一度だけ累積した座標は区別しています。

リポジトリのルートから一時出力へ再実行できます。

```powershell
uv run --project "P7橋脚" --locked python "P7橋脚/run_design.py" --stage all --input "P7橋脚/tests/fixtures/pier_models/parapet-asymmetric.json" --output-dir "tmp/pier-model-samples/parapet"
uv run --project "P7橋脚" --locked python "P7橋脚/run_design.py" --stage all --input "P7橋脚/tests/fixtures/pier_models/asymmetric-footing.json" --output-dir "tmp/pier-model-samples/footing"
uv run --project "P7橋脚" --locked --group dev pytest "P7橋脚/tests/test_pier_model_samples.py" "P7橋脚/tests/test_frame_model.py" -q
```

再実行で同名の一時成果物を更新する場合は`--overwrite`を追加します。編集アプリで開く場合は`edit_input.py --input`にサンプルのパスを指定し、「名前を付けて保存」で作業コピーを作ってください。編集アプリの「保存して計算・PDF出力」は本番の`P7橋脚/output`へ出力するため、上記一時出力の確認にはCLIを使用します。
