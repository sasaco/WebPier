## Implementation Plan: Pier Height Boundary Nodes

### Purpose

`Example橋脚/pre/input-下部構造.pdf` のH1/H2・H2/H3・H3/H4境界と、H1が正のときのパラペット上端を、0610・0620の計算入力モデルの節点・部材接続として表現する。パラペット付き／両方向で基礎が非対称の、CLIでも再利用できる完全入力サンプルを追加する。

### Scope

**ユーザー確認済み**

- 表示用の点追加ではなく、結果JSONの実モデルに節点と部材を追加・分割する。H1が正のパラペット上端にも節点・部材を設ける。
- パラペットのB2・B3・H1が正のサンプルと、B7≠B9かつW7≠W9のサンプルを追加する。パラペットと非対称基礎が同時にある条件も検証する。
- 共通 `.agents/rules`、`.agents/STATE.md`、`PROGRESS.md`、`.agents/docs/DESIGN.md` が未配置であるため、ユーザー許可に基づき既存README・前計画・ソースを根拠とする。

**今回採用するモデル契約（実装承認の対象）**

- 現実装は荷重と骨組条件を生成するもので、変位・断面力を解くソルバは存在しない。今回は接続・断面・材料・剛域・ばね取付先を持つ計算入力モデルを作り、解析ソルバや断面照査は追加しない。
- 底面をy=0、柱軸をx=0とする。基礎天端 `zF=H6+H5`、柱天端 `zC=zF+H4`、H2/H3境界 `zB=zC+H3`、H1/H2境界 `zT=zB+H2`、H1上端 `zP=zT+H1` と一度だけ累積する。フーチング重心は0600から受け取るhGのSingle値を保ち、H6肩に置き換えない。
- H2・H3・H4の部材は既存の等価柱断面・材料を継承する。境界追加を理由に、新たな梁・ハンチの変断面剛性モデルへ変更しない。フーチング天端→重心→底面の接続は既存の剛域とする。
- H1>0では方向別寸法a=BまたはWについて、パラペット中心 `xp=(2*a2+a3-a1-a4+a5)/2` に基部 `(xp,zT)` と上端 `(xp,zP)` を置く。H1部材は鉛直とし、梁天端 `(0,zT)` から基部へ剛な水平アームを接続する。xp=0なら基部を梁天端と共用し、長さ0のアームを作らない。
- H1断面はB3×W3、A=`ROUND(B3*W3,3)`、線路方向I=`ROUND((1/12)*W3*B3^3,5)`、直角方向I=`ROUND((1/12)*B3*W3^3,5)`。既存のExcel互換丸めと方向別body材料を使う。H1>0でB3/W3が0、丸め後A/Iが0、非有限値なら0610/0620で入力パス付きエラーとする。0600単独の0体積処理は維持する。
- `frame.nodes` を実節点、`frame.members` を明示接続として扱う。節点は `id,x,y,roles,source_rows`、部材は `id,node_i,node_j,region,behavior,section_ref,material_ref` を基本とする。`frame.node_ids` の意味別参照、`frame.sections`、`frame.support_node_id`、`frame.load_anchors`、`frame.model_version=2` を設ける。既存 `frame.section`・materials・springs・shape_eccentricityは互換情報として残す。rigid部材はsection_ref/material_refをnullとし、behaviorで剛な接続を明示する。元4節点は `frame.legacy_nodes` に元のid/x/y/source_rowと合流先active_node_idを保存し、実節点のsource_rowsには合流した元行番号を全て保持する（新規のみなら空配列）。0610の元行81～84、0620の元行79～82を取り違えず、新規境界へ架空の元行を付けない。
- IDは入力に対して決定的とする。既存node 1=梁天端、2=基礎天端、3=基礎重心、4=底面を維持し、5=H2/H3、6=H3/H4、7=偏心H1基部、8=H1上端とする。member IDは1=H2、2=H3、3=H4、4=基礎天端→重心、5=重心→底面、6=水平剛アーム、7=H1とする。省略時のID欠番を許し、表示順とIDを分離する。新境界が既存節点と一致する場合は既存IDを優先し、重心と底面が一致する場合は底面ID4を支持節点として共有する。処理は配列の位置や「節点4」という表示文字に依存させない。同じ(x,y)の境界roleは同一節点へまとめる。H2/H3=0、hGと端点の一致でも長さ0部材を作らず、同じ高さでもxが異なるパラペット基部と梁天端は別節点にする。近接する別節点を表示丸めで合流させない。全ての同一座標グループには完全優先順 `[4,2,1,3,5,6,7,8]` を適用し、最初に存在するIDを残す。H3=0では5へ6を合流、H2=0では1へ5を合流、H2=H3=0では1へ5/6を合流、hG=zFでは2へ3を合流、hG=0では4へ3を合流、xp=0では1（またはその合流先）へ7を合流する。roles/source_rowsは失わず、全memberと支持・荷重参照を合流先へ書き換える。H1中心条件は入力の十進値の関係と浮動小数残差を区別し、数学的に中心ならxp=0とする。許容誤差で小さな実偏心を0とみなさず、中心・極小非0の独立例で確認する。正の高さが座標精度で消失する場合は、ゼロ高さと黙って同一視せず数値範囲の入力エラーとする。
- 既存荷重は桁受けの重量・偏心・慣性力を既に含む。部材追加から自動自重を加算せず、柱頭の集約N/Mは元の梁天端role、基礎の集約荷重は元の帰属位置に維持する。元の柱分布荷重区間はH2/H3/H4の分割部材に対応付ける。役割・部材参照の対応は新モデルのメタデータへ明示し、今回ソルバ用荷重ベクトルへの変換は行わない。`frame.node_ids` のrole名は cap_top / footing_top / footing_centroid / footing_bottom / h2_h3 / h3_h4 とし、H1>0のときだけparapet_base / parapet_topを加える。`frame.load_anchors` は次の固定schemaとし、数値荷重は複製しない。cap_top={node_id: node_ids.cap_top}、footing_centroid={node_id: node_ids.footing_centroid}、column_line_load={from_node_id: node_ids.cap_top, to_node_id: node_ids.footing_top, member_ids: 存在するH2/H3/H4のIDを[1,2,3]の順で列挙}、pedestal={equivalent_node_id: node_ids.cap_top, automatic_self_weight: false}。このpedestal参照は既存集約成分の扱いを示すメタデータで、既存水平力・慣性力の高さやモーメントを新しい荷重ベクトルへ読み替えない。
- 元Excelの `cells`・`transfers` は旧4節点も含め監査用として保持し、原表セルを拡張モデルで上書きしない。PDFの実モデル表は `frame` から生成し、原表との違いを説明する。入力schema_version=1および既存の荷重値・組合せ係数は維持する。変更されたframe契約はmodel_versionとREADMEで明示する。

**New files**

- `src/frame_model.py` — 共通の節点・接続・role・断面・荷重帰属参照の生成と検証。
- `./tests/test_frame_model.py` — 明示期待値による両方向のモデル、縮退・偏心・参照整合性検証。
- `./tests/fixtures/pier_models/parapet-asymmetric.json` — 既存独立検証の `pedestal_nonzero` に基づく完全入力。
- `./tests/fixtures/pier_models/asymmetric-footing.json` — 既存独立検証の `geometry_water` に基づく完全入力。
- `./tests/fixtures/pier_models/expectations.json` と `README.md` — 独立に固定した座標・接続・断面・出典・再実行手順。

**Modified files**

- `src/longitudinal_calculator.py`、`transverse_calculator.py` — 元セルの計算を保ち、拡張frameを共通生成する。旧「全節点x=0」の注記を主幹と偏心H1の説明へ更新する。
- `src/frame_outline.py` — パラペット外形、任意の節点x/yと部材接続、意味別寸法、番号の配置。
- `src/longitudinal_report_reference.py`、`transverse_report_style.py` — 実接続からの骨組図と、実節点／部材の動的表。
- `./tests/test_longitudinal_calculator.py`、`test_transverse_calculator.py`、`test_frame_outline.py`、`test_longitudinal_report.py`、`test_transverse_report.py` — 4節点・隣接部材・H1非表示の固定期待を新契約へ更新し、既存数値検証を保持する。
- `./tests/test_longitudinal_cli.py`、`test_transverse_cli.py`、`test_report_cli.py` — サンプルの全経路、共通SHA、段階別エラー時の非公開を既存パターンで検証する。
- `./README.md` — モデル契約、等価断面の継承、H1偏心・エラー条件、サンプルと実行例を記載する。
- 検証完了後の再生成は `./output/0610_線路方向荷重.{pdf,json}`、`0620_直角方向荷重.{pdf,json}` の4ファイル。

**対象外・Dependencies**

- GUI、入力JSON原本、0500/0600の計算式・帳票、元xls・参照PDF、既存独立oracle、組合せ係数、選択ポリシー、依存パッケージ・lockを変更しない。構造解析・断面照査・配筋・新たな設計基準の導入、コミット／pushは含めない。
- 既存ReportLab・PyMuPDF、devのpytest・pypdfを使用する。通常実行／テスト時にExcelや参照PDFを読まない。

**調査根拠**

- ソルバ非実装と現在のframe: `longitudinal_calculator.py:1`、`:117`、`:133`、`transverse_calculator.py:341`、`:362`。元節点・等価断面は両計算器の `_frame`（各`:159`）。
- 入力の0許容と幅条件: `reaction_inputs.py:163`。パラペットの位置・外形: `reaction_report_diagrams.py:134`、`:209`。入力PDF1ページを画像化して目視照合した。
- 桁受けを含む既存荷重: `longitudinal_calculator.py:92`、`:202`、`:234`、`transverse_calculator.py:136`、`:275`。
- 固定寸法ペア・主幹軸限定の配置: `frame_outline.py:114`、`:144`。両描画器の固定軸・部材番号・節点4注記: `longitudinal_report_reference.py:62`、`transverse_report_style.py:67`。
- 2ページ目の旧4点表: `longitudinal_report_reference.py:115`、`transverse_report_style.py:219`。既存layoutの座標表だけを描画時に抑止・置換し、材料・ばねは再利用する。layout JSON自体の全面再抽出は不要。
- 独立セル検証: `test_longitudinal_calculator.py:166`、`test_transverse_calculator.py:166`。既存サンプルは `tests/fixtures/{reaction,longitudinal,transverse}_excel_oracle.json` の `pedestal_nonzero`／`geometry_water`。

### Implementation Steps

独立サンプルとモデル契約を先に固定し、両計算器、荷重の帰属、共通配置、両帳票、全経路検証の順に進める。本番出力は検証完了後に更新する。

#### Step 1: 独立期待値と再利用可能な入力サンプルを固定する

- [x] 実装着手時の最新コードと差分を確認し、並行作業の反力入力変更を保持する。その時点を基準として、現入力と既存2条件について、変更前の0610/0620の結果・PDF、0500/0600の結果、対象出力と保護対象のハッシュを `tmp/pier-height-boundary-nodes/` に保存する。比較は同名コピーのinput.jsonを使い、出典ファイル名・SHA差を計算差と混同しない。
- [x] 既存oracleの完全入力から2サンプルを追加する。新コードでoracleを再生成しない。出典には「独立試験条件からの変更サンプル」であることと元ケース名を明記し、原PDFの実測値と誤認させない。
- [x] 新モデルの座標・全node_ids・残るID・全roles・接続・断面・剛域・ばね取付先・load_anchorsの全フィールド・legacy_nodes/source_rowsの明示期待値を別fixtureに固定する。H2/H3の0・正4構成、hG=底面／天端、中心H1と偏心H1の合流について完全な期待辞書を用意する。既存4点セルの照合とは分ける。
- [x] 具体例を固定する。既定入力の主幹y=`[11.2,10.025,9.8,2,1,0]`。パラペット条件はB2=.25、B3=.6、W2=.3、W3=.9、H1=.4、B4=.175、B5=.275、W4=.875、W5=1.075、B7=.35≠B9=.2、W7=.4≠W9=.25。主幹は既定と同じ、H1上端y=11.6、中心xはB=-.5／W=-3.375、A=.54、Iは.0162／.03645で、各方向8節点・7部材となる。
- [x] 非対称基礎条件は `geometry_water` のH5=.6、H6=1.8を含む全入力を使う。主幹y=`[11.6,10.425,10.2,2.4,1.1779999732971191,0]` とし、hGとH6肩の混同を検出する。

**Verification**: 2サンプルが既存の入力parserと全stage計算を通る。サンプルの数値入力が元oracleケースと一致し、追加の出典注記だけが意図した差である。独立期待値は本体のモデル生成関数を呼ばず、原本・本番出力・既存oracleのハッシュは未変更。

#### Step 2: 共通frameモデルを生成し、両方向へ組み込む

- [x] `frame_model.py` に上記契約の生成・参照検証を実装し、両計算器の旧セル計算後に呼ぶ。node roleと明示memberから構成し、IDの大小・配列位置で接続を推測しない。
- [x] H2/H3/H4の分割とフーチング剛域、偏心パラペットの基部・上端・水平アーム・H1断面、支持節点を生成する。方向別の断面と材料fck=24／25の既存差を保持する。
- [x] H1=0はパラペット節点・アーム・断面を作らない。H2/H3が0、H1中心が柱軸上、hGが端点と同じ、極小正高さ、偏心符号反転を扱う。ゼロ長・重複部材、孤立節点、存在しない節点／断面／材料参照を禁止する。
- [x] H1正かつ幅0／丸め後断面0の入力は0610/0620で明確に拒否する。0600単独の互換入力処理は変更しない。

**Verification**: `test_frame_model.py` と両計算器テストが通る。既定6節点5部材、偏心H1サンプル8節点7部材、中心H1では基部共用で7節点6部材となり、全接続が基礎底面に到達する。独立座標・断面・roleの照合、完全優先順による全合流パターンのID/alias/member/support/source_rowsの厳密一致、同高別xの保持、十進中心と極小偏心の区別、決定性・入力非破壊、段階別エラーを確認する。既存全セル・転記値・Single・係数の独立検証は引き続き通る。

#### Step 3: 荷重の帰属と互換性を検証する

- [x] 元の柱頭・基礎・分布荷重区間の意味を上記の固定load_anchorsで明示し、独立fixtureの全辞書と直接比較する。有効でも誤った節点（例: H1上端）や、正しい長さでも順序・部材を取り違えた対応は失敗とする。H1上端追加後も集約荷重の適用高さ・腕を変えず、未計算の0620基本行は未計算のまま保持する。
- [x] H2/H3/H4の部材長合計が元の柱頭～基礎天端の長さに一致し、同じ柱分布荷重による力と底面回り一次モーメントが分割前後で保存されることを独立算定する。H1自重は元のtop／慣性成分だけに1回含まれることを確認する。
- [x] 変更前結果との比較許容を `frame` と、旧「節点xが全て0」というwarningsの1文を主幹と偏心H1を区別する説明へ置換する差だけに限定する。他のwarnings・provenance・units・inputは保持する。その他の `cells,transfers,vertical,horizontal,inertia,basic_cases,combinations` と、0620の選択結果・風荷重・集約値は厳密比較する。値を変えて検証を通すための既存期待値更新は禁止する。

**Verification**: 既定・パラペット・非対称基礎の全経路で、荷重値と組合せ係数が同一入力の基準と一致する。0600の桁受け重量セル5.29 kNと後段受渡しのSingle値を区別して照合し、既存成分に1回含まれ、新たな自動荷重がない。支承・荷重の参照がH1上端へ移動せず、load_anchorsの各node_id/from/to/部材順/自動自重flagが独立期待値と完全一致する。境界や基礎重心の合流後も同じ対応を確認する。

#### Step 4: パラペット外形と任意接続の図配置に対応する

- [x] `frame_outline.py` にパラペットの矩形を追加し、0600と同じ位置規則を使う。柱軸と非対称基礎の座標系を維持する。
- [x] `fit_frame` の入力を節点・部材・明示的寸法仕様へ拡張する。実際の(x,y)、任意の接続の中点、role指定の高さから配置し、同じ高さの横アームを隣接鉛直部材として描かない。
- [x] H1/H2/H3境界を確認できる寸法と番号を表示し、主幹全高・基礎剛域・hGの区別を保つ。高さ0の寸法・重複番号を抑止し、近接節点には必要な引出線を付ける。
- [x] 等方縮尺、番号の白下地、線種の状態復元を保持する。幅広・低い・左右鏡像・極小区間でも外形／骨組み／寸法／注記を枠内へ収める。以前の「H1を変えても外形不変」試験を意図して改め、hGだけでは物理外形が変わらない試験は残す。

**Verification**: 共通形状・配置テストが通る。H1の位置／外形と実節点xが一致し、水平アームと鉛直H1部材が別々に表示される。座標・部材番号・寸法の全annotation範囲、非重なり、縦横倍率の一致を検査し、ハンチなしなど既存の形状分類を保持する。

#### Step 5: 両PDFの骨組図と実モデル表を更新する

- [x] 両描画器を `frame.members` の明示接続へ切り替え、elastic／rigidの線種・部材ID・実節点x/yを使う。最下節点や剛域を固定indexや「節点4」で参照しない。
- [x] 両2ページ目の旧4点座標表を抑止し、`frame.nodes`／`members` から実節点表・接続表を描く。材料・ばね表は再利用し、等価柱断面を継承した分割であることとH1断面・剛アームを示す。
- [x] 表の可読性を優先し、必要ならモデル条件のページだけを適切に改ページする。旧4点の原表セルとlegacy_nodes/source_rowsはJSONの監査用として保持する旨を記す。追加ページが生じる場合は、0610の固定9頁ループと0620の元layout頁番号を実際の出力順による連番へ置換する。source layoutページと出力ページを別管理し、モデル表の継続頁を挿入しても後続内容の順序と見出しを保持する。実図にない「元節点4」を現モデルと混在させない。
- [x] 既定・パラペット・非対称基礎について、1ページ目とモデル表を画像化して目視確認する。両PDFの節点座標・ID・部材接続がJSONと一致することを、文字／ベクトルの検査で確認する。

**Verification**: 両帳票テストが通り、図と表に全実節点・接続があり、H1上端と境界が独立期待値に一致する。render時の入力／見本PDF／Excel再読込がなく、result辞書も不変。荷重以降はページ番号などのメタデータを除いた対応する内容単位で、基準の数値・文字・ベクトル／画像と一致する。ページ数9／17固定や「2ページ目以降不変」を完了条件にしない。本文比較から頁番号を除くことは頁番号検証の省略を意味しない。全頁footerが1～実ページ数で順序通り・欠番重複なしであること、入力SHA表示と荷重章の出力順が正しいことを別に検証する。少なくとも1試験はモデル表の使用可能高さを小さくして継続頁を実際に発生させ、後続頁が正しく繰り下がることを実PDFで確認する。

#### Step 6: 全経路・失敗時の検証と説明を仕上げる

- [x] サンプル2つと既定入力を使い、0500→0600→0610／0620、`--stage all` を一時出力へ実行する。段階別実行とallのframe・数値が一致し、全結果の入力SHAが共通であることを確認する。
- [x] H1正・幅0等のモデルエラーでは、0610/0620/allが公開前に失敗し、既存成果物を更新しないことを既存CLI試験のパターンで確認する。0600単独の既存0体積動作も確認する。
- [x] READMEにサンプルの意味・出典、CLIと編集アプリでの開き方、新しい節点・接続・断面・荷重帰属、原表監査セルとの違い、ソルバ非実装の範囲を記す。サンプルの出力先はtmpとする。
- [x] 対象テスト後、`.agents/check.ps1 -ProjectRoot 'K:/ニュージャパンコンサルタンツ/26_LRT鉄道照査'` を実行し、失敗とskipを確認する。他タスクの差分を取り込まず、Scope内の変更だけを確認する。

**Verification**: 対象試験と全pytest gateが成功する。skipは理由を記録し必要なケースを再実行する。サンプルが単独JSONとして再実行でき、モデル・荷重・帳票の整合と入力／原資料／既存oracleの不変を証拠で確認できる。

#### Step 7: 検証済みの実出力を更新する

- [x] 全確認後、現在の本番入力に対して既存CLIの `--stage 0610 --overwrite` と `--stage 0620 --overwrite` を実行する。既存のPDF／JSON対の退避・復旧処理を使う。
- [x] 両PDFの図・実モデル表を再確認し、同名JSONのSHA・節点・接続を確認する。0500/0600とその他出力、入力・原資料のハッシュが実行前と同じであることを確認する。

**Verification**: 現在入力の両方向で境界節点・分割部材が実PDFとJSONに一致する。変更対象の出力は指定4ファイルだけで、サンプルは本番入力と出力を上書きしていない。

### Risks & Considerations

- **H1追加に伴う設計範囲**: 偏心基部と剛アームは今回のモデル化方針であり、単なる図上補助線にはしない。構造応答の妥当性を検証したとの主張はしない。H2/H3/H4には従来の等価柱断面を継承する範囲を、表とREADMEに示す。
- **既存荷重の二重計上・高さ変更**: H1部材があることから自重を再追加したり、旧top合力をH1上端へ移さない。力と一次モーメント、独立Excelセル、役割参照を検証する。
- **縮退と浮動小数**: 境界高さを一度だけ累積しroleを共用する。近接節点を図の表示桁で合流させず、同高・別xを区別する。重心のSingle値は再計算しない。
- **互換性**: `frame.nodes` の件数・ID・xの契約が変わる。model_versionとrole参照を導入し、全既存消費箇所を更新する。入力schemaと元数値の監査証拠は保つ。H1正・断面なしは0610/0620で新たにエラーとなることを記す。
- **モデル表の取り残し**: 旧4点セルは互換証拠であり、実モデル表として再印字しない。1ページ目だけの修正では完了しない。
- **サンプルの独立性**: 既存独立oracleを上書きせず、全入力の数値一致と固定座標を確認する。新モデルの期待値を本体から逆生成しない。現在入力の結果が保存見本と一致することは要求しない。
- **レイアウトと回帰**: 任意接続・同高節点・短部材で番号や寸法が重なりやすい。実PDFを画像化し確認し、荷重内容はページ位置ではなく内容単位で照合する。
- **作業環境**: 日本語パスのPython stdinにはUTF-8を明示し、ネットワークドライブを読めないread-only Codexには対象ファイルの一時ローカルコピーを使う。本番コードをレビュー用コピーで置き換えない。

### Open Questions

- 節点を計算モデルへ追加すること、H1上端も含めること、共通ルール未配置時の調査資料はユーザー回答で確定済み。
- 本書のモデル契約を含む実装は2026-10-15のユーザー回答「実装に進んでよい」で承認済み。技術的に未解決の阻害事項は残さず、独立検証で発見した必須修正は承認提示前に反映する。

### Plan Validation

- Status: Complete — live統合・最終gate・独立レビュー・本番4出力の再生成と照合を完了。
- Slug: `pier-height-boundary-nodes`
- Plan path: `.agents/docs/plans/pier-height-boundary-nodes.md`
- Codex decomposition: `.agents/logs/codex/20261015T051424Z-plan-pier-height-boundary-nodes-steps.md`。固定semantic ID、役割参照、剛アームのnull断面、独立サンプル、実モデル表の更新を採用した。工程は関連する契約・生成をまとめた7段階とする。旧x=0注記だけは新要件に合わせ更新し、モデル表の適切な改ページを本計画の承認対象に含める。
- Gate 1 — shape: PASS（必須5節・警告なし）。最終記録更新後も再実行済み。
- Gate 2 — artifact: PASS（解決済みパスに空でない計画書が存在）。
- Gate 3 — adequacy: 初回NEEDS_REVISION（`.agents/logs/codex/20261015T052339Z-plan-pier-height-boundary-nodes-validate.md`）。全合流のID優先順、荷重anchorの固定schema／期待値、元source_rowの保存、継続ページの連番検証を追記。再検証 **PASS**（`.agents/logs/codex/20261015T053020Z-plan-pier-height-boundary-nodes-validate.md`）。必須修正・技術的阻害事項なし。
- Gate 4 — user approval: Approved。2026-10-15にユーザーが「実装に進んでよい」と承認。
- Next: 完了。追加実装の必須事項なし。
- Review environment: 対象ソース・テスト・計画書のローカルread-onlyコピーを使用し、最終レビュー対象と作業原本のSHA256一致を確認した。別作業のA/D反力入力変更は保持し、実装開始時の基準採取へ明示した。
- 計画段階の確認: 入力PDFの1ページを目視確認、コード調査、Codex工程相談と内容検証、文書contract／実体検証。製品コード・本番入力・本番出力の変更および製品テストの実行は本作業では行っていない。

### Approved Scope Adjustment

- 2026-10-15: 並行して導入されたB9=B7の計算時強制は非対称サンプル要件と衝突したため、ユーザーが「明示されたB9を優先する」を承認。0500のinputs.pyと0600のreaction_inputs.pyはJSONの明示B9（0を含む）を検証して使用し、欠落/nullだけB7の式へfallbackする。GUIのB9自動計算と他の復元式は維持する。test_input_formulas.pyの旧B9常時強制期待だけを新契約へ改訂し、明示・未指定・不正B9の段階間一致を追加検証する。
- 比較基準は他の並行数式復元変更が落ち着いた時点のコードへ合わせ、今回のモデル変更前後を同じ上流入力契約で比較する。元の着手時基準も保持し、無関係な数値差を本変更によるものとして扱わない。

### Implementation Verification Progress

- ユーザーの別セッション停止確認後、承認済み明示B9処理・サンプル実parser試験・両READMEをliveへ最小統合。他作業のGUI/数式・15有効桁文・反力帳票試験は保持した。
- レビュー指摘の極小正H6消失を元の加算順のまま検出する2行guardを追加。両方向のRed→Green、関連254件成功、独立20モデルの通常結果完全一致で修正を確認。
- 最終live gate: overall=pass / exit=0、2066 passed / 1 Tk初期化skip、243.63秒。skipした上部構造GUIケースだけの隔離再試験は1 passed / 7.94秒。source/testsはgate前後・本番更新後ともSHA不変。全toolsは `tmp/pier-height-boundary-nodes/root-live-gate.raw.json` に保存。
- 独立security/quality/testレビュー完了。必須指摘は解消済み。任意Lowは微小な標高差の表表示精度と表内chunk分割の永続試験強化で、実動作の独立probeは正常。Ruff未利用、coverage未計測。worklog6件・review3実体・plan文書のcontract検証済み。
- 最新上流条件の既定・パラペット・非対称基礎で、frameと承認済み注記以外のJSON、0500/0600、荷重頁の文字/ベクトル/画像が厳密一致。最新本番入力でも非frame数値不変を確認。
- 本番0610/0620のPDF+JSON計4ファイルを既存CLIで更新。両JSONは承認済み期待出力と完全一致、PDF全26頁は期待出力の文字/ベクトル/画像と完全一致。実図/実モデル表4頁を目視確認。現在入力は両方向6節点5部材、H1付きサンプルは8節点7部材。
- 更新前後の保護対象SHAにより、入力・原PDF/xls・既存oracle・0500/0600・その他出力が不変と確認。証跡: `tmp/pier-height-boundary-nodes/production-verification.json`。commit/pushなし。
