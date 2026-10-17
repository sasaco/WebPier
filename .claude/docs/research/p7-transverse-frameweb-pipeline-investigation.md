# P7 線路直角方向 FrameWeb 出力経路の調査

調査日: 2026-10-16。計画前の読取調査。製品コード・入力・既存成果物・既存計画は変更していない。現在の正式資料は `./output/0620_直角方向荷重.pdf`（12頁）で、ユーザー指定の「0620_線路直角方向荷重.pdf」に相当する内容を持つ。生成先は指定どおり `./post/線路直角方向.json` とし、通常0620/all計算への自動接続を前提とする。

## 結論

実行時はPDFを解析せず、同じPDFを生成する正規0620結果から変換する。0610とは異なり `actions[].points/line_loads` に載荷位置とN/H/Mが直接そろっているため、荷重の共通変換は単純化できる。一方、17基本と15Defineが別体系で、単線L/I上り下りの選択相関を維持する必要がある。

現在は各L/Iが同じ短期ばね2を持ち、列車を使う全組合せで衝撃も併用する。したがって用途別のL+I複合補助荷重を作り、単線は同方向のL+Iをまとめたup/downの2候補を一つのDefineから選ぶ方式が適する。複線も同じ方式へ統一でき、現定義なら5補助loadと4補助Defineで足りる。LFとWの正負は独立である。16組合せを相関付きで展開した物理状態は現在37通りになる。

既存の線路方向FrameWeb計画は未実装（`p7-longitudinal-frameweb-input.md:5`）。新規変換器・publisherが既に存在する前提を置かず、共通骨組／荷重直列化・方向別ケース構築・共有出力公開を一度だけ設計する。

## 現物の世代

| 対象 | SHA256 |
| --- | --- |
| pre/input.json | `82d5a2769dfb36b069263c7849e30fdd4a5a23b8c69700613603c51ba430628b` |
| output/0500_直接基礎.json | `2fd013e9b75180b534e9dc2f64bcecd29c3d3b11c23fe6cca242bb9672d39745` |
| output/0600_上部工反力.json | `ba2c335818a03cee1c8bd86692a980ec32871d3a2d56621a7e683892a10e12b4` |
| output/0620_直角方向荷重.pdf | `64a5ac2380530b4fb1996889b11a375a31fc7b6821669731d022eba1fff3140a` |
| output/0620_直角方向荷重.json | `07f76b318c482d92353a6b037c2bb522fbcdb44158a513322066cbbbe49a2bca` |

現入力と現コードから0500/0600/0620をメモリ内で再計算し、CLI同等のJSON直列化とWindows CRLFで照合した。3ファイルとも保存bytesに完全一致。入力SHAも3結果のprovenanceとPDF各頁で一致する。既存成果物を再生成・上書きしていない。

`transverse-example2-parity.md:283–288` の最新12頁公開版と一致する。先行17頁のPDF SHAを現公開版と混同しない。受入済み差はD1天端Nの0.01、橋脚用衝撃低減、風M。これらをExample値へ戻さない。同計画の「longitudinal_actions未実装」等の当時の状態は現在の依存関係へ読み替えない。

調査の機械可読記録は `tmp/p7-transverse-frameweb-plan/pipeline/investigation-evidence.json`。入力／PDF／結果／主要ソースのSHA、全16組合せの非零係数、候補列挙、相関適用前後の件数を持つ。応答解析結果ではない。

## 正規データ契約

| 参照箇所 | 内容と輸出上の意味 |
| --- | --- |
| transverse_calculator.py:24–65 | schema_version=2、stage=0620。正規actionsとケースを生成。旧計算は呼ばない |
| transverse_calculator.py:72–93 | 直角方向A/I、部位材料、Kr_transverse、frame v2を構築 |
| transverse_actions.py:24–40 | `points`、`line_loads`、`rows`、`table_totals`を分離 |
| transverse_actions.py:75–88 | 支承別分担率へraw×有効係数を一度適用、表N/Mを採用 |
| transverse_actions.py:91–134 | 用途別I、支点0.1kN丸め残差を絶対分担率で分配 |
| transverse_actions.py:137–180 | D1/D2の異なる作用位置、D1分布、3水位 |
| transverse_actions.py:199–234 | 車両横荷重、風の天端H/Mと柱qH |
| transverse_actions.py:262–300 | 非零Defineごとに解決済み候補配列を生成。全variant展開はしていない |
| transverse_example2_cases.py:19–87 | 17基本、15Define、16名目組合せ、8抽出の原定義 |
| transverse_example2_cases.py:114–157 | ばね・領域、単線相関group、有効係数、usageを付与 |

輸出する実荷重は `points` と `line_loads` のみを読む。`rows` と `table_totals` は同じ作用の内訳・表表示であり追加載荷しない。とくにD1/D2のtable_totalsは天端分だけで、footing_centroidの力を含まないため、table_totalsのみを載荷すると基礎自重／上載土が欠落する。

0620の `legacy_audit` は旧関数名・出典だけで、0610のような旧セル計算全体ではない。地震・遠心力・別種の横圧を旧監査側や0600から勝手に追加しない。正規17基本には独立遠心ケースはない。車両横荷重LFは `0.2×axle_load` の移動荷重から求める定義で、0610のロングレール／制動とは別である（transverse_actions.py:199–217）。

## 骨組・材料・支持と方向差

PDF p1–2。P7 IDは上からの連番ではなく意味付きID。現節点は `(id,x,y)=(1,0,10.3),(2,0,2.7),(3,0,1.350000023841858),(4,0,0),(5,0,8.3),(6,0,7.6000000000000005)`。役割はcap_top=1、footing_top=2、footing_centroid=3、support/footing_bottom=4、h2_h3=5、h3_h4=6。

部材1=`1→5`、2=`5→6`、3=`6→2` は弾性。材料は1/2=beam、3=column。部材4=`2→3`、5=`3→4` は剛域。全弾性部材の現A=12.15 m²、I=20.50313 m⁴、幅2.7m、深さ4.5m。現fck=27、E=26,500,000 kN/m²。0610のI=7.38113を流用しない。部位材料やH1有無が変わる場合も正規frameの参照を保つ。

| ケース | Ks→tx (kN/m) | Kv→ty (kN/m) | Kr→rz (kN m/rad) |
| --- | ---: | ---: | ---: |
| 1 長期 | 4,262,769 | 12,788,244 | 86,320,647 |
| 2 短期 | 8,525,475 | 25,576,488 | 172,641,294 |

ばね出典は正規0500の `Kr_transverse`。Single化した86,320,648等や線路方向Krを使わない。基本1–8は長期1、9–17は短期2（PDF p10、transverse_example2_cases.py:115–119）。支持は節点4。H1分岐、H2/H3/H4零長による節点統合は既存frameが解決しているため輸出で再推定しない。

## 17基本の数値・位置・符号

正規Nは下向き、Hは正方向、Mは帳票の作用モーメント。FrameWeb nativeへの対応は `load_node.ty=-N, tx=H, rz=-M` を前提に外部ソフト契約と照合する。分布は `qN` をグローバルgy負、`qH`をgx正へ変換し、`member_ids`ごとに個別指定する。JSON精度を保持し、PDFの表示桁へ再丸めしない。

| 基本 | 意味 | 天端 N/H/M（kN、kN m） | その他の荷重 | PDF |
| ---: | --- | --- | --- | --- |
| 1 | D1 | 8299.52 / 0 / 0 | 重心N=4167.4501953125、qN=297.68 | p3 |
| 2 | D2 | 780 / 0 / 0 | 重心N=1830.5999755859375 | p3 |
| 3 | WP1 | － | 重心N=-2381.39990234375、M=-0 | p4 |
| 4 | WP2 | － | 重心N=-1701、M=-0 | p4 |
| 5 | WP3 | － | 重心N=-0、M=-0 | p4 |
| 6 | S2 | 710 / 0 / 0 | － | p4 |
| 7 | S10 | 1140 / 0 / 0 | － | p4 |
| 8 | S30 | 1270 / 0 / 0 | － | p4 |
| 9 | L上り | 567.39 / 0 / 1210.08 | 無係数 | p5 |
| 10 | L下り | 567.39 / 0 / -1210.08 | 無係数 | p5 |
| 11 | L複線 | 1134.77 / 0 / 0 | 無係数 | p5 |
| 12 | I上り | 171.7 / 0 / 364.43 | ultimate、a=1.0 | p6 |
| 13 | I下り | 171.7 / 0 / -364.43 | ultimate、a=1.0 | p6 |
| 14 | I複線 | 328.7 / 0 / 0 | ultimate、a=1.0 | p6 |
| 15 | LF | 0 / 111.69 / 430.01 | 正負候補 | p7 |
| 16 | W1列車あり | 0 / 305.87999725341797 / 2124.358680408477 | qH=4.050000000000001 | p7 |
| 17 | W2列車なし | 0 / 611.75 / 4248.643817901611 | qH=8.100000000000001 | p8 |

基礎荷重のM=0、雪・複線M=0は現在の対称入力で得られた値であり固定値ではない。位置・分担・土の偏心が変わればMも保持する。特に負の支承分担率、Σrate=0でも偶力M≠0が成立する。Nが0だけでケースを落とさない（transverse_actions.py:105–127、test_transverse_actions.py:88,201–255）。

0620の基本Iはultimate/a=1.0。0610の代表基本Iはultimateの採用係数付きであるため、共通変換器が「基本Iを1.23で割る／掛ける」といった推定をしない。

風・LFのMは天端節点での付加モーメント。Hの高さを基礎底まで運んだMではない。基礎底まわりの物理符号検証では天端H×10.3も加算する。柱風qHはy=2.7～10.3の7.6m区間で、合力位置はy=6.5。正方向の基礎底荷重（時計回りの絶対量）参考値:

| 荷重 | 合計Fx | 時計回りM絶対量 |
| --- | ---: | ---: |
| LF | 111.69 | 1580.4170000000001 |
| W1 | 336.659997253418 | 5474.992652118683 |
| W2 | 673.3100000000001 | 10949.808817901612 |

風を単一の天端HにまとめてqHを落としたり、Mを「既に基礎底まわり」と解釈してH×高さを差し引いたりしない。Exampleとの差Mは承認済みであり、風H/Mを書き換えない（transverse-example2-parity.md:19–31）。

## Define・相関・補助ケース

原Define1–8は基本1–8の一対一。Define9=L単線 `[9,10]`、10=L複線 `[11]`、11=I単線 `[12,13]`、12=I複線 `[14]`、13=LF `[15,-15]`、14=W1 `[16,-16]`、15=W2 `[17,-17]`。Define頁では複線記号がL3/I3、係数頁ではL2/I2であり、この別名を誤参照扱いにしない（PDF p10–11）。

係数は15Defineへ作用する240セルであり17基本へ直接掛ける表ではない。Define9/11は両方 `selection_group=single_track`、候補は `direction=up/down, compatibility_group=single_track`（transverse_example2_cases.py:123–132、transverse_actions.py:294–295）。L上り+I下り／L下り+I上りは無効な組合せである。

一方LF/W1/W2の符号には相関groupがない。LFとW1が共存する組合せでは `(+,+),(+,-),(-,+),(-,-)` を保持する。符号反転は該当横作用のH/M/qHだけに作用し、D/L/I等の鉛直Nや偏心Mへ波及させない。

L/Iは解決済み値の採用が必要。例: 複線L最大は `1134.77×1.35=1531.9395` でなく1531.94。複線I最大は `328.7×1.35=443.745` でなく443.7。使用性I複線は `328.7×0.75=246.525` でなく245.3。使用性I単線Mは `364.43×0.75=273.3225` でなく272.73。

提案する意味付き補助集合（IDは計画で固定する候補）:

| 補助load | 補助Define | 意味 | L N/M | I N/M | 合成N/M | 元組合せ |
| ---: | ---: | --- | --- | --- | --- | --- |
| 18 | 16 | double ultimate maximum | 1531.94 / 0 | 443.7 / 0 | 1975.64 / 0 | 1,10 |
| 19 | 17 | double ultimate ordinary | 1395.77 / 0 | 404.3 / 0 | 1800.07 / 0 | 2,8,11 |
| 20 | 18 | double service | 1134.77 / 0 | 245.3 / 0 | 1380.07 / 0 | 5 |
| 21 | 19候補1 | single service up | 567.39 / 1210.08 | 128.5 / 272.73 | 695.89 / 1482.81 | 7,15,16 |
| 22 | 19候補2 | single service down | 567.39 / -1210.08 | 128.5 / -272.73 | 695.89 / -1482.81 | 7,15,16 |

全補助は短期ばね2。補助Define16–18は正方向の一候補、19はload21/22の二択（`[21,22]`）であって `[21,-21]` ではない。現在の上下対称を前提に荷重全体を負にするとNまで上向きになるため誤り。非対称入力では上下Nが異なる場合もある。

原17基本／15Defineは追跡用に保持し、native combineのL/I二列を対応する一つの補助Define係数1へ置換する。D/W/LF等は元Defineを使い、元L/I列も同時に残して二重計上しない。組合せID1–16、pickupID1–8は保持できる。JSON配列の順番や数値偶然一致による重複排除をせず、family/usage/effective L factor/effective I factor/track/springを契約として補助を構成する。新しい係数パターン・片方だけのL/I・ばね不一致が現れたら無条件合成せず明示検証する。

係数0で名目項が消える時は無効参照を作らず、その組合せのL/I補助を不使用にする。既定の補助スロットをゼロの有無で詰め直さない方針なら、ゼロケースを省略するソルバーとの連携を別途検証する。応答上の力・モーメントが全て0かどうかと、Nのみ0は区別する。

## 全16組合せの有効項と状態数

以下でTmax/Tult/Tsvc2/Tsvc1は上表のL+I補助。LF±とW±は独立候補。元の240名目係数は正規結果と独立fixtureで保持し、この解析用置換表と区別する。

| ID | 用途 | 解析用の有効項 | 状態数 |
| ---: | --- | --- | ---: |
| 1 | 躯体破壊 列車最大 | 1.1D1+1.2D2+S10+Tmax+1.23LF±+W1± | 4 |
| 2 | 躯体破壊 車横最大 | 1.1D1+1.2D2+S10+Tult+1.35LF±+W1± | 4 |
| 3 | 躯体破壊 風最大 | 1.1D1+1.2D2+S2+1.2W2± | 2 |
| 4 | 躯体破壊 雪最大 | 1.1D1+1.2D2+S30 | 1 |
| 5 | 躯体使用性 永久+変動 | D1+D2+S2+Tsvc2 | 1 |
| 6 | 躯体使用性 永久 | D1+D2+S2 | 1 |
| 7 | 躯体使用性 変動 | Tsvc1(up/down) | 2 |
| 8 | 躯体復旧性 列車最大 | D1+D2+S10+Tult+1.23LF±+W1± | 4 |
| 9 | 躯体復旧性 雪最大 | D1+D2+S30+W1± | 2 |
| 10 | 基礎安定 列車最大 | 1.1D1+1.2D2+WP3+S10+Tmax+1.23LF±+W1± | 4 |
| 11 | 基礎安定 車横最大 | 1.1D1+1.2D2+WP3+S10+Tult+1.35LF±+W1± | 4 |
| 12 | 基礎安定 風最大 | 1.1D1+1.2D2+WP3+S2+1.2W2± | 2 |
| 13 | 基礎安定 雪最大 | 1.1D1+1.2D2+WP3+S30 | 1 |
| 14 | 長期支持 | D1+D2+WP2+S2 | 1 |
| 15 | 短期支持 低水位 | D1+D2+WP3+S2+Tsvc1(up/down) | 2 |
| 16 | 短期支持 高水位 | D1+D2+WP1+S2+Tsvc1(up/down) | 2 |

合計37状態。単線L/Iを独立直積にすると組合せ7/15/16が各4通りとなり全43状態へ誤拡大する。雪最大組合せ9でW1が参照されているのは現在の原定義であり、名称からW2へ差し替えない。

抽出所属は `[1,2,3,4] / [5] / [6] / [7] / [8,9] / [10,11,12,13] / [14] / [15,16]`（PDF p12、transverse_example2_cases.py:78–87）。元16組合せを保持する上記補助方式ならpickup番号は変更不要。

## CLI / GUI と未実装線路計画との統合

現 `cli.py:96–115` は同一入力から0500/0600を各1回計算し0620を生成する。0620は0610を計算しない。出力部 `125–137` は8成果物を単一output内stagingから公開する。`editor_calculation.py:118–149` の検証対象も8成果物で、`paths[::2]` が4PDF抽出を担う。既存の未実装線路計画を読み、共通部分を二重実装しない。

推奨構成:

- 純粋な共通骨組／支持／点・線荷重serializerと、0610/0620別の作用adapter・case builderを分ける。0620のpoints/line_loadsを標準化契約として扱える。方向別schemaを曖昧なキー存在判定だけで混在させずstageで明示する。
- stage別の出力名registryを持つ。現線路計画に従う0610は `frameWebForJS.json` と同名provenance、0620は `線路直角方向.json` と `線路直角方向.provenance.json`。ユーザーが線路側名称も改訂した場合はregistryへ反映する。
- 0620単独は既存0620 PDF/JSON＋直角post2件、0610単独は線路側だけ。両方向を実装したallは既存8＋post4=12成果物。0500/0600単独では両方向postを変更しない。
- 共通 `--post-dir` 解決を1関数で定義する。production outputならP7/post、それ以外はoutput_dir/post、明示post-dir優先。カスタム検証がproductionへ漏れないようにする。
- 共通publisherは出力親ごとのstaging/backupと全体journalを持ち、全旧版退避→全配置→失敗時逆順復元。跨volumeのos.replaceを避ける。方向別provenanceのnative/PDF/計算JSON/input SHAを生成し、通常JSONへ独自metadataを混ぜない。方向名を含むバックアップキーにして同名一時ファイル衝突も防ぐ。
- GUI CalculationJobへpost先を保持。post2方向のnative+provenanceまで検証してから成功表示。PDF一覧は明示的な既存4PDFにし、追加JSONで `paths[::2]` を壊さない。完了後改変検知にも4postを含める。
- 共通publisher・CLI/controller変更は所有者を1人にする。後から線路計画を実装するときに直角stage登録を失わない回帰条件を置く。製品計算式・0620帳票の変更は必要ない。

主な対象候補: 新 `frameweb_export.py`（共通）、`frameweb_transverse_cases.py`（0620固有）、既存線路計画の `frameweb_cases.py`、共通 `artifact_publication.py`、変更 `cli.py/editor_calculation.py/README.md`。共通線路側が先行したら新規ではなく拡張として最新コードを読む。名称は実装計画で確定する。

## 検証案と既存試験

1. PDF p1–10から独立転記した6節点/5部材、直角I、6ばね成分、17基本、15Defineをfixtureへ保存。原本とP7の承認済み差を分離し、exporter自身で期待値を作らない。
2. 基本作用について支持ケース別・節点別・部材別の作用ベクトルを独立照合する。D1の基礎自重と分布の二重加算、D2基礎荷重欠落、風qH欠落、H/M高さ混同、符号反転を検出する。
3. 240名目係数と補助置換を照合し、37状態の有効候補を独立列挙する。native展開と同じ集合であり、単線交差組合せ6状態が混入しないことを確かめる。LF/Wの混合符号も全て検証する。
4. helperは正規resolved候補のL/I物理荷重を同じばね内で加算する。非標準ρ/service、ρ=0、signed ratesの完全/近接相殺、非対称支承、丸め境界、上下N差、単線M≠0・N=0を試験する。元Iを係数倍する実装を検出する固定反例は使用性N245.3、単線M272.73、最大N443.7。
5. 直角と線路でI/Krが異なること、材料差、H1偏心、零長によるID統合、重心端部を検証。グローバルgx/gy分布の部材向き・長さをFEMPython片持梁で確認する。
6. FEMPythonは各基本荷重を自身の支持ばねで解き、その結果を組み合わせる。長短期混在を単一ばねで合成載荷して比較しない。L+I helperの解析応答は同じ短期ばねでのLとI別解析の和と一致すべきである。基本反力釣合いと37状態の応答包絡を独立チェックする。
7. CLIは0620単独の4成果物、0610単独との非干渉、allの12成果物、custom post-dir、変換失敗、post書込/lock、最後のpublish失敗、復元失敗、既存両方向post保護を検証。GUIは片方向native/sidecarの欠落・改変・別世代を成功扱いしない。

関連既存試験: `test_transverse_actions.py:30–180`（載荷位置、分担、用途、風、材料）、`:201–255`（signed impactの相殺と残差）、`test_transverse_example2_cases.py:27–75,97–220`（全定義、相関参照、係数）、`test_transverse_foundation_routing.py:81–186`（6ばね、方向、macro非依存）、`test_transverse_cli.py:38–208`（独立stage、依存各1回、保護／衝突／材料）、共有frame/controller試験。今回の調査では製品テストの追加／実行や成果物再公開はしていない。

## 残る外部契約

nativeのDefineが候補をどのように包絡するか、複合helperを使うnative JSONの直接解析、GUI保存時の数値変換、空荷重省略時の参照、負ケースの展開はFEMPython調査担当の実測へ合流する。37状態の一致は正規作用定義の物理整合性であり、部材断面照査や構造安全性の完了を意味しない。

## 調査中の並行変更（開始時と区別）

2026-10-16追記。上記の開始時点では線路方向FrameWebは未実装だったが、その後別作業が実装を開始した。以下は読み取った**実装途中のAPI**であり、検証・公開・完成を確認した意味ではない。直角計画では既存変更を継承して拡張し、新規ファイル作成や旧cli復元で上書きしない。

| 現在追加／変更中のAPI | 0620計画への具体的な変更 |
| --- | --- |
| `frameweb_artifacts.py:18` `resolve_post_dir(output_dir, post_dir=None)` | production/customの既定解決が既に存在。再実装しない |
| `frameweb_artifacts.py:12–15,26` `frameweb_paths(post_dir)` | 0610のstem/native名/sidecar名/規約版を定数固定。0610既定引数互換を保ち、stage別仕様で0620の`線路直角方向.json`とsidecarを追加する |
| `frameweb_artifacts.py:30` `build_provenance(..., correspondence)` | input SHA、native/result JSON/PDFの実bytes SHA、各basename、correspondenceを持つ。方向別convention_version・stageを導入してbinding先を取り違えない。現関数の3対象SHA計算を流用 |
| `frameweb_artifacts.py:46` `validate_frameweb_artifacts(...)` | 0610のファイル名を固定し、native validatorも0610専用。stage別のファイル集合・規約版・validatorへ明示dispatch。結果JSONの入力SHAだけでなくstage/directionも照合する |
| `frameweb_export.py:273` `FrameWebExport(document, source_mapping)` | 出力オブジェクトとsource_mapping契約は共用可能。骨組生成`:291–311`も共通化可能 |
| `frameweb_export.py:65–150` `_validate_frame` | 部位/参照/非零長/材料/正のばね検証は共用可能。ただし`:88`はlongitudinal固定。期待directionを引数化し、0620にKr_longitudinalを許さない |
| `frameweb_export.py:157–197` `_actions/_load_case` | 0610の基本番号と荷重形を固定、分布gyのみ。0620へそのまま利用不可。共通の疎点・線作用serializerを抽出し、0620adapterからpoints/line_loadsとgx/gyを渡す |
| `frameweb_export.py:278` `build_frameweb_input` | 現stage0610限定を保持するwrapper＋明示0620入口、またはstage dispatchで拡張。source_documents/exporter_version/member_load規約も方向別にする |
| `frameweb_export.py:342` `validate_frameweb_input` | load/define28、正負Define13–20、分布gy、原L/I列9–12不使用を固定。単に件数を緩めるのでなく、共通構造検査＋0610/0620固有規約検査へ分ける。0620はload22/define19、track連動、gx風が必要 |
| `frameweb_export.py:232–269` `_validate_action_vectors` | 0610の20成分・単一水平sign・28variantを固定。0620は候補とsingle_track相関から37状態を検証する独立関数が必要 |
| `frameweb_cases.py:46,62` `FrameWebCases` / `build_frameweb_cases` | dataclass形式は流用可能だがcase builderは0610専用20基本・補助21–28・20成分を固定。0620固有case builderを新設し5複合helper/4Defineを実装 |
| `artifact_publication.py:21,38,81` `validate_destinations/ArtifactStaging/publish_outputs` | 複数親stagingと復元が追加済み。0620で別publisherを新設しない。12成果物集合と両sidecar末尾公開へ拡張し回帰検証 |
| `cli.py:53,84,103–119` | post_outputsとframewebが単一0610値。stage→export/spec/pathsの集合へ変え、0620選択時も対応2postを生成・検証し同じpublish集合へ追加 |
| `editor_calculation.py:56–64,123–158,174–178,210–213` | post_dir保持・CLI明示渡し・明示4PDF抽出は実装途中で追加済み。10成果物の0610sidecar検証を方向別2回／計12成果物へ拡張。旧`paths[::2]`修正を再実装しない |

この追記時点のCLI `--post-dir` helpは「0610/allのみ」で、0620単独ではpostを作らない。直角追加はhelp・stage選択・provenance validator・GUI監視・回帰試験を一緒に更新する。新APIの構成や行番号は並行作業で変わり得るため、実装開始時に再読込して差分を限定する。
