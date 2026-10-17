# P7線路方向 FrameWeb入力 実装検証

実施日: 2026-10-16。対象は[実装計画](../plans/p7-longitudinal-frameweb-input.md)。検証データは `tmp/p7-frameweb-implementation/` に保存した。

## 実装と数値の対応

正規0610結果を純粋変換し、基本20荷重と用途別L/I補助8荷重を生成する。補助ID21～28とDefineは固定し、Combineでは補助を係数1で参照する。16Combine・8Pickupを保持する。全28状態を支持ばね別・節点別・部材別の作用ベクトルで検査してから公開する。

| P7計算書の物理頁 | 採用値・JSONとの関係 | 確認方法 |
|---|---|---|
| 1–2 | 6節点・5部材、支持点4。梁材料/柱材料を断面1/2へ分離。A=12.15、Iz=7.38113。長期Ks/Kv/Kr=4262769/12788244/52218663、短期=8525475/25576488/104437326 | 正規frameと独立fixture、MCP入力帳票p1 |
| 3 | D1天端N=8299.52、M=-610、フーチングN=4167.4501953125、柱q=297.68。ty=-N、rz=-M、各柱部材へgy=-q | native直接値、各解析ケースの反力釣合い。重複自重を再控除・再加算しない |
| 4–5 | 列車L2最大M=298.40、安全性M=271.87。I1使用性N=128.50、I2使用性N=245.30、最大N=443.70 | 解決済み作用の直接転記、基本値×名目係数との違いを固定fixtureで検査 |
| 6 | 20基本荷重・Define。水平13～20だけ正負選択、14/18/20は長期ばね1 | canonicalとnative参照比較。Example保存JSONのばね2を流用しない |
| 7 | 20×16表は名目係数。実行用L/Iは補助Defineへ置換 | 全28状態335作用成分、独立加算で残差0 |
| 8 | 8抽出と所属Combine | 全抽出と選択元・同時成分を独立照合 |

正規結果のsource_page=9/10/11はExample計算書の頁であり、P7物理頁6/7/8と分けて付帯JSONへ記録した。現rendererは対応するH1形状を含め固定8頁で、表超過時はエラーになる。

分布荷重はFEMPython投影で `floor(P*100+0.5)/100` となる。独立レビューで将来q=297.681を見逃す問題を検出し、公開前のInputErrorに修正した。正負の2桁値と丸め境界を再確認し、指摘は解消した。

## structural-mcpでの実解析

通常の `all --output-dir tmp/p7-frameweb-implementation/candidate/output` により10成果物を生成した。native SHA-256は `1abaa2b50e94bbc5eb833db63b40f2cfc84e9ea2248f1e6ed2b9f06213dbb5d2`。

正式精度の候補を `fempython_calculate` へ渡したjobは `2026-10-16_81d609b4-a399-4a10-8641-7e5b34715da8`。executionStatus=success、engineeringStatus=not_checked。6節点・5部材、保存28ケース中27解析ケース・27Define・16Combine・8Pickup。省略は実荷重なしのWP3(case5)だけである。

取得したresult/PIK/PDF/変位CSV/反力CSVはbytesとSHA-256を検査して `mcp-native/` に保存した。独立照合は製品exporterを呼ばない `verify_analysis.py` で実施した。

| 独立確認 | 比較数 | 最大絶対残差 |
|---|---:|---:|
| 28状態の作用ベクトル | 335 | 0 |
| 全27ケースの反力Fx/Fy/Mz釣合い | 81 | 1.82e-12 |
| 支持点の変位=反力/ばね | 81 | 6.78e-21 |
| Define選択値 / 同時6成分 | 3564 / 21384 | 0 / 0 |
| Combine独立加算 | 12672 | 0 |
| Pickup選択値 / 同時6成分 | 1056 / 6336 | 0 / 0 |

Exampleの局所x正方向と部材別global gy負方向の同値性は先行再調査のMCP job `2026-10-16_12882773-8c86-469e-bec7-d0d3834ae4d7` で確認済み。詳細は `tmp/p7-frameweb-rereview/review-findings.json`。

MCP入力PDFは5頁。p1/3/5を描画確認した。骨組・材料・ばね・Define/Combine/Pickupを確認できるが、外部FEMPython帳票には長い名称と未丸め数値の列重なりがある。このPDFは検証用で、P7の納品計算書の代替にはしない。FEMPython本体は変更していない。

### ゼロ係数の実解析で見つかった境界

ρ=0はjob `2026-10-16_600213cb-6a7e-46e9-acdd-5d1dcda946d6` で21解析・8Pickupとなり、省略IDは予測どおり5/11/12/23/24/27/28だった。

一方、使用性係数=0は当初job `2026-10-16_14d6975d-3465-466d-87a5-671684e1a201` で `INVALID_DERIVED_REFERENCE: PICKUP 4 references an unavailable COMBINE` となった。組合せ7に実効作用がなく、FEMPythonが空の組合せ結果を作らないためである。作用ベクトルの一致だけでは検出できなかった外部ソフトの境界であり、不合格の証跡を保持する。

検証用コピーで解決済みゼロ補助への係数1参照を保持し、補助21だけに明示ゼロ節点荷重行を1件残した。job `2026-10-16_f7bed7db-a363-4281-b8c8-3e4892fba5fe` は24解析・16Combine・8Pickupで成功、省略は5/22/25/26。Combine7・Pickup4はそれぞれ全792応答成分が厳密に0だった。微小な架空荷重は使用していない。

製品へ同じ規約を反映し、66試験を通過。実装生成物を入力した最終job `2026-10-16_2dc453fc-7969-4d62-bccc-823efaca8f08` は上記検証用コピーのresult/PIK/両CSVとSHAがすべて一致した。さらに全28状態335作用成分、24解析の釣合い・ばね変位、全Define/Combine/Pickupと同時成分を独立照合した。作用・派生応答は残差0、釣合い最大残差1.82e-12。通常P7のWP3表現・native bytesは維持する。

最終レビューで、名目係数0の微小非ゼロ値を通常の作用比較許容差で受理する境界を補強した。基本resolvedとvariantの双方に厳密ゼロを要求し、各N=1e-11/1の4回帰をRed→Greenで確認した。独立レビューの残存指摘はなし。通常nativeと上記MCP解析入力の数値は変わらない。

## GUI読込・保存の精度境界

Computer Useのnative pipeが利用できず、画面の操作・形状の目視確認は未実施。代わりに既存Release GUI DLLをSTAから呼び、実際の `InputFileLoader.Open → InputDataService.JsonDataOpen → GetSaveJson → 再読込 → 再保存` を実行した。専用ハーネスと生成物は `gui-contract/`。

独立期待値は型付き項目だけ `Q(v)=DoubleParse(JsonSerialize(SingleParse(v)))` を適用した。node、section、ばね、節点荷重等の25値が変化し、参照と組合せ係数を保持した。既知のrow/layout/null追加・rate=1省略・文字列化を個別に正規化すると意味一致し、2回目の保存は同値だった。

GUI保存JSONのMCP jobは `2026-10-16_b2c5199c-8222-46af-a199-151ff737598d`、独立Q期待JSONは `2026-10-16_25cc22eb-7cc9-44da-8bc2-35ec0f7ea2d5`。両者のresult/PIK/変位CSV/反力CSVのSHAはすべて一致した。

元nativeとの最大差は、基本ケースの節点変位1.8841e-11 m、反力1.953125e-4 kN、柱断面力7.6661e-5 kN。元数値がGUI往復で不変とは扱わない。元nativeを直接headlessへ渡す経路が正式精度の確認対象である。

## 有限剛域の感度

検証用コピーの断面3についてA/Izだけを10倍・100倍とした。Eは一定で、軸・曲げ剛性をそれぞれ同じ倍率にした。採用nativeの剛域E=26500000、A=Iz=1000は変更していない。

| 比較 | case16柱頭dx (m) | 基準からの差 (mm) | D1下側剛部材の軸縮み (m) |
|---|---:|---:|---:|
| 採用値 | 0.0009709581999490732 | 0 | -7.503625250884e-7 |
| A/Iz×10 | 0.000967154923334081 | -0.00380328 | -7.503625250880e-8 |
| A/Iz×100 | 0.0009667745956725817 | -0.00418360 | -7.503625250880e-9 |

27基本解析ケース全体の反力最大差は1.71e-62以下、柱断面力差は2.60e-64以下。剛域の変形と柱頭変位には有限の影響がある。完全剛体との同値性や設計上の許容を認定する検証ではない。jobは×10 `2026-10-16_ee513095-cf33-482e-b46c-cc81db3ee1af`、×100 `2026-10-16_879df8e6-5175-49b6-a00f-8634a741c5df`。詳細は `comparison-summary.json`。

## ソフト版・試験・納品記録

FEMPythonソースHEAD=`7488c8fb4d6c100438a9691747ceb11fd9e66358`（確認時clean）、headless実体engineVersion=`1.0.0+018d0d0ee9453464b0b541a5344ce5a6c0acdfc6`、GUI DLL=`1.0.0+c9e7448bf592e27e0b8bd61fee948e93b30e3861`。ソースと実行バイナリの版を区別し、実体SHAを `fem-environment.json` へ記録した。

変換は不正コンテナをInputErrorへ正規化する5回帰を追加し、直角方向のstage共通化後も59試験すべて通過。再変換した0610 nativeのbytes/SHAは上記MCP候補と完全一致した。初期統合では公開/CLI35試験と既存CLI106試験、GUI連携73試験が通過。独立レビューは公開・変換関連88 passed/1 skipped（Windows symlink権限）および丸め修正再確認2 passed。これらは試験集合が重複するため合算しない。coverage/pytest-covは環境未導入で、カバレッジ率は未測定。

並行作業の直角方向側から共通公開処理・CLI/GUIへの拡張が入り、ユーザーは「両方進め、共通変更は維持して統合する」と回答した。初期受入時のall=10成果物は両方向統合後に12成果物となった。0610単独は引き続き4成果物、native名・精度・意味を保持する。新しい付帯JSONはschema2でpublication_id、全ジョブのartifact_manifest、expected_sidecarsを持つ。schema1は旧0610単独の照合用としてのみ残る。

共通公開処理の追加レビューでは、commit記録の書込失敗・rollback記録の書換失敗・旧ファイルの復元ロックが重なったとき、記録だけcommittedとなる不備を再現した。出力変更前の独立したpublication-pendingマーカーで修正し、新旧混在時には各出力親の次回書込みを拒否する。commit完了後のマーカー削除失敗では公開済みファイルを巻き戻さない。公開22試験・独立再確認7試験を通過。最新GUIのnon-Tk検証は89 passed/3 deselected、native構造拒否まで到達する試験補強1件も通過した。

最終統合候補の通常all実行は12成果物を生成し、実GUI完了検証関数で全SHA・共通publication_id・4PDF順序を確認した（`integrated/verification.json`）。0610 nativeはMCP検証済みbytesと一致した。

並行担当のnon-Tk全3144件では3139成功・旧`test_report_cli.py`の5件が失敗した。履歴fixtureのB6=1.75によるqH=2.625→2.63と、L2未設定による片側ゼロ候補を、新0620検査が拒否したためである。0500固有2試験はstageを明示し、全工程公開3試験のコピーだけB6=1.76・両側d1/d2のL2=0.5を明記した。元fixtureは保持し、A/Izは独立の固定値、その他の骨組期待値と全stage同値比較を維持した。調整後の同ファイル11件はすべて成功（`P7橋脚/.agents/logs/transverse-publication-report-cli-green-2.log`）。製品処理の緩和はなく、旧条件の拒否試験も別に保持する。

通常の `run_design.py --stage 0610 --overwrite` で本番4成果物を公開した。`delivery-receipt.json` のpublication_idは `ec960b036ca5455e8eeaa0560bff1a3a`、schema2、selected_stages=[0610]。native SHAは上記MCP入力と一致し、付帯JSON・生成元の全SHAも照合済み。`delivery-scope.json` では入力と他段階の成果物が不変。0610結果JSONも不変で、PDFは生成日時等によりSHAが変わったが、全8頁の文字と描画pixelsが以前の計算書と一致した。開始時152ファイルの監査でも元資料・入力の変更、ファイル欠損はない。

全体ゲート `tmp/quality-gates/pytest-20261016-203051-6855558.log` は35分30秒で完走し、**3379成功・5失敗・1スキップ**だった。失敗は収集時点の旧`test_report_cli.py`の5件だけで、上記の修正後11件成功により解消した。スキップは `test_all_derived_cells_are_bound_but_readonly_and_not_editable_fields[上部構造]` のTk初期化エラー `invalid command name "tcl_findLibrary"`。同じ項目の別プロセス実行ではsetup/call/teardown全て成功し、56件の製品・試験・環境ソースSHAがその検証用コピーと一致することを確認した。

`summarize_final_tests.py` で全3385収集IDと全体ログを完全照合し、修正後11件と上記GUI1件を対応させた。**全3385項目に成功証跡があり、未実行・未解消の項目はない**。証跡は `final-test-outcomes.json`。これは複数実行の照合結果であり、単一の全体コマンドが成功したとは扱わない。`git diff --check` も通過した。

先行3回の途中終了は完了証拠に含めない。初回は改行バッファを停止と誤認して終了、2回目は共有コード更新後の重複GUI試験を避けるため終了、並行側の共有実行も途中終了だった。最終全体実行の前半には並行側の分離Tk試験と一部重なりがあったため停止を依頼し、以後は1本にした。最終実行にフォーカス依存のassertion失敗はなかった。

並行側の通常0620本番生成後にも0610納品物を再検証し、native・付帯JSON・計算結果のSHA不変を確認した。入力とExample原本も開始時SHAを維持する。両方向の共通変更を保持したまま、外部FEMPythonの実画面操作を除く実装・検証・納品を終了した。
