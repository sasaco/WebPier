# WebPier 線路直角方向 NDU 5.2-L03 フィールド対応

2026-10-17。ユーザー「線路直角方向も同様に作業してください」に基づく方向別対応。実装対象は `C:/Users/sasai/AppData/Local/Temp/webpier-transverse-ndu-20261017`、研究資料の保存先は共有workspace。前回受入済み `webpier-ndu-final-review-20261017` は読取のみ。共通nativeレコードの意味・版・必須空欄は [線路方向field map](webpier-longitudinal-ndu-field-map.md) を継承し、本書に方向差と追加の適用条件を記す。

## 根拠と入力世代

- 指示/範囲: `.agents/docs/plans/webpier-transverse-ndu-export.md`、`tmp/webpier-transverse-ndu/root/brief.md`。同じ版・微小M-θ/他剛域・並進＋非線形FootInfo・現在配筋・自動Df/γ2・編集可能な4入力を引継ぐ。
- 参照見本: `.claude/docs/Example橋脚2/11_直角(耐震)/直角方向_朝里川温泉P1.ndu`（CP932、5.1.10.S.4）と `.claude/docs/Example橋脚2/11_直角(耐震).pdf`。PDF物理1–4頁は上部2.750 mを含む8節点7要素、6頁は2700×4500/La10350/31行/直角帯筋6脚を明示。
- 5.2公式マニュアルの参照頁は線路方向と同じ: 32–33（M-θ集約）、38（右x/下y/時計回りM）、79（制御条件）、89–92/529–531（断面・鉄筋・安全係数）、142–145（非線形/剛域）、155/515（直接基礎）、159–163（荷重）。
- 現入力の初期SHA `7f22b9ca22696e04b43145c9a1d668609b6654961e12c8410ebbc677065f0d93`。rootが `jrsnap_transverse` 4項目だけを追加し、新SHA `10955ada22130e4b0e249c8c146175809e3eb10cee93331bba75d7c73763173b` を今回対象に確定した。その他のJSON値は不変、旧入力と旧0710 receiptを保持する。
- 読取専用実計算: `tmp/webpier-transverse-ndu/core/current-input-calculation.json`（0500/0720/現配筋）。作成スクリプトは同directoryの `inspect_sources.py`。独立担当の0500/0720と数値を相互確認したが、受入oracleは別担当が独立に保持する。

以下の製品行番号は新しい隔離rootを基準とする。見本NDU行番号は元CP932ファイルの行番号（可読複製 `tmp/webpier-transverse-ndu/core/sample-ndu-utf8.txt`）。

## 制御点・La・適用範囲

見本 `DataInfo:23` は350 step、制御節点1、目標+0.35 m、限定最終300、荷重分割1000、FTM0.001。見本の節点1は上部構造、capは節点2、基礎天端は節点6（`JointXY:28–35`）。`SectInfo:96`/PDF6頁のLa10350 mmは上部構造節点→基礎天端であり、cap→基礎天端7600 mmではない。

0720は `seismic_transverse_calculator.py:377` でB/Cそれぞれのh1+h2をDecimal和から上部高さとして生成する。`seismic_frame.py:221–275` は同座標だけを合併し、`superstructure_b/c` の役割、`upper_levels.B/C.node_id`、既存H1の必要な分割、`upper_geometry` を保持する。

直角profileは以下のとおり確定した。現在WebPierでは一意に定まる。

- control_role=`superstructure_b`。B/C役割が同じ節点を参照し、その役割がnodes.rolesにも一意に存在することを必須とする。
- La=(上部構造の共通節点高−基礎天端高)×1000。現在2.75+7.6=10.35 m、La/d=10350/(4500−102)≈2.353。曲げ型のLa/d>=2検査を維持する。
- 350 step、目標+0.35 m、増分+0.001 m、限定最終300。他の制御flag/収斂/反復は既存5.2 profileと同じ。
- B/C上部高さが異なる場合は、見本から最大/平均/どちらかを選ぶ根拠がなく、制御点とLaが一意に定まらないためv1未対応として具体的に拒否する。最大高や平均高を自動採用しない。
- 0720が持つ全接続・H1分割・役割を保持する。0.010 m部材以外は承認モデルの剛域。`upper_geometry` は重量や慣性を追加しない。

rootの実装GOでこの制御/La・適用範囲を確定した。現在WebPierに追加の工学数値入力は不要。

## 座標・部材・断面・支持の方向差

|Native対象|直角方向の定義・現在値|出典|
|---|---|---|
|JointXY/JointOrg|x=0720のx、y=footing_top.y−元y。原点=footing_top。上部−10.35、cap−7.6、微小上端−.01、天端0、重心1.349999976158142、底面2.7|0720.frame、共通原点規約。見本の底面原点から全yを平行移動するだけ|
|Member/Element|現8節点7部材7要素、一要素一部材。要素5=0.010 M-θ、他6要素=剛域1000/1000/25|見本NonLinInfo:93、0720.frameのregion/役割|
|SectInfo width/height|width=B6×1000=2700、height=W6×1000=4500 mm|transverse_calculator.py:80–93、見本:96/PDF6頁|
|SectInfo La|共通上部節点→基礎天端10350 mm|見本:96、0720.upper_levels|
|SectConc|現柱fck27、Ec26500000/1e6=26.5、粗骨材は新4入力の値|0720.frame.materials.column。DMAXは単位重量ではない|
|SectRein|directional_rows(bars,"直角")。芯位置は物理x_mm。現在31行、計76本|rebar_model.py:676–691、見本:100–130|
|主筋段数/間隔|face_direction="直角"の有効行が1段、主筋D19×9/芯102・4398、間隔250 mm|現在raw main_rows、column_rebar.py:192|
|主筋選択安全検査|row_indicesで抽出した直角主筋物理集合が全配筋の先頭/末尾N行と位置・径・本数・材質で一致必須。角筋は1本|前回Q1修正、rebar_model.py:492–547|
|SectSher|direction="直角"の均一hoop1件。D22、有効6脚、150 mm、SD390|raw.column_hoops、見本:131。線路10脚の流用禁止|
|SectSafe/DMAX|前回と同じ意味、係数3個とDMAXは `jrsnap_transverse` の独立4入力。今回2/1.3/1.8/25|明示指示「同様」、brief。長方向キーを暗黙fallbackにしない|
|FootInfo B/L|B=0500.foundation.L=9（W7+W8+W9）、L=0500.foundation.B=7（B7+B8+B9）|inputs.py:97–106、calculator.py:130、見本FootInfo:140|
|SuppotInfo|底面節点8に水平Ks8525475、鉛直Kv25576488、短期値|0500.short_term、見本:137–138|
|FootInfo kv|0500.short_term.kv=405976。別のKr支持は作らない|直接基礎非線形回転の承認方式、見本:140|
|FootInfo土値|Df4.7、γ1=支持層水中10、γ2=12.3、φ42.2、c0、砂質1、KR2=2/KR3=20|前回地盤導出と同一raw/0500、stage出典名を0720へ。見本3.78/11.6はコピーしない|

基礎の元B/LとKs/Kv/kvをrawからの純粋0500計算に照合してから、直角方向だけB/Lを交換する。単純に `Kr_transverse` を追加するとFootInfoと回転支持を二重定義するため追加しない。短期Ks/Kv/kvは方向共通、Krのみ方向別という既存0500仕様は `foundation_springs.py:33–50` でも確認できる。

## 9ケースと組合せ

0720の `basic_cases` と `actions` を同一性検証して用いる。見本NDUは旧8ケースで、下り/上りの一方だけを含む。0720の9ケースを8へ圧縮しない。case5下り/case6上りと組合せは `seismic_transverse_calculator.py:400–433` が正規契約。PDF p11/p13の逆表記は既存0720でユーザー確認済み（同:421前後のprovenance）。

|case/key|LK|Native作用・現在値|主な出典|
|---|---:|---|---|
|1 dead_fixed/D1|0|cap N8299.52、footing_centroid N4167.4501953125、h2/h3/h4/micro全長iT4=qN297.68|0720.actions.dead_fixed、transverse_actions.py:137–173|
|2 dead_additional/D2|0|cap N780、footing_centroid N1830.5999755859375|0720.actions。直角上載土は基礎重心を保持、長方向の天端へ変更しない|
|3 buoyancy_normal/Wp|0|footing_centroid N−1701|0720.actions.buoyancy_normal|
|4 snow_2_year/Sw2|0|cap N710|0720.actions.snow_2_year|
|5 train_down/L|0|cap N480、M−1028.62|0720._train_action:190–216（下り支承係数）|
|6 train_up/L|0|cap N480、M+1028.62|同（上り支承係数）|
|7 girder_inertia/EQ1|1|cap H+9090、M+27105|0720._horizontal:219–257、0600直接Double値。見本9080をコピーしない|
|8 train_inertia/EQL|4|cap H+144、M+770.4|同。Kh0.30は適用済み、再乗算なし|
|9 self_inertia/EQ2|1|footing_centroid H+1105.65、h2 qH595.35一定/h3 595.35→297.68/h4+micro297.68一定、H1があればcap等価H/M|0720._self_inertia:260–320|

- 右向き水平Hと時計回りMを正とし、全pointのN/H/Mを0720の符号付き値のまま採用する。片線列車の偏心Mを消さない。
- 垂直要素は上→下に正規化。右向き横分布はnative局所y負なのでiT1のWM1/WM2は `−qH_top/−qH_bottom`。見本MLoadInfo:209–211でも負値。D1のiT4軸方向qNは正のまま。
- 0720 line.member_ids/from/toと実要素・列区間の一致を確認し、一要素一行へ展開。D1/EQ2は現在各4行（合計8）。H4分割前後の合力と一次モーメントが一致する。
- H1の等価作用はcapへ載せ、上部・H1の分布を追加しない。全成分0のH1 pointは省略し、現在JLoadは11件。ゼロのない作用を省略しない。
- EQ1/EQLのMはcap回り全等価モーメントなので上部節点へ再移動しない。上部剛域は幾何/制御/La用である。
- 組合せ1件: ρm=1、αf=1、右方向、地盤抵抗1、係数 `[1,1,1,1,1,0,1,1,1]`。上りLはcaseとして保持し、本組合せの係数だけ0。
- `SNAPConb1` は前4欄＋固定15係数枠＋末2欄の21欄。9係数の後は空6欄（8ケースの空7欄をそのまま残さない）。`ConbAlpf1` は9欄。

## API・互換契約

- `build_transverse_ndu_model(raw, foundation, seismic, input_sha256=sha) -> dict`。既存 `build_longitudinal_ndu_model` を保持する。
- `TRANSVERSE_PROFILE_ID="webpier-transverse-v52-v1"` を追加。既存 `PROFILE_ID="webpier-longitudinal-v52-v1"` は保持する。schema1/target5.2-L03は共通。
- `get_profile(raw, direction="longitudinal")` と `derive_jrsnap_soil_conditions(..., direction="longitudinal")` を後方互換拡張し、直角では明示的に `direction="transverse"` を渡す。
- `serialize_ndu(model)` と `validate_ndu_bytes(data)` を共通化する。native DataNameは線路方向/線路直角方向、8/9ケース、制御値、組合せ係数を対応するprofileへ結び付けて検証する。古い0710 NDU bytesを変更しない。
- metadataの既存キー `profile_id/schema_version/target_version/input_sha256/canonical_snapshot_sha256{foundation,seismic}/settings/setting_sources/soil_provenance/correspondence/roles` は維持。新直角modelにdirectionを持たせる。sourcesはraw.jrsnap_transverse、0720、方向交換後のB/Lを明記する。
- productは同じ実行の0500/0720だけを受け取り、ディスクのExample/帳票/保存JSONを参照しない。入力SHA・スナップショット・現配筋・材料・幾何の同一性を検証する。
- header5.2.3.S.4、CP932strict/CRLF、逐次レコード順、Tisou空行、旧CHOKU/SoilRenkei/NDTPath除外は変更しない。初回freshの実5.2受入はroot/独立担当が行い、NDT/解析は行わない。

## 検証と未実施範囲

現在WebPierの工学値は全て入力・0720・直角見本または前回承認profileに対応し、未確定の工学値はない。B/C異高時はv1未対応として拒否し、現入力に対する制御・Laは上記のとおり確定した。

- 新隔離版のcore4テストファイル: 143 passed in 2.61s、exit0。所有7 PythonファイルのRuff: All checks passed、exit0。断面方向・31行/76本・方向別hoop、B/L交換、9荷重合力/一次モーメント、限定増分、片線偏心、係数0、H1、異高/低せん断スパン/不整合の拒否を確認した。
- 同じ新入力からの0710 NDUは6298 bytes/SHA `02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71` で前回受入済みbytesと完全一致。0720試作は7484 bytes/SHA `16f2da64fa9630adbb3b32181bba5b7a8c0f653c700d503274a1d8e51ba0fc22`。`tmp/webpier-transverse-ndu/core/current-generation.json` に保存。
- 実5.2初回形式probeはrootと独立担当が実行し、200レコード/724欄、9基本荷重＋1組合せの合力/モーメントが生成前・第1保存・第2保存で一致。保存後SHA `1b0f76a82634e636c6aca7bcf0501f7da14ca99508db809b75e994d08733f464` が2回同一。証拠 `tmp/webpier-transverse-ndu/root/first-v52-semantic-probe.json` と `tmp/webpier-transverse-ndu/acceptance/native-probe/probe.json`。
- このprobeは正式公開の受入記録ではない。正式候補は全担当の固定後にfresh受入を行う。GUI操作・NDT出力・解析・構造安全性検証は行っていない。
