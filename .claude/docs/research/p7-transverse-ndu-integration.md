# P7線路直角方向NDU：CLI・GUI・公開連携

作成日: 2026-10-17。担当: pdf-inputs。実装先は `C:/Users/sasai/AppData/Local/Temp/p7-transverse-ndu-20261017`。以前の受入ソース `p7-ndu-final-review-20261017` は変更しない。以下の行番号は調査開始時の新隔離版に対応する。

## 現状と確定した出力範囲

`pier_design/cli.py:218` の `_calculate_stages` は0720のために0500・0600・0620を内部計算するが、公開対象は指定stageだけである。`frameweb_artifacts.py:33` のFrameWeb対象は0610と0620であり、0720にFrameWeb出力はない。既存0720はPDF/JSONの2件である。rootはこの契約を維持し、初回も0720の4件のみを正式公開する方針を確定した。直角方向FrameWebと線路方向の既存成果物には触れない。

| 指定 | JRSNAPなし | JRSNAPあり | NDU対象 |
|---|---:|---:|---|
| 0710 | 2 | 4 | 線路方向 |
| 0720 | 2 | 4 | 線路直角方向 |
| all | 16 | 20 | 両方向 |
| 0500/0600/0610/0620 | 従来どおり | 入力読取り前にエラー | なし |

`--post-dir` と一括公開・退避・復元は既存処理を利用する。両方向を出すallで片方が不正なら全候補を公開しない。初回4件と通常all20件は別の成果物集合として検証する。

## 合意中のAPI契約

core担当は `build_transverse_ndu_model(raw, foundation, seismic, input_sha256=sha)` を既存線路方向と同形で実装する。metadataの既存キーを維持し、直角方向には `direction="transverse"` を加える。`jrsnap_design_conditions.TRANSVERSE_PROFILE_ID = "p7-transverse-v52-v1"` を公開し、`get_profile(raw, direction="longitudinal")` と地盤導出APIは既定の旧動作を保持する。

| 境界 | 契約 |
|---|---|
| `GenerationOptions` | 既存の引数と既定値を維持。stageは0710/0720/allでJRSNAPを許可 |
| `candidate.ndu_models` | stageキー0710/0720 → core modelのread-only map。内側のモデル変更はhashで拒否 |
| `candidate.ndu_paths` | stageキー → 最終NDUパスのread-only map |
| `candidate.metadata_by_stage` | stageキー → metadataのdeepcopy。呼出元の変更を候補へ反映しない |
| `ndu_model / ndu_path / metadata` | 互換用の選択alias。0710/allは0710、0720単独は0720、JRSNAPなしは従来の空値 |
| `canonical_snapshot_sha256` | 単独は0500＋対象stage、allは0500/0710/0720。全選択モデルと全対象snapshotを保持・検証 |
| `jrsnap_paths` / provenance builder / validator | `stage="0710"` のkeyword引数を追加。旧callは線路方向のまま |

受入担当はstage mapを使って方向を明示する。allの正式受入を行う場合は、同一raw SHAに対応する独立oracleで両NDUを照合し、全対象のアプリ往復が終わってから同じ候補を一回公開する。旧入力SHAに固定された0710 oracle/receiptを新入力のallへ流用しない。通常CLIのall生成にはアプリ受入を必須化しない。

## CLI・sidecarの変更境界

- `cli.py:288` の `prepare_generation` で対象NDU stageを決める。rawを一度読み、現在と同じ `_calculate_stages` で得た0500と0710/0720をそれぞれcoreへ渡す。直角方向のために0710を追加計算しない。
- 生成済みnative bytesを方向別にstagingへ置く。現在の `declared` と `sidecars` へ `0710.jrsnap` / `0720.jrsnap` および対応sidecar roleを登録する。全候補は同じpublication IDと同じtransactionで公開する。
- `jrsnap_artifacts.py:25` のpath選択を方向別specへ拡張する。新規名は `線路直角方向.ndu` と `線路直角方向.ndu.provenance.json`。既存FrameWebの `線路直角方向.json` / `.provenance.json` と衝突しない。
- `jrsnap_artifacts.py:76` のschema 1は維持し、stage・direction・convention/profile・snapshot keyと成果物3件を方向ごとに選択する。0720は `p7-transverse-jrsnap-v1` と0500/0720を使用する。0710の既存callとschemaは保つ。
- 両方向のvalidatorを個別に実行し、stage/profile/input/計算hash/manifest/native/公開IDの取り違えを拒否する。allでは既存FrameWeb世代照合を保持する。FrameWeb schema 2へNDUを混ぜない。
- `GenerationCandidate` の候補集合・モデル・source・input・目的地・退避ファイル・最終hash検証を両方向の全候補へ適用する。片方向だけの検査へ縮小しない。既存のone-shot publicationとrollback処理は変更しない。

## GUI・入力欄

GUIは `editor_calculation.py:181` と `editor_gui.py:720` でall固定である。rootはstage選択UIを新設しない最小拡張を確定した。既存のdefault-off checkboxを選ぶと両方向NDUを出す。通常allの16件は不変、有効時は20件を検証・監視する。成功表示は既存どおり6帳票で、NDUの両方向出力を明記する。

`editor_gui.py:515` の線路方向4行表に加えて直角方向4行表を置く。`jrsnap_transverse` のキーは `shear_factor_vcd`、`shear_factor_vsd`、`shear_factor_vdd`、`aggregate_max_mm`。ラベル・単位・範囲は線路方向と同じ。`editor_model.py:47,72,228` のoptional path・保存・範囲検証を2 namespaceへ適用する。未設定は空欄のままで、表示時にも未編集の保存時にも値を補完しない。長方向設定を恒久aliasにしない。今回の4初期値2.0/1.3/1.8/25はrootだけが原入力へ追加する。

両表の編集中の値を保存前にflushし、実行中の編集・貼付け・削除・undo/redoを両表とも無効にする。成果物公開失敗で保存済み入力を巻き戻さない。

## 検証計画

- 既存0710の選択alias、単独4件、独立期待値、native bytesを維持する。
- 0720単独4件、all20件、source/input一致、0500一回計算と両方向が同一in-memory結果を利用することを確認する。
- 0720-onlyで長方向NDU/FrameWebを変更しない。JRSNAPなしでどちらのNDUも触れない。不正stageは入力読取り前に拒否する。
- 両方向model/snapshot変更、どちらかの候補削除・追加・改変、sidecar取り違え、異世代、目的地競合、途中失敗時の全復元を検証する。
- 旧入力の空欄、方向独立の編集/save/reload、入力範囲、両表のbusy制御、両方向20件の検証と後続変更監視を確認する。Tkはfresh processでrootと排他調整する。
- 実raw→実calculator→core→serializerの期待値照合は独立受入担当と分担する。新しい全体4000件suiteや正式アプリ公開を独断で開始しない。

## 共有への最小統合

調査開始時の11所有ファイルを `tmp/p7-transverse-ndu/integration/isolated-baseline/` と `shared-baseline/` に保存し、SHA一覧 `baseline-hashes.json` と差分 `shared-vs-isolated-start.patch` を記録した。開始時点で共有と隔離が異なる所有ファイルはcli.py、jrsnap_artifacts.py、README.mdの3個である。

共有のcli.pyは描画依存のhash、全計算snapshot、default経路の競合検出を追加している。jrsnap_artifacts.pyは `reporting.runtime.dependency_hashes` へ委譲している。これらを隔離版全体のコピーで戻してはならない。方向追加の差分だけを3-way比較して適用し、共有の `_rendering_identity`、`_computed_sha256`、renderer error変換、source/dependency/backup guardを維持する。READMEも追加された帳票移行説明を保持する。開始時に一致したeditor/testファイルも統合直前にhashを再確認し、並行変更があれば同様にhunk単位で統合する。

本資料の段階では製品編集は未開始。方向固有の解析制御値はcore担当の根拠確認とrootのGOに従う。
