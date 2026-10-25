---
name: webpier-footing
description: WebPier の 0800・0810・0820 フーチングの照査（決定60、CONTEXT.md「フーチングの応答値」「Rvd到達ステップ」「フーチングの断面照査」）を扱う。0800 の応答値の算定（反力 CSV の断面照査用ピックアップ 1〜3、Aggre-SE の runner が返す直接基礎のステップ表と Rvd到達ステップ、地盤反力形状 Case 1〜4、両側の張出し、自重・浮力、Md・Vd・La、webpier/calc/footing.py）、フーチングの配筋の入力（footing_rebar.py）、0810・0820 の Capacita への断面力入力モードの WDJ（footing_check.py・export/capacita/footing_wdj.py）、計算書 12.1〜12.9（reporting/stages/footing*.py）、原資料 0700_線路フーチング.xls の式の読み方、本物の4つの runner での受入（scripts/accept_footing.py）に使う。見本 12_フーチング.pdf 244〜267 ページと値が合わない、Rvd に到達しない、ピックアップや Case の選び方が違う、q2 や分布の式を変えるときにも使う。基礎の安定計算（0612・0622）は webpier-foundation、Aggre-SE の runner は structural-aggrese（WebPier の呼び出しは webpier-aggrese）、Capacita は webpier-capacita（Capacita そのものは structural-capacita）。
---

# フーチングの照査（0800・0810・0820）

0800 は線路方向・線路直角方向のフーチングの応答値（12.1）を WebPier が計算して印刷し、0810・0820 は方向ごとの断面照査（12.2〜12.5／12.6〜12.9。基準は RC標準 R5、決定73）を Capacita に任せてページを差し込む（決定60、ADR-0008）。3段階とも出力項目 `footing` で、両方向の骨組解析と静的非線形解析を選んだときだけ選べる（決定72）。0612・0622（安定計算）の列は流用しない：同じ反力 CSV を**断面照査用のピックアップ**で読み直し、地震時は JRSNAP の Rvd到達ステップを使う。

## 置き場所

| もの | 場所 |
|---|---|
| 応答値の計算（`prepare` は入力から、`complete` は反力とステップ表で） | `webpier/calc/footing.py`（`distribution`・`effective_width`・`self_weight`・`buoyancy`・`ground_reaction`・`section_forces`・`seismic_action`、`calculate_footing`／`complete_footing`） |
| 配筋の読み取り | `webpier/calc/footing_rebar.py`（`footing_reinforcement(pier, direction)`：下側の主鉄筋 1 m 当たりの本数、中心かぶり、スターラップ） |
| Capacita の条件と断面力 | `webpier/calc/footing_check.py`（`calculate_footing_check`、`REPORT_SECTIONS` 6節（最後が `bending_rebar_amount`）、`Forces(column, md, vd, la mm)`）、WDJ は `webpier/export/capacita/footing_wdj.py` |
| 0612 と共有する式 | `webpier/calc/foundation_check.py` の `bearing_capacity`／`Capacity`（qvd・qd・Mmd）と `pick`（反力の極値の選び方） |
| ステップ表 | `webpier/pipeline/aggrese.py` の `FOUNDATION_STEPS_COLUMNS`・`foundation_steps(content)`、0711・0721 が `post/線路方向_Aggre-SE_直接基礎.csv`・`post/線路直角方向_Aggre-SE_直接基礎.csv` に公開（kind `steps`） |
| 登録表・生成 | `webpier/pipeline/stages.py` の `_footing`（0800、依存 0500・0610・0612・0620・0622・0711・0721）と `_footing_check`（0810・0820、依存 0800、`complete=` で WDJ を組む）、`generate.py` の `_completion_files`（依存段階の解析のファイルを `"<stage>/<kind>"` で渡す） |
| 帳票 | `webpier/reporting/stages/footing.py`（12.1）、`footing_figures.py`（Case 1〜4・有効幅・地盤反力・自重の図）、`footing_check.py`（12.2〜12.9、`Chapter(12, 2)`・`Chapter(12, 6)` で節番号） |
| 見本の転記と手計算 | `tests/fixtures/example2/footing.json`（見本の値）、`footing_hand.json`（正しい q2 での台形8列と地震時）、`footing_notes.md`（Excel の式の写し） |
| 受入（本物の FEMPython・JRSNAP・Aggre-SE・Capacita） | `scripts/accept_footing.py` → `tests/fixtures/acceptance/footing/{record.json, input.json}`、テスト `tests/acceptance/test_footing_acceptance.py` |
| 見本と原資料 | `.claude/docs/Example橋脚2/12_フーチング.pdf`（244〜267 ページ。12.1 は 244〜253、解説は 254〜266、Capacita 形式の表は 255・258・261・264・267）、`12_フーチング/0700_線路フーチング.xls`（シート `地盤反力 (1)`／`断面力 (1)` と `(2)`） |

## 原資料の読み方

- 式は Excel COM で読める（xlrd は値だけ）。PowerShell で `$xl = New-Object -ComObject Excel.Application; $wb = $xl.Workbooks.Open(<xls>, 0, $true); $ws.Range("S45").Formula`。終わりに `$wb.Close($false); $xl.Quit()`。Git Bash からは呼ばない。
- 見本 PDF は pymupdf でページを画像にして Read する（`uv run --project "." --locked python -X utf8 -c "import pymupdf; ..."`、80〜110 dpi で十分）。テキスト抽出は表の値が入り乱れるので図と表は画像で読む。
- `地盤反力 (1)` 45〜49 行の式：Case ＝ Md＞Mmd なら 4、三角形の頂点 2Vd／(3L(B/2−ex))＞qd なら 3、ex＞B/6 なら 2、他は 1。Case 1 は qd1・qd2＝Vd/(BL)(1±6ex/B)・X1＝B、Case 2 は頂点と X1＝2Vd/(qd1·L)、Case 3 は qd1＝qd・X2＝√(12B·Vd/(qd·L) − 12Vd²/(qd·L)² − 24Md/(qd·L))・X1＝Vd/(qd·L)−X2/2、Case 4 は qd1＝qd・X1＝Vd/(qd·L)。Mmd＝B·Vd/2 − Vd²/(2qd·L)（0612 と同じ）。
- `断面力 (1)` O63 の q2 ＝ `qd2 + (qd1 − qd2)·L1/X1` は qd2 側の縁から L1 の位置の値で、q1＝qd1 と組み合わせると台形の片端だけ反対側になる（対称な張出しでだけ辻褄が合う）。WebPier は `qd1 − (qd1 − qd2)·L1/X1`（owner 2026-10-19、ADR-0001）。このため安全性・使用性の W・x・M・Md・Vd・La は見本より大きい（線路 安全性 Vd最大 Md 760.74 → 799.16）。地震時（Case 4、一様ブロック）は一致する。
- 有効幅 be ＝ 柱幅 ＋ 2×min(直交方向の張出し, d)、d ＝ H6 − 下側主鉄筋の中心かぶり。上側（`断面力` 23 行、d/2）は印刷しない。直角方向の d は 2.573（見本は 0.125 で丸めた 2.575）。
- 浮力は底面の揚圧力（水位×L1×−10.0、水位は基礎下面から。`I96 = 1.08 + 2.7` が高水位 3.78）。安全性＝高水位、使用性・地震時＝平水位、低水位の行は印刷するだけ。

## 反力とステップ表の読み方（2026-10-19 に本物の runner で確認）

- 4列：安全性 Md最大＝ピックアップ 1 安全性（破壊）の |mz| 最大、安全性 Vd最大＝1 の fy 最大、使用性 短期＝2 耐久性 永久＋変動の fy 最大、長期＝3 永久作用の fy 最大。支点の節点は骨組の役割 `FOOTING_BOTTOM`、符号と丸めは 0612 と同じ（Vd＝−fy、Hd＝|fx|、Md＝|mz|、2桁）。
- ピックアップ 2・3 は fy が max 行と min 行で同じ（19506.36）で、mz が ±（水平力の向き違い）の2つある。`foundation_check.pick` は fy が同値なら |mz| の大きい行、さらに同じなら |fx| の大きい行を採る（owner 2026-10-19）。これで使用性の Md は見本（3327.13／3056.25）と一致する。先頭の行を採ると 2852.88／1887.75 になる。
- 使用性の Vd は 19506.36 で見本 19505.93 と 0.43 違う（見本の隠れ桁）。受入の許容差は使用性の Vd だけ 0.5 kN、他は 0.25。
- ステップ表（`foundation-steps.csv`）：`case_index, case_name, node, step, V, H, M, qvd, qd, Rvd, Mmd, plasticity`。SNAPDBLib が返す JRSNAP の値のまま（列と step の番号はスキル structural-aggrese 参照）。Rvd到達ステップは `V ≧ Rvd` の最初の行。Case ごとに求め、αf＝1.0 の Case（`case_index` は SnapDBPath の順＝0710・0720 の組合せの順。その組合せの αf で選ぶ）のうち |M| が最大の Case（決定76。αf＝2.0 は上部構造物の照査用で、基礎には使わない）。Vd＝V（0以下はエラー）、Hd＝|H|、Md＝|M|。見本 10-23・11-24 の「増分ステップ＝31／32」と同じ番号付け。
- Example2（`pre/input.json`、Df 4.70）の結果：線路方向は Case 1 のステップ 32（見本 31）、Vd 16825.97（一致）、Hd 5901.07／Md 54168.43（見本 5747.86／52784.78）。Df・γe2 の既知の差で1ステップ遅い。Aggre-SE の PIK（決定57、応答値までの包絡）は Md が約7%大きく、使わない（owner 2026-10-19）。
- 地震時の列の抵抗側は WebPier が求める：地盤抵抗係数 1.00（`FACTORS` の地震時）、γe2 は平水位、Df は 0612 と同じ表層厚。ステップ表の qd・Rvd は到達の判定にだけ使う。

## 張出し・配筋・Capacita

- 張出しは起点側・終点側（B7・B9／W7・W9、土かぶり df1・df2）の両方を計算し、Md の大きい側を採る（同じなら起点側）。結果JSONに両側と採った側（`chosen`）。計算書は採った側だけ。
- `鉄筋.フーチング`（決定60・68）：下面の方向ごとの主鉄筋 `faces.下.{線路,直角}`（1段目の径・ピッチ・芯かぶりと `inner_layers`（ピッチと同じ方向のひとつ前の段とのあき、径は1段目と同じ））。1 m 当たり 1000／pitch 本を小数2桁で丸め、端数を許す（1000／130 ＝ 7.69）。複数段は Capacita の段の割り方（総本数÷1段目の本数を倍精度で切り上げ）で段数に戻るものだけ表せる（6.67本/m の3段は入力エラー）。WDJ には `rebar_lines`・`rebar_space` を書く。芯かぶりは「指定」の `center_mm` か「自動」の純かぶり＋（`outer_direction` でない方向なら外側の方向の径）＋径/2、内側の段は前の段＋径＋あき。0800 の有効幅の有効高さは図心まで（`MainBars.centroid`、owner）。スターラップは `stirrups.{線路,直角}`（密度は `density_per_m`、間隔は 1000／`width_pitch_mm`。どちらも小数2桁）。材質は部材の `materials`（行ごとの材質はない）、`concrete_strength_mpa`、`aggregate_max_mm`（フーチング自身の値。柱の値は使わない。owner 2026-10-19）。上面の主鉄筋と上面の `outer_direction`（画面に出さない）は 0800〜0820 では読まない（0400 の構造細目と配筋図は上面も要る。決定73）。水掛かりの程度・ε'csd・機関・JR-001/004 は `柱の断面照査` と同じ。`pre/input.json` は見本の D25@125 中心 100・D29@125 中心 127・D16 2本/m@250・SD390・27・25。`tests/fixtures/inputs/current.json` のフーチングは決定73（8b6109f）から `pre/input.json` と同じ配筋（上面 D25@125 芯 79・104 を含む。Ex2 06 6.2）で、テストは `tests/pipeline/pipeline_support.py` の `footing_input`／`SAMPLE_FOOTING` で項目を上書きする。空欄から始めるテスト（エディタなど）は自分で空欄にする。
- Capacita への対応：安全性（破壊）の曲げ・せん断は安全性2列のうち Md の大きい列の Md・Vd・La（見本は Vd最大の列 760.7／675.1／1127）、耐久性の縁引張＝短期の Md、永久作用＝長期の Md、復旧性（地震時）＝地震時の Md・Vd・La、最小鉄筋量（行8 の Md8、決定73）＝長期の Md（Nd＝0、点1）。La は着目点に1つなので方向ごとに2点（「線路方向」「線路方向（地震時）」）。耐久性のせん断・使用性・使用性（損傷）は渡さない（その空の行の WD-408 は今も出る）。詳細は webpier-capacita スキルの「フーチングの断面照査」（断面力入力モードの WDJ の一般的な性質はスキル structural-capacita）。
- 受入での Capacita の耐力：線路方向 安全性 Mud 3670.5（見本 255 と一致）、Myd 3863.6；直角 Mud 4581.9／Myd 4808.1。

## 生成

- 入力の `outputs` で `footing` と使う項目（両方向の計算・骨組解析・静的非線形解析）を選び、`uv run --project "." --locked python -m webpier --overwrite`（4つの runner が `.env` に要る。JRSNAP を含むので数分）。使う項目の段階（0611・0612・0621・0622・0711・0721 ほか）も作り直して公開する（決定72）。
- 受入：`uv run --project "." --locked python -X utf8 scripts/accept_footing.py`（一時フォルダーに生成し、`output/`・`post/` は触らない）。`current.json` を変えると他の受入記録（0610〜0721、データ確認図）も SHA で落ちるので、各 `scripts/accept_*.py` を回し直す（JRSNAP の NDU と Aggre-SE のプロジェクトは `--overwrite` が要る）。
- 並行して別のセッションが作業しているときは CLI を避け、`render_footing`／`render_footing_check` で scratchpad に出す。

## 計算書

- 章の見出し（§12・12.1）は印刷しない。0800 の最初の見出しは「(1) 線路方向の計算」。0810 は 12.2 安全性の照査・12.3 耐久性の照査・12.4 復旧性（地震時）の照査・12.5 最小鉄筋量及び最大鉄筋量（見出しだけ。Capacita の頁が 3 頁）、0820 は 12.6〜12.9（同じ題で番号を続ける。決定73 の前は 12.2〜12.4／12.5〜12.7）。0400 の参照先（12.5・12.3／12.9・12.7）は `reporting/stages/detailing.py` の `FOOTING_SECTIONS` が持つので、節を変えたらそちらも直す。
- 見出しに条文番号は付けない（R5 への切替で外した）。12.1 の【ＲＣ標準 13.6.3】は切替の対象外なので残す。解説は R5 の方法（曲げひび割れの流れ図は 0611 の `column_check.CRACK_METHOD` と共有）。R5 の `bending_rebar_amount` は Nd＝0 でも計算する（0.008Ac＝0、本物の runner で確認）。
- 図は `footing_figures.py` の `Figure`＋`Polyline`／`Arrow`／`Label` で寸法値付き。体裁の要件が GridLayoutPdf で満たせなければ GridLayoutPdf 側で直す（CLAUDE.md）。
- 0810・0820 の解説の文は 0611 と同じ短い形（照査式と「ここに、」の定義だけ）。見本 256〜257 ページの Vcd・βd・βp などの式の展開は印刷していない（2026-10-19 時点で owner 未確認）。耐久性のせん断ひび割れは見本 262 ページの「面部材のため省略」の文だけ。
- 第2軸の行（ey・L′）と粘着土の行（c・Nc・frc）は 0612 と同じく印刷しない。

## 知見を更新する

見本や原資料との新しい差、runner の挙動、受入で見つかった値の違いは、根拠（コード・実アプリ・推定の別）を付けてこのスキルに足す。決定は `.claude/docs/plans/refactoring-decisions.md` の決定60に。計算書を使う人向けの 0800〜0820 の説明（応答値の5列、Capacita の照査、既知の差）は structural-mcp のスキル `structural-webpier` の checks.md にある（ここには書かない）。式・既知の差を変えたら、そちらも直して structural-mcp で commit する。


## 杭基礎のフーチング（決定96、2026-10-26。場所打ち杭だけ）

直接基礎の 0800〜0820 とは別の段（`StageSpec.foundations` の杭基礎版、`stages.py` の `_pile_footing`・`_pile_footing_check`）。反力から地盤反力の分布を決める作りは使わず、骨組と耐震性能照査のピックアップの部材の端の値をそのまま断面力にする。

| もの | 場所 |
|---|---|
| 断面と断面力（`prepare` は骨組と入力から、`complete` は PIK・ピックアップ・NDU の要素の番号で） | `webpier/calc/pile_footing.py`（`Point`・`Width`・`End`・`Force`、`CASES`、`SEISMIC_PICKUP`＝2） |
| Capacita の条件 | `webpier/calc/pile_footing_check.py`（`calculate_pile_footing_check`、`REPORT_SECTIONS` 5 節、`scaled` で 1 m 当たりの鉄筋を幅に比例） |
| WDJ | `webpier/export/capacita/pile_footing_wdj.py`（5 点・5 部材、`shear[].deep_beam`） |
| く体前面の節点 | `webpier/calc/frame.py` の `_pile_rows(faces=)`・`NodeRole.COLUMN_FACE`。NDU の要素の番号は `webpier/export/jrsnap/build_pile.py: element_numbers(frame)` |
| 帳票 | `webpier/reporting/stages/pile_footing.py`（0800）、0810・0820 は `footing_check.py`（`shear_deep_beam_safety_destruction` の見出しを足した） |
| 鉄筋 | `webpier/calc/footing_rebar.py: main_bars(pier, direction, face)`（上面も読む） |
| 偽 runner | `tests/fixtures/fempython/fake_runner.py`（`base_lines`：フーチング底面の部材の M・S）、`aggrese/fake_runner.py`（`pickup_lines`：ピックアップ 2）、`capacita/fake_runner.py`（`deep_beam` の節） |
| 受入 | `scripts/accept_pile_footing.py` → `tests/fixtures/acceptance/pile_footing/` |

- **端の値を使う理由**：PIK もピックアップも最大・最小が別々のケースの値なので、途中の点を補間できない。部材をく体の面で分け、端の値をその面の値にする。
- **PIK の M の向き**：下側引張が正で、部材の i→j で連続（`M(j) = M(i) − V·L` が同じ組合せで成り立つ）。上側引張は最小の M が負のときだけ。
- **有効幅**：calc の docstring に式。ディープビームのせん断の幅が曲げと違うので、く体前面の下側引張のせん断だけ別の点（点 5）。
- **Capacita の `deep_beam`**：Capacita の README「shear[].deep_beam」が契約。引張側は点の `isUpperCalc`・`isLowerCalc` ではなく `mode` で決まる。Md3・Md4・Md6 と Vd0〜7 がない WD-408・WD-409 の警告は無害。
- **杭基礎の見本との差**：見本は鋼管杭・別の荷重なので断面力そのものは照合しない。値は、PIK の杭頭の力と静力学でつり合うことを受入で確かめる。見本 2.3.10・2.3.11 の式と値は Capacita のテスト（`R5DeepBeamShearTests`）で固定している。
