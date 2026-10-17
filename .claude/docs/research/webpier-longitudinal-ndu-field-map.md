# WebPier 線路方向 NDU 5.2-L03 フィールド対応

2026-10-17。Gate 1 技術確認済み。承認計画 `.agents/docs/plans/webpier-longitudinal-ndu-export.md` と追加指示「入力画面に追加する」「見本値を初期値にして作成する」に基づく。製品実装前に公式説明書とインストール済み5.2の読書き処理を照合した。実読込はrootのprobe、独立oracleはndu_acceptance担当。

## Gate 1 の確定事項

- 確定: 0710の節点・接続を保持、柱下端0.010 mだけM-θ、自動算定、それ以外剛域。WebPier現在入力の配筋・材料・地盤・作用を使用する。
- 確定: 5.2剛域のA=1000 m²、I=1000 m⁴、E=25 kN/mm²は公式PDF144–145頁の初期値。M-θへ部材全長の曲げ変形を集約して他部分を剛域とする理由は32–33頁。
- 確定: FootInfoによる直接基礎回転ばねの自動算定。短期Ks/Kv/kv、平水位、砂質土系の支持層、c=0。KR2=2、最終勾配比1/20。0500のKrを別支持に追加しない。
- 確定: Df/γ2は既存入力から自動導出する。WebPier Df4.7 m、γ2丸め前12.25531914893617、採用12.3 kN/m³。見本の3.78/11.6は定数にしない。
- 確定: せん断部材係数GBC/GBV/GBVDは新しい入力欄 `jrsnap_longitudinal.shear_factor_vcd/vsd/vdd` に保存し、今回初期値2.0/1.3/1.8を使用する。公式標準は順に1.3/1.1/1.2（PDF90/531頁）と異なることを示した上で、ユーザーが見本値の初期採用を承認。ランタイムに見本値の暗黙fallbackは置かない。
- 確定: 粗骨材最大寸法は新しい入力欄 `jrsnap_longitudinal.aggregate_max_mm`、今回初期値25 mmを使用。SectConc第5欄は単位体積重量ではない（PDF90/529頁）。実数mm、0.1～999999。係数3欄は0より大きく99.99以下、全てfinite必須。
- 見本の `TanbuShiji=0,0` は5.2保存で追加される断面せん断耐力算定用支持条件（単純支持、両端固定用部材長0）であり、骨組の実支持ばねとは別。見本の実5.2保存が追加する既定値として維持することをGate 1で確定した。
- `DataInfo` 第20欄0.001は剛性低下率**収斂係数FTM**。変位増分0.001 mは目標-0.300 m÷300回から導出される別値。両者を混同しない。

## 根拠

公式資料: `.agents/agents/jrsnap-operator/JRSNAP_Ver5.2-L03/JRSNAP_操作説明書.pdf`。頁番号はPDF物理頁。抽出テキストは `manual-comparison-data/JRSNAP.json` の `old.pages`。

見本: `.claude/docs/Example橋脚2/10_線路(耐震)/線路方向_朝里川温泉P1.ndu`（CP932、SHA256 `7511404fa1da9d67c5f89dd03b084831da322cfcf6764648a288673eb053c35e`）。PDF10の入力と照合。地盤の直接式は08 PDF28頁。正式調査記録 `.agents/docs/research/webpier-longitudinal-ndu-soil-derivation.md`。

ソース確認: インストール済み `C:/RTRI_Program/JRSNAP(Ver5.2-L03)/JRSNAP_Input.exe` をscratchのilspycmd 9.1.0.7988で読み取り。該当型のみ `tmp/webpier-ndu-implementation/core/decompiled/` に出力。製品やインストール先は変更しない。

- `DataInputTool.mdlDataFile.decompiled.cs:56` DataInfoの16整数+4実数+6flag、`:171` ElementInfo、`:370` NonLinInfo、`:420` SectInfo、`:443` TanbuShiji、`:670` SectSher、`:683` SectSafe、`:817` FootInfo、`:997` LoadCase、`:1166` SNAPConb。
- `DataInputTool.frmEditKihonJyoken.decompiled.cs:4127` 解析手法、`:4158` DDV、`:4170` DSMAX、`:4180` JNO、`:4193` MDV、`:4201` 限定ステップ、`:4233` FTM。
- `DataInputTool.frmEditYousoShogen.decompiled.cs:3379` 要素種別、`:3407` M-θ/φ、`:3411` 正負対称、`:6818` 自動非線形設定の各列。
- `DataInputTool.mdlSectKyoutuu.decompiled.cs:1959` 安全係数UIとの対応、`:2026` 主筋段数/ピッチ/降伏位置、`:2989` La、`:3149` 安全係数保存。
- `DataInputTool.mdlDATA_NDT.decompiled.cs:1219` FootInfo→基礎回転ばね種別6、`:2385` 主筋、`:3125` 安全係数、`:3584` 自動M-θ断面対応。

root実probe: `tmp/webpier-ndu-implementation/root/v52-minimal-probe-result.json`。FileVersion5.2.3.0、helper Assembly5.2.3.1、保存header `Virsion=5.2.3.S.4`。ChokuKisoNum0/リンクなし/SRenkeiなし/TishouNum0でもFootInfo・支持・荷重が保持。**TishouNum=0でもTisou=の空行は必須**。これを消すとString空→Byte変換例外。正規化は2回目保存同一SHA。

1要素1部材の6Member probeも `root/six-members-probe.json` で成功、103レコード一致、2回目同一SHA。試験専用入力から実装builder/serializerが生成した `core/fixture.ndu` は `acceptance/core-probe.json` で実5.2読込・2回保存安定・独立166レコード/623項目・8ケース合力/基礎底面モーメント照合PASS。これは解析実行ではない。正式入力への4項目追加後のSHAは `7f22b9ca22696e04b43145c9a1d668609b6654961e12c8410ebbc677065f0d93`、変更内容は `root/approved-input-additions.json`。

## モジュールAPIとmetadata契約

`jrsnap_design_conditions.py`: `derive_jrsnap_soil_conditions(raw, foundation, seismic) -> dict`、`get_profile(raw)`、名前付きprofileとversionを持つ。Df/γ2は自動導出。追加指示による4入力だけをrawから読み、入力値を解決したsettingsを返す。

`jrsnap_export.py`: `build_longitudinal_ndu_model(raw, foundation, seismic, input_sha256=sha) -> dict`。受け取った同一実行の0500/0710だけを使う。モデルは`metadata`, `nodes`, `members`, `elements`, `section`, `nonlinear`, `supports`, `footing`, `cases`, `combination`を持つ。metadataの予定確定キー:

```text
profile_id = webpier-longitudinal-v52-v1
schema_version = 1
target_version = 5.2-L03
input_sha256 = 全raw bytesのSHA
canonical_snapshot_sha256 = {foundation: SHA, seismic: SHA}
settings = 名前付きprofile設定（全値）
setting_sources = 新4欄のraw.jrsnap_longitudinal.*出典
soil_provenance = Df/γ2等の導出・出典・丸め・適用条件
correspondence = {nodes: 元ID→NDU ID, members: 元ID→NDU ID}
roles = 0710役割→NDU ID
```

snapshot SHAは全dictを`json.dumps(sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')`。0500/0710のprovenance.input_sha256が渡されたshaと一致必須。呼出元はrawを読んだbytesからsha取得する。保存済みoutput/Exampleのランタイム参照はなし。

`jrsnap_ndu.py`: `serialize_ndu(model)->bytes`、`validate_ndu_bytes(data)->dict`（製品用の構造/既知形式検査）。独立受入readerとoracleは別モジュールでserializerの定数をimportしない。sidecarは入力確認済みと`app_read_verified=false`/`analysis_executed=false`を分離し、初回実アプリ結果は外部受入記録へ残す。

## 座標・接続・荷重割当て

- 絶対系はx右、y下、M時計回り正（PDF38頁）。NDU y=0710 footing_top.y−0710 node.y、xは0710を維持。柱下端が原点。
- 必須役割cap_top/footing_top/footing_centroid/footing_bottom/column_base_micro_topは各1件。役割辞書とnodes.rolesの一致も確認する。制御節点はcap_top。
- native memberは0710 member1本ごとに1要素、MemberInfo=i,j,1、MemberLeng=実長、MemberDvid=実長,1。これは編集用グループを明確化する技術表現。rootの6Member実read/saveで確認済み。readerは名前検索でなく順次読込なのでMember_BunpuBaneやShabuzaiMeInfoのblock位置も保持する。
- 垂直要素は上→下、水平要素は左→右へ正規化（PDF32頁）。0710のH1が上向きi→jなら反転しmetadataへ残す。斜材はv1で拒否。
- 全柱区間h2/h3/h4/microにD1軸方向分布を1要素1レコードで載荷。標準4行。H4とmicroの実長合計は元H4と等しい。長さ追加や微小部材の等価節点置換はしない。
- D1のtopNは既に柱強度×(H2+H3)を差し引いてあるため、全柱長へのline載荷が正しい（`longitudinal_calculator.py:366`）。H1重量はtopN/Mに含まれ、H1へのD1追加はしない。
- EQ2はh2=beam_top両端、h3=beam_top→beam_bottom、h4/micro=column両端。各要素へiT1の全長分布を明示し標準4行。上から下の局所y正は左向きなので値は正。微小要素も対象（PDF159–161頁の全長指定と見本MLoadInfo4=要素3～4が直接証拠）。
- H1のEQ2は既存0610が定めたcap_top等価節点へH=-pedestal.H/M=-pedestal.M。`frame_model.py`のload_anchors.pedestalはequivalent_node_id=cap_top、automatic_self_weight=false。H1要素への二重line載荷はしない。
- 基準点回りMはx*Fy−y*Fx+M（y下・時計回り正）。符号付き鉛直N/Mは0710をそのまま、水平左向きは負H、pedestal正のH×heightの大きさは負M。
- H4<=0.010+1e-9 m、同位置節点、長さ<=1e-9 m、元0710で未合併のゼロ部材は拒否。La/d<2の低せん断スパンは曲げ型profileの適用外として拒否し、せん断型へ自動切替しない（PDF143頁）。

## 解析profileとNative各欄（欄は1始まり）

|キー/欄|意味と採用値/取得元|根拠|
|---|---|---|
|Virsion|5.2.3.S.4。誤記を含むnativeキー|実V52保存|
|DataName/DataTitle1..20|線路方向、titleは空。案件固有の旧名なし|mdlDataFile|
|DataInfo1/2|非線形1 / 変位増分1|PDF78–79、UI source|
|3/4|水平変位分割300 / 制御cap_top ID|見本、PDF79|
|5/6|漸増荷重分割1000 / 限定載荷最終200|見本、PDF79|
|7/8/9|非線形固定/強制終了/地盤変位最終ステップ:空、未設定|見本、PDF79|
|10/11|剛性低下trial中間/最終999/999|見本、PDF79|
|12/13/14|材料/要素直角地盤/節点ばね非線形を考慮1|PDF79、NDT変換|
|15/16|各増分結果1 / 一括出力1|見本、UI source|
|17/18|ρm=1 / αf=1。0710 combinationと同値必須|PDF79|
|19/20|目標水平変位−0.3 m / 収斂係数0.001|見本、UI source|
|21..26|基礎flag0/直接基礎1/任意座標0/等価せん断スパン法0/γc入力値0/両端固定判定0|5.2保存/基本条件UI|
|ExOptLoad|1,1,1:入力符号維持、増分係数1、地盤変位符号維持|PDF84|
|ExOptDisp|2,2,1,0,0,1,0,0:応答変位連携無効・対象要素0|5.2保存、PDF84|
|JointXY|x m,y m,出力節点ID。JointOrg=footing_top ID|0710.frame|
|ElementInfo1..4|kind:剛域1/Mθ2、i端/j端release0=剛、斜材flag0|PDF145、UI source|
|ElementInfo5..8|i,j,非線形番号(微小1/他0),地盤番号0|mdlDataFile/NDT|
|ElementInfo9..11|剛域1000/1000/25、Mθは空欄(自動算定)|PDF144–145|
|ElementInfo12..14|地盤種別0、損傷制限0、出力element ID|mdlDataFile:191|
|NonLinNum|1,1,0:全1、自動1、固定0|mdlDataFile|
|NonLinInfo1..5|自動1/断面1/Mθ1/曲げ破壊1/正負対称1|PDF142、UI source|
|NonLinInfo6..9|抜出しi/j=1/1、奥行倍率1、等価塑性ヒンジ長0自動|PDF142–143|
|SectInfo1..4|RC材料1/矩形型1/形状補助flag0/奥行1|5.2 source|
|SectInfo5/6|矩形幅W6×1000/高さB6×1000 mm|raw→section_geometry、PDF89/529|
|SectInfo7..9|中空/他形状寸法0|矩形充実のみ|
|SectInfo10/11|La=(cap_top.y−footing_top.y)×1000 / 固定軸力未設定sentinel|PDF89/91|
|SectInfo12..14|他形状寸法0/0、外部断面連携0|mdlDataFile:433|
|TanbuShiji|0,0（見本対応、断面算定用単純支持/両端固定用部材長0）|PDF529、V52追加保存|
|SectConc|柱fck、ひび割れ0自動、Ec/1e6 kN/mm²、接合部fck0同一、DMAXは新入力|PDF90–91/529|
|SectJikuNum|全行数、上/下曲げ主筋段数、上/下せん断段数、降伏位置0重心|PDF90/530|
|SectJiku|fyk,Es200,PTU0,PTL0,DELU,DELL,円形角0,任意降伏座標0,0|PDF90–92/530|
|SectRein|上面からの**芯かぶり**mm,径mm,本数。線路方向rows昇順|rebar_model.directional_rows、PDF530|
|SectSher|帯筋fyk,径,有効脚数,pitch,帯筋比0自動,未使用0,せん断筋fyk,径,脚数,pitch|均一線路hoop、PDF530|
|SectSafe|GC1.3,GR1,GS1.05(非RC用保管),GB1=1,GB2=1,GB23=1.15,GBC新入力,GBV新入力,GBS0非適用,K=.9,GBVD新入力,GBVO1.3|PDF90/531、source|
|SuppotNum/Row/FootRow|3/2/1。直接基礎ではNum=Row+FootRow|V52 source/実probe|
|SuppotInfo|始点空,底面ID,方向1水平/2鉛直,短期Ks/Kv,残9欄空|0500.short_term、PDF支点|
|FootInfo1..3|始点空,底面ID,土種1砂質|PDF155/515|
|FootInfo4..12|B,L,短期kv,c0,Df,支持層γsub,表層γ平均1桁,支持層φd,KR2=2|0500+導出、PDF155/515|
|FootInfo13/14|20=最終勾配比の逆数 / 追加未設定sentinel|V52正規化、PDF155。未設定を物理値に流用しない|
|MLoadInfo|case,開始空,終了element ID,LK,iT,AML1空,AML2空,WM1,WM2,WS1空,WS2空,説明|PDF159–162|
|JLoadInfo|case,開始空,終了node ID,LK,H,N,M,説明|PDF163|
|LoadCase/LoadAlph|1,1,0 / 1（非線形の基礎ばねcase1、その他無効）|V52 source/見本|
|SNAPConb|ρm,αf,方向0=入力符号,応答変位連携0,係数8個,未使用7空,ELoad0,DLoad0|0710 combination、mdlDataFile:1166|
|ConbAlpf|0710 coefficients8個。別の線形用集合も同値保持|mdlDataFile:1200|

### 8基本荷重の固定・増分

|番号|作用|LK|載荷位置/内容|
|---|---|---|---|
|1 D1|固定死荷重|0|柱全区間iT4=q、cap_top N/M、footing_centroid N/M|
|2 D2|付加死荷重|0|cap_top N/M、footing_top 上載土N/M|
|3 Wp|平水位浮力|0|footing_centroid 負N/M|
|4 Sw2|2年確率雪|0|cap_top N/M|
|5 L|地震時列車|0|cap_top N/M|
|6 EQ1|桁慣性|1|cap_top H=−girder.total、Kh1適用済み|
|7 EQL|列車慣性|4|cap_top H=−train.total、Kh0.2再乗算なし|
|8 EQ2|橋脚慣性|1|柱各区間iT1、footing_centroid H、H1ありcap_top等価H/M|

### 地盤検証と導出

土被りdf1/df2同値を先に検証する（abs差<=1e-9 m）。Df=H6+H5+min(df1,df2)>0と0500.layers[0].thicknessをabs差<=1e-9 mで照合。表層1＋支持層1の2層だけ。0<hw2<Dfだけ対応し端点も拒否。基礎底が支持層上面。γ1=support_layer.unit_weight_submerged、φ=support_layer.friction_angle。支持層soil_typeは砂/砂礫/砂質土の認識済み値、compressive_strength=0。wetSegment=Df−hw2、submergedSegment=hw2、γ2raw=(wetSegment*surface.unit_weight_wet+submergedSegment*surface.unit_weight_submerged)/Df。excel_round(raw,1)採用。元のDF2源・差・許容値・層・水位・区分厚・raw/adopted全て記録。

### 配筋の限定

`load_member(raw,"柱")` → `section_geometry` → `member_preview` → `directional_rows(...,"線路")`。complete=false、stale manual basis、警告、異材質混在、帯筋ゾーンは拒否。手動詳細配筋は生成元が一致し、物理バーの座標・径・材質が基本入力からの自動配置と一致する場合に限る。手動移動後の主筋段数・間隔の代表化はv1未対応として拒否する。片面の主筋層数と面内主筋間隔を現入力から採る（現値1段/150mm）。段ごとのピッチが異なるなど単一DELU/DELLで代表できない形はv1拒否。線路方向rowはy_mm上面基準、面外W6の本数を集約する。端面の純かぶり70mmを芯かぶり108mmへ誤コピーしない。現在11行/76本。

`SectJikuNum`の上下面引張段数DRTU/DRTL（せん断用DRTUV/DRTLVも同じ採用値）は、全配筋の先頭/末尾N行を選ぶ。面方向IDを別に保存する形式ではない（公式PDF90/530頁、`mdlSectKyoutuu:2027–2034`、`mdlDATA_NDT:2399–2440`）。したがって線路の有効な主筋入力行indexから物理バーの`row_indices`を通じて線路主筋集合を求め、集計した上下面各N行が全配筋の先頭/末尾N行と芯位置・径・本数・材質すべて一致することを必須とする。共通角筋は物理バー1本として照合する。側面筋が主筋より外側に来る、主筋段間に割り込む、同じ位置の行へ追加混入する配置はv1未対応として拒否し、Nを増やして別の鉄筋を主筋扱いしない。適合する複数段はその入力段数を維持する。

### 非解析の必須レコード・明示的無効

MemberOkuyuki=1、MemberShogen=1、MemberKUI=0、Member_BunpuBane=0。KGNum0。HendoCaseInfo全0。JibanCaseNum1、各JibanShogenInfoは7空欄。TyakumokuNum0/ElementTyakumokuNum=0,0。SHABUZAI_INFOと節点0,0,False・部材0×9,False,Falseは斜材編集なし。ChokuKisoNum0/G_intCHOKU_KISO_Link_Num0、各支持/Foot_ChokuKisoCaseNo0で旧照査連携なし。TishouNum0/Tisou空、SRenkeiなし、NDTPathなし。ELoad/DLoad/Pick/Conb2/Pick2/Sesf各件数0。SesfPiIJは各要素0,0,0,0,,、SesfKihonNum0/PiM0/PiS0/PiBuzai0×5。これらの無効レコードの必要性はV52読書きが根拠。

JibanTeikouKeisuu(.83×5/1×5/1×5)は `mdlChokuKiso.G_JibanTeikouKeisuu` の照査用テーブル。`mdlInitData:714–719` のrow4/5/6のアプリ初期値で、`mdlDataFile:970` がJRSNAP(SNAP_FLG=1)ではindex+3を保存する。ChokuKisoNum0・連携0なので本モデルにはその照査ケースがなくFootInfo物理値へ転用しない。GanmaA(1.2/1/1/1)は `mdlInitData:1036–1039` の初期値。`frmDanmenShousa:1949` は「応答値係数γはVepp連携出力時の応答値に反映」と明示しており、Sesf照査なし・Vepp連携出力なしの本出力では非適用。両者とも旧案件値のコピーでなく、意味と無効条件を確認したnative初期レコードである。FontColor/Size/Name、LineColor/Width、Sunpo、JointCircle、Gridは表示設定として明示初期値を持つ。ErrInfo全0は入力エラーなしの保管値であり、独自validator合格とは区別する。

## バイト・範囲・精度契約

- CP932 strict、CRLF、末尾CRLF、BOMなし。タイトル/説明のCR/LF/制御文字/`,`/`=`を拒否。本文の文字列は生成固定語のみ、40 CP932 bytes以下（非線形出力titleは20bytes以下に限定、PDF143）。変換不能を置換しない。
- 数値はlocale非依存ASCII、負ゼロは0、finiteのみ。Python round-trip可能な有効桁で出力（PDFの表示桁で丸めない）。ID/countは整数。nativeの空欄は半角空白1個、0と未設定sentinelを別扱い。
- 2500節点/3500要素/400member/200要素-per-member/500断面上限（公式29頁）。本v1はone-element/memberなので400member上限も適用。座標±20000m、部材/断面長は公式入力範囲、断面寸法0.1–999999mm、fck18–80、鉄筋径0.01–9999mm、本数正整数、荷重絶対値<1e10。具体validatorは使用欄の公式範囲を照合する。
- 0500のVBA Single境界とExcel ROUNDを保ち、macro_handoff_singleへ置き換えない。現footing_centroidのSingle位置も保持する。実V52保存で生じるSingle丸めは独立reader許容差と別に記録する。
- 全native有効値はWebPier取得/導出値・確定profile・明示未設定のどれかへ分類する。意味未確認の値を生成へ入れない。
