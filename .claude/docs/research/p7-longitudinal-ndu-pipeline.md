# P7 0710 → JRSNAP 5.2-L03 NDU 出力の現状調査

調査は読取り専用。元入力、コード、PDF/JSON、post、NDUは変更していない。新規成果物はこの調査資料と `tmp/p7-ndu-plan/input-snapshot-comparison.json`。対象版はユーザー指定の JRSNAP 5.2-L03、予定出力は `./post/線路方向.ndu`。

## 1. 現状経路

- 正規入口は `./run_design.py:3` → `pier_design.cli.main`。引数は input/output-dir/post-dir/overwrite/stage のみ。`--frameweb`、`--excel` は存在しない（`src/cli.py:47`–53）。
- CLIは入力バイトを1回だけ読み、同じSHAを全結果へ付与する（`cli.py:64`–78）。`0710` は現在入力から 0500 → 0600 → 正規0610 → 0710 をメモリ内で計算し、保存済み0610/0710 JSONやPDFを読み戻さない（`cli.py:71`–93）。
- 0610は部位別コンクリート強度の既存入力を `parse_longitudinal_design_conditions(data)` で取得する（`cli.py:80`–83、`src/longitudinal_design_conditions.py:80`–91）。Ecは RcDan テーブル補間による kN/m²（同ファイル:54–65）。
- 0710は正規0610 schema2を要求し、選択した旧監査情報から地震列車・桁・自重慣性力を採用する純粋アダプター（`src/seismic_longitudinal_calculator.py:173`–203）。結果は schema1 / stage0710 / direction longitudinal、8基本ケース・1組合せ（同:204–216、242–255）。
- 帳票レンダラは `src/seismic_longitudinal_report.py:431`、CLI接続は `cli.py:104`–118。最終0710は3ページ。renderは結果だけを使い、入力を変更しない契約がある（`./tests/test_seismic_longitudinal_report.py:142`）。
- 現行postの対象は0610と0620のみ（`src/frameweb_artifacts.py:33`–40）。`0710`単独はPDF/JSONの2件、allは6帳票12件＋FrameWeb2方向4件＝16件（`./README.md:21`、63–67）。
- GUI「保存して計算・PDF出力」は入力保存後に同CLIの `--stage all --overwrite` を起動する（`src/editor_gui.py:516`、`src/editor_calculation.py:168`–186）。既存実行ボタンに、新規の任意チェックを接続する候補となる。

## 2. 0710にある情報・ない情報

### 骨組

- `seismic_frame._physical_frame` は nodes/members/node_ids/sections/materials だけをallowlist複写し、support modelをコピーしない（`src/seismic_frame.py:66`–129）。
- 柱下端0.010mを既存H4から切り出す。柱長へ0.010mを加算しない。behavior=nonlinearは原本分類だけで、構成則・剛性・拘束は未定義（同:161–208）。
- 節点は高さ降順、部材は中点高さ降順に連番。node_idsと微小部材参照も更新する（同:132–158）。標準入力は節点1–7、要素1–6、微小要素4 = node4→5。H1ありでは増えるため7/6を固定してはいけない（同:193–216、`./tests/test_seismic_longitudinal_calculator.py:401`）。
- 0710 provenanceも「他部材の剛域化は今回再現しない」と明記する（`seismic_longitudinal_calculator.py:232`）。見本NDUの「微小要素以外は全剛域」を0710へ無条件適用すると既存骨組の意味が変わる。

### 荷重・符号

- D1/D2/Wp/Sw2/L/EQ1/EQL/EQ2 の8ケース。固定・増分・限定増分を保つ（`seismic_longitudinal_calculator.py:204`–216）。
- 列車Kh=0.20は適用済み。再乗算禁止。橋脚Khは1.00を検証し、式の因子と丸め結果の整合も確認する（同:112–125、128–169、199–202、229）。
- Wpは平水位、Sw2は2年確率を選ぶ。0610の旧組合せ全体は複写しない（同:188–196、225–230）。
- 0710の8ケースは力のグループであり、NDU向けnode/member loadを完成させた配列ではない（同:214–216、242–250）。再採番後の `frame.node_ids` の役割から載荷位置を解決し、NDU符号/座標規約へ変換する専用アダプターが必要。

### 支持・非線形・解析条件の欠落

- 0710は支持モデル、非線形構成則、応答解析を定義しない（`seismic_longitudinal_calculator.py:1`–5、230–254、`CONTEXT.md:23`付近の「検討モデルの骨組図」）。したがって、PDFの「ばね非表示」を固定支持や無支持へ読み替えてはいけない。
- 0500正規結果には方向別 long_term/short_term Kv/Ks/Kr があり、既存 `foundation_spring_set(foundation,'longitudinal')` が未丸めDoubleと出典を返す（`src/foundation_springs.py:27`–58）。これは既存0610用の線形ばねの取得経路であり、そのままJRSNAP耐震モデルの支持条件として採用する設計決定ではない。
- 支持地盤や基礎形状のraw値は既存0500 parserにある（`src/inputs.py:81`–166）。5.2-L03の回転ばね/直接基礎照査/解析制御へ必要な入力は、版別マッピングと不足判定を別途固める必要がある。

### 配筋の再利用

- raw `鉄筋` は `ReactionInput` / 0710.input へ含まれない。0710.inputは geometry/spans/train/dead/warnings/snow のみ（`seismic_longitudinal_calculator.py:181`、244、調査JSONのstored_0710_input_keys）。
- 配筋は既存 `rebar_model.load_member` → `section_geometry` → `member_preview` → `directional_rows(bars,'線路')` を再利用できる。線路断面は width=W6、height=B6、単位mm、配筋座標は左上原点X=直角/Y=線路（`src/rebar_model.py:1`–7、310–345、676–692）。
- `directional_rows` は実物の芯位置・径・材質で集計し、NDU SectReinへの候補となる（同:676–692）。同位置の異径/異材質を無断合算しない。
- GUI向けpreviewは欠落入力をwarningとして許す部分がある。NDU exporterは warnings / incomplete / stale manual_basis を明示エラーにするか許容仕様を定める必要がある（同:592–604、1038–1058）。
- 現在の柱入力には線路方向SD390/D22/有効本数10/pitch150がある（`./pre/input.json:663`–732）。方向別有効本数を帯筋の組数へ置換しない（`CONTEXT.md`の対応定義）。
- コンクリートEcは0710 frameでkN/m²、NDU断面でkN/mm²なら1e6換算が必要（`longitudinal_design_conditions.py:27`、54–65、`seismic_longitudinal_calculator.py:251`–252）。m→mm、N/Mの符号と単位も出典表へ残す。

## 3. 入力世代・現行資産の監査

調査時SHA256:

|ファイル|SHA256|
|---|---|
|`./pre/input.json`|`d8da41d8d87a04b33a35cc45226231564ebd1dc1dcdcf3abce397d7487887f78`|
|`./output/0710_線路方向荷重.json`|`b3589b770b72f68e2b8411b8bcb3d164b39228aaf8717375dcda4d4d84995d26`|
|`./output/0710_線路方向荷重.pdf`|`d2b9f888e0a27d9dad55bf1566a44dd817e6216b46e4846e1c830fb5e25a03b5`|

0710 JSONが記録する入力SHAは `0a17f5301371fead6383eb00d315f6984bfd21c8580fe2e861a12d088e67f408`（`./output/0710_線路方向荷重.json:1030`）で、現在入力と不一致。

ただし、そのSHAに完全一致するraw入力を `tmp/column-rebar-implementation/baseline/./pre/input.json` で発見した。これが指定0710生成時の再現可能な全入力。`tmp/column-rebar-implementation/baseline-sha256.json:8`も同SHAを記録する。

現行との差分は次の8項目のみ（構造比較の完全記録: `tmp/p7-ndu-plan/input-snapshot-comparison.json`）:

1. `鉄筋.version`: 1→2。
2. `鉄筋.柱.column_hoops`: 新規（外帯D22、線路D22/10本@150、直角D22/6本@150）。
3. `main_rows[0].distribution`: 両端＋中央ピッチ/端部芯108/ピッチ150を追加。
4. `main_rows[1].center_mm`: null→102。
5. 同 `cover_mode`: 自動→指定。
6. 同 `distribution`: 中央ピッチ250を追加。
7. 同 `per_face_count`: 11→9。
8. `materials.main`: `390`→`SD390`。

形状・荷重・地盤・コンクリート材料にはraw差分なし。正規ReactionInput全項目と0710材料の数値比較も差分ゼロ。単なるmtimeやJSON整形差ではなく、柱配筋の実入力が変わっている。初回NDUで旧配筋/現在の確定済配筋のどちらを採用するかは、継続的な同一run生成の設計と分けて確定すべき。0710 JSON単独から鉄筋や0500地盤rawを復元できると扱ってはいけない。

現行postは以下4件だけで `線路方向.ndu` は存在しない:

|ファイル|SHA256|
|---|---|
|`frameWebForJS.json`|`1abaa2b50e94bbc5eb833db63b40f2cfc84e9ea2248f1e6ed2b9f06213dbb5d2`|
|`frameWebForJS.provenance.json`|`72739abef4d26adc1f6b48eb780a5f9dd813f014500ea48b8874a68d6629666b`|
|`線路直角方向.json`|`b692a9ec5157af8daf0000bd31e70085b2fe697140515e3765322dde1f769dba`|
|`線路直角方向.provenance.json`|`dbbaf75326610adcc5a4d30fc93ae3e4faf271001da515ce3462b788c5db3ce8`|

## 4. 公開処理と専用manifestの提案

### 再利用する公開処理

- `ArtifactStaging` は出力先と同一filesystemに一時領域を作り、対応するpathへ書き出す（`src/artifact_publication.py:118`–159）。
- `validate_destinations` は入力とのパス衝突、重複、symlink、非通常ファイル、overwriteなしの既存ファイル、readonlyを拒否する（同:96–115）。
- `publish_outputs` は全旧成果物退避後に置換し、final_validator成功までbackupを保持。途中失敗時は全復元、復元失敗時はjournal/backupを残す（同:162–246）。NDUもこの同じ公開トランザクションに含める。
- JSON生成/描画/既存FrameWeb検証を全てstageしてから公開する現在順序を維持する（`cli.py:98`–157）。

### 既存FrameWeb schema2へNDUを押し込む問題

- `FrameWebSpec` / `_spec` は0610/0620固定、nativeをUTF-8 JSONとして `validate_frameweb_input` へ渡す（`frameweb_artifacts.py:21`–46、143–169）。
- 全sidecarに `_spec(peer_stage)` と `_validate_direction` を適用するため、単に `0710.sidecar` を登録するとNDUをFrameWeb JSONとして扱って壊れる（同:190–223）。
- 推奨: 新設 `jrsnap_artifacts.py` にNDU専用パス/sidecar/manifest/検証を持たせる。既存FrameWeb台帳/metadataの役割は保つ。CLIの公開destinationsだけ両系統を合成し、同じArtifactStagingとpublish_outputsを使う。
- NDU専用sidecar候補は `post/線路方向.ndu.provenance.json`。target=JRSNAP5.2-L03、exporter/schema/template版、入力SHA、0710 PDF/JSON SHA、NDU SHA、入力→NDU対応表、補助設定出典を記録。FrameWebの `線路直角方向.provenance.json` と名前が衝突しない。
- allでは同じpublication_idをNDU専用manifestへ渡し、GUIが両validatorと共通publication_idを確認する。FrameWeb schema2側の14件manifest＋2 sidecarsを変更せず保てる。NDU側は0710関連3成果物と出典に限定してよい。
- NDU有効時だけ0710単独は4件（PDF/JSON/NDU/専用sidecar）、allは18件となる。無効時は0710単独2件/all16件の現状を維持。0610/0620単独は従来4件、0500/0600/0720単独は従来2件。NDU検証はFrameWebの有無に関わらずNDU有効時に必須。

### 非干渉境界の提案

- 親の最終設計方針に合わせ、新規opt-in `--jrsnap` を提案する。`--stage 0710 --jrsnap` または `--stage all --jrsnap` の時だけNDUと専用sidecarを同時生成。GUIは「JRSNAP入力も出力」チェック（既定off）を用いて同じall経路へ接続する。
- 追加調査でDf/GAM2は既存地盤条件と平水位から導出可能と確認した（[根拠](p7-longitudinal-ndu-soil-derivation.md)）。NDU固有の適用範囲・導出検証は有効時だけ実行し、従来の0710/all/GUI生成を維持する。
- `0610/0620/0500/0600/0720 --jrsnap` は明示CLI error。無指定の各段階はNDUを要求せず、既存NDUを変更しない。有効/無効判定は入力読込や出力作成より前に行う。
- `--post-dir` の現在規則を共用: 通常outputならP7/post、任意outputならその配下post（`frameweb_artifacts.py:49`–54）。検証用tmp出力から本番postへ書かない。
- `--frameweb` / `--excel` は現在存在しないため、この新規 `--jrsnap` と架空の既存フラグ組合せを計画しない。
- 0710 PDF/JSONの形式・内容・3ページ・ばね非表示は維持。NDU用解析条件を0710帳票骨組へ混入させない。
- 初回起点は前節の8項目差分を説明して決定。指定PDFへの対応を守るなら旧SHAのrawスナップショット＋採用配筋の明示が必要であり、無言の世代混合は避ける。

### 任意オプションの最小伝播経路

1. `cli.py:47`–63 に `--jrsnap` とstage組合せ検証を追加。`publication_paths` の既存返り値を変更せず、専用 `jrsnap_publication_paths` の2件を有効時だけdestinationsへ合成する。
2. `CalculationJob` に `jrsnap: bool = False` を末尾既定フィールドで追加（`editor_calculation.py:46`–54）。`CalculationController.start(..., *, jrsnap=False)` がジョブ生成時に選択値を固定する（同:221–226）。既存呼出互換を保つ。
3. `_run_process` は `job.jrsnap` がTrueの時だけcommandへ `--jrsnap` を追加（同:168–172）。途中でGUIチェックが変わっても実行中ジョブには影響させない。
4. `validate_outputs` は既存16件に、job.jrsnap=True時だけNDU2件を加える。専用validatorを呼び、before/after snapshot、成功後`check_current_outputs`の対象へ含める（同:125–147、Controller._verified_outputs:213）。無効時は以前生成されたNDUを今回成功済みと扱わない。
5. GUIの計算ページへ既定offのBooleanVar/Checkbuttonを配置（`editor_gui.py:506`–523）。`_dispatch_calculation` がその値をstartへ渡す（同:699–701）。実行中はチェック無効化。チェック変更は次runの選択であり、前runのジョブ/検証集合を書き換えない。
6. NDU専用manifestへenabled/target/program versionを記録し、GUIはjobの選択と照合。既存FrameWeb schema2は同じ16件体系を維持し、専用2件は新validatorが保証する。既存の16件fixture/試験はdefault offで引き続きPASSさせ、onの18件ケースを新規追加する。

## 5. 変更ファイル候補

### 新設候補

- `src/jrsnap_export.py`: 0710計算結果＋同一runで確定した柱配筋/支持/解析設定から、5.2-L03用のモデル・荷重・断面を構築する純粋変換。I/O・再計算を持たない。
- `src/jrsnap_ndu.py`: CP932/CRLFの5.2-L03 serializer、再読込validator、カウント/参照/符号/荷重型検証。具体的モジュール分割は規模に合わせる。
- `src/jrsnap_artifacts.py`: 専用path/manifest/validator。同じ公開トランザクションへ参加。
- `src/jrsnap_design_conditions.py`: 支持・非線形・材料係数/解析設定の出典付き型と必須値検査。raw入力スキーマ追加が必要なら既存inputモデル/UIにも限定追加。
- `src/assets/jrsnap_52_*.ndu` または対応する構造化template: 版確認済の静的規約だけ。Example案件値を日常runtimeの入力元にしない。
- `./tests/test_jrsnap_export.py`、`test_jrsnap_ndu.py`、`test_jrsnap_cli.py`、`test_jrsnap_publication.py`、独立fixture。

### 変更必須または候補

- `src/cli.py`: `--jrsnap`、0710/all opt-in分岐、raw入力から配筋/専用設定を読み取る、exporterを0710と同じ計算結果へ接続、NDU bytes/sidecarをstage・verify・publish、結果path表示。
- `src/editor_calculation.py`: jobのjrsnap選択伝播、有効時だけNDU/sidecar追加、専用validator/世代確認、成功後の再確認を16または18件へ適用（現状 `validate_outputs`:113–152）。
- `src/editor_gui.py`: default offの任意チェック、startへの選択伝播、実行中disable、選択に応じた完了表示（現状:506–523、699–701、725）。
- `src/frameweb_artifacts.py`: 専用manifest方式なら内部schema2変更を避けられる。中立の台帳へ切り出す別案を採るなら既存public API互換が必要。
- `./README.md`: 0710/all出力一覧、postと上書き、NDU target版、初回入力起点と支持/解析スコープ、構造解析を自動実行しないことの説明。
- `CONTEXT.md`: NDU入力モデルと荷重帳票/解析結果の区別が必要なら用語を追記。既存用語を変えない。

## 6. 既存試験・追加が必要な検証

### 再利用すべき試験

- `./tests/test_seismic_longitudinal_calculator.py:101` 独立見本値/ケース、:133 符号/係数二重適用防止、:147 detached/support排除、:240 形状/単重/H1感度、:281 不正値、:366 微小部材、:401 再採番順、:418以降 不正H4/座標精度。
- `./tests/test_seismic_longitudinal_report.py:69` 3頁/表示値、:142 snapshot-only、:162 微小部材/番号、:202 形状差、:236 表示精度、:301 描画失敗時無変更。
- `./tests/test_seismic_longitudinal_cli.py:46` 1回読込/同一upstream、:95 単独/all値一致、:109 選択外保護、:126 生成/公開失敗復元、:171 改変/欠落0710検出。現状 :87 の「postなし」期待と :92 の16件期待はdefault offで維持し、onの4/18件試験を追加。
- `./tests/test_frameweb_cli.py:94` 0710 default offのpost非変更期待を維持。:126 overwrite/衝突、:163 公開失敗復元、:216 既存sidecarのmanifest/世代、:243 方向別保護、:282 final bytes validation失敗。NDU有効時にも既存FrameWeb native規約を変えないことを別途確認。
- `./tests/test_frameweb_publication.py:41` 台帳契約、:66 staged bytes、:80不完全manifest、:100旧schema1制限、:119方向/破損。専用manifest方式では既存期待を原則維持。
- `./tests/test_artifact_publication.py:15` cross-dir復元、:40重複、:80復元失敗backup保存、:162 final validate前backup保持、:181中断journal、:310pending marker。機構の全面改修は不要。
- `./tests/test_editor_calculation.py:43` fixture生成器、:149/:468 16件assert、:293各artifact欠落、:302改変0710、:383入力外部変更、:425実CLI、:463成功後のartifact改変。NDU2件のcoverageを追加。
- `./tests/test_column_rebar_reference.py:81` 見本独立Oracle、:121 76本と線路11段/直角31段の全配置、:146現行P7一致。NDU行をこの独立fixtureと比較し、実装から期待値を生成しない。
- `./tests/test_frameweb_export.py:39` 正規結果native化、:76変形、:96非連番、:171再読込検証、:195精度喪失拒否は新exporter設計のパターン（FrameWebの規約値自体はNDUへコピーしない）。

### 新規試験の焦点

1. 見本NDUから独立に固定した5.2-L03規約・カウント・enum・Section/NonLin/Joint/Member/Load/Conbを検証。CP932厳格encode、CRLF、ヘッダー、再読込とJRSNAPでの読込確認を分離する。
2. 保存済0710PDF/JSONやExampleファイルを削除/アクセス禁止にしても、選択した入力だけから新規出力できること。初回旧入力の場合は採用SHAのsnapshotを明示。
3. H1>0、H2/H3ゼロ、偏心/非対称フーチング、高さ変更、node/member再採番、非整数値、微小要素分割前後の鉛直/水平合力とモーメント一致。
4. 荷重型 fixed/incremental/limited_incremental、左向きH、Wp負N、M符号、0荷重ケースを保持。Kh0.2二重適用を検出。
5. 配筋未完成、異径/異材質同距離、manual stale、対応外鋼種/鉄筋径/断面/支持設定を明示拒否。入力や既存postに書かない。
6. default offの0710単独2件/all16件、onの0710単独4件/all18件、対応外stage+flag拒否、他stage不干渉、post-dir隔離、上書き/入力衝突/失敗時全復元、専用manifest欠落/改変/異世代をGUIとCLI双方で検出。実行開始後のcheckbox変更がジョブへ混入しないこと。
7. NDU nativeを実アプリ5.2-L03で開く/保存できる互換検証は版別fixtureまたは隔離tmpで実施。解析実行は出力機能テストと別の承認範囲・目的として扱う。

## 7. 調査制約

- 該当AGENTS.mdは `rg --files --hidden -g AGENTS.md` で見つからなかった。
- context-loaderのmissingは `[".agents/rules", ".agents/STATE.md", "PROGRESS.md", ".agents/docs/DESIGN.md"]`、unreadable=`[]`、warnings=`["DESIGN.md is still the uninitialised /init template; run /init to populate it"]`。design.placeholder=true、progress.entries=0。既存 `CONTEXT.md` と `.agents/docs/plans/seismic-longitudinal-loads-report.md` を根拠にread-only調査した。
- ここでは既存テストを実行していない。テスト名・assert・検証対象をコードから確認した。製品変更も正式成果物再生成も行っていない。
