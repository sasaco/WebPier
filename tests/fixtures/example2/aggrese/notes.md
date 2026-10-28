# Aggre-SE のプロジェクトXML の期待値（決定49）

`線路方向.xml`・`線路直角方向.xml` は、Example2 の Aggre-SE（Docu-SE）のプロジェクトXMLを Aggre-SE 自身に保存し直させたもので、WebPier の書出しを使わずに作った。

## 元

| ファイル | 元 | SHA256 |
|---|---|---|
| `線路方向.xml` | `.claude/docs/Example橋脚2/10_線路(耐震)/P1_線路.xml` | `7eacba3d920e277c67980dc5aaacc067c5ae4d40399be025af57b79a69dfb84d` |
| `線路直角方向.xml` | `.claude/docs/Example橋脚2/11_直角(耐震)/P1_直角.xml` | `a8a3b20adaa37800f9c0b53535a92943e304b3fb26fb36d63364dbc0403ea06e` |

照査条件（スペクトルⅠ,Ⅱ両方・C地域・G2地盤・液状化 5<PL<20・M6.5 なし・α=1.000・η(x) なし、照査項目 ④ 以外、部材照査タイプ 2・せん断耐力式 ①、損傷レベルの制限値（柱の復旧性は下の 2026-10-28 を除く）、直接基礎の制限値は空欄、カスタム仕様）、せん断スパン La（7600・10350）、直接基礎の照査位置の節点（7・8）は、元の値のまま。

## 手で変えたこと（2026-10-18）

1. ケースごとの配列（`dgCaseList_1`〜`9`、`analysisObject`、`SnapDBPath`、`dgEkijoCase1`・`21`・`2`）を、元の101件から先頭の50件にした。いまの Aggre-SE の `Option_ケース数` は50で、新しく作るファイルの配列は50件になる。
2. `SnapDBPath` を、WebPier の JRSNAP のフォルダーの DB1 の XML からの相対パスにした。
   - 線路方向：`線路方向_JRSNAP/線路方向(Case1_ρm10_αf1_正向).DB1`
   - 線路直角方向：`線路直角方向_JRSNAP/線路直角方向(Case1_ρm10_αf1_正向).DB1`、`…(Case2_ρm10_αf1_正向).DB1`
3. 線路直角方向は WebPier の組合せが2つ（上り線・下り線）で、元は1ケースなので、Case2 の照査項目（`dgCaseList_1`〜`9` の2件目）を Case1 と同じにした。

## 手で変えたこと（2026-10-22、決定76）

組合せが照査パターン（ρm, αf）の4つずつになり（線路方向 4 Case、線路直角方向 8 Case。Case5〜8 は下り線の逆向）、照査項目が Case ごとに変わったので、上のファイルの `dgCaseList_1`〜`9` の先頭の Case と `SnapDBPath` を、owner が手で直して Aggre-SE で保存した `post/線路直角方向.xml`（2026-10-22。WebPier の書出しではない）から写した。

- 線路直角方向：その8 Case の照査項目と DB1 のパス（`線路直角方向_JRSNAP/線路直角方向(Case1_ρm10_αf1_正向).DB1` 〜 `(Case8_ρm12_αf2_逆向).DB1`）。
- 線路方向：その Case1〜4（上り線・正向。照査項目は照査パターンで決まり載荷の向きによらない）の照査項目と、名前を `線路方向` にした DB1 のパス（`線路方向_JRSNAP/線路方向(Case1_ρm10_αf1_正向).DB1` 〜 `(Case4_ρm12_αf2_正向).DB1`）。

写したあとのファイルを下の手順で保存し直し、バイト列が変わらないことを確かめた（SHA256 線路方向 `4eb1c3fdc8610bf0fdbb8187d9bf3827b29448da441b5f234af13bd6e81f166e`、線路直角方向 `9559069267d7e25b476efb79d9356dbc849fe3225f8f013660bb15977d4c544d`）。

## 手で変えたこと（2026-10-28、決定115）

両方のファイルの `_dgLimitLevel`（損傷レベルの制限値 復旧性）の2番目（部材照査タイプ 2＝柱）を `2` から `3` にした（603 行目）。見本の値は 2 で、WebPier の定めだけが違う。

下の手順で保存し直し、バイト列が変わらないことを確かめた（SHA256 線路方向 `18641111e622c3ba548f46c386be3379b7191d9870c84e4b322ead9791c36f72`、線路直角方向 `788f377715c523e316a8173ff3e0e85f7bf605ef887ede422b34557f384a5a81`）。

## Aggre-SE での保存し直し

手で変えたファイルを、`scripts/aggrese_project_roundtrip.cs`（Aggre-SE の `Input.SetXmData` → `applyVersion` → `Input.GetXmlData` → Shift-JIS の `StreamWriter`）で保存し直した。使った Aggre-SE は structural-mcp の `Batch` サブモジュール（コミット `14ed213`）の `Aggre-SE/Headless/bin/Release/Batch.exe`（FileVersion 5.3.0.1）。

保存し直しで変わった書式は次のとおり。
- 名前空間の宣言の順（`xmlns:xsi` が先）
- `Version` が `5.3.0.1`
- `_dgLimitLevel_SIJI`（-1）と `_ParagraphLength`・`ParagraphLength` が加わった
