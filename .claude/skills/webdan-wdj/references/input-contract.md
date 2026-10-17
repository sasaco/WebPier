# WDJ input contract

この資料は WebDan 利用マニュアル、現在の Capacita/RcDan 入力クラス、既存 WDJ で確認した application-supported subset である。ベンダー形式全体の公式 JSON 仕様ではない。

Authoritative manual: <https://fresh-tachometer-148.notion.site/WebDan-5a22f8541cb14d27b56389fec84b580f>

## Evidence labels

- `observed`: マニュアル、現行パーサ、または実 WDJ で直接確認した。
- `inferred`: 複数の observed 事実から導いたが、公式 JSON 仕様としては未確認。
- `unknown`: 入力元だけでは確定できず、ユーザー確認またはエンジン検証が必要。

## Inputs needed to produce a calculation-ready WDJ

### 1. Document and mode

- 適用: 鉄道またはバングラディッシュ鉄道 (`observed`)
- 仕様: H16/R5 鉄道標準、運輸機構、JR東日本の該当仕様 (`observed`)
- 断面力の指定方法: 直接入力、2D pickup、3D pickup (`observed`)
- pickup の場合: 元ファイルと各照査の Pickup No (`observed`)

`pickup_filename` が空文字なら断面力モード、`.pik` 等なら 2D、`.csv` なら 3D と解釈される (`observed` from current Capacita source)。

### 2. Member and section

- 部材番号、グループ No、部材名 (`observed`)
- 断面形状 (`observed`)
- 断面寸法 B/H、形状によって Bt/t、部材数 (`observed`)

矩形は保存値 `shape: 1`。寸法単位は mm。`members.B/H` は計算値であり、対応する `bar.b/h` と fatigue 行の `b/h` は表示用重複値として同期する (`observed`/`inferred`)。

### 3. Design point and checks

- 算出点番号、対象部材、算出点名 (`observed`)
- 上側引張・下側引張の実施 (`observed`)
- 計算対象軸 My-Vz または Mz-Vy (`observed`)
- 曲げ、せん断、ねじりの実施 (`observed`)

手入力モードでは `force[index]` が算出点に対応する。曲げモーメントは正が下側引張、負が上側引張。軸力は正が圧縮、負が引張 (`observed`)。

### 4. Longitudinal and shear reinforcement

各引張側について次を決める。

- 鉄筋径と本数 (`observed`; 矩形の最小本数は 2)
- 1段目芯かぶり (`observed`)
- 複数段の場合: 1段目本数、段間隔 (`observed`)
- 隣接鉄筋間隔 (`observed`; 曲げひび割れ幅に影響)
- 必要な場合: 主鉄筋斜率 (`observed`)

せん断・ねじりを行う場合は、スターラップと折曲げ鉄筋の径・本数・間隔・角度、およびせん断スパン等も必要 (`observed`)。

日本基準の対応径は D10, D13, D16, D19, D22, D25, D29, D32, D35, D38, D41, D51。D19 の公称断面積は 286.5 mm² (`observed`)。

### 5. Materials and factors

- 軸方向鉄筋、側方鉄筋、スターラップの材種。標準選択肢は SD295/345/390/490 (`observed`)
- D25以下と D29以上の材料行 (`observed`)
- コンクリート設計基準強度 Fc、最大骨材寸法 (`observed`)
- 軸力を考慮するか、および関連オプション (`observed`)
- 既定値から変える場合は安全係数、杭施工条件、ひび割れ・疲労条件 (`observed`)

`SD345` は現行入力で `id: 2, fsy: 345, fsu: 490` (`observed`)。

### 6. Design forces and outputs

- 実行する照査項目ごとの Md/Nd、Vd/Md/Nd、Mt/Md/Vd/Nd (`observed`)
- 曲げ・せん断・ねじりの計算選択 (`observed`)
- 対象部材グループと必要な帳票 (`observed`)

引張側に軸方向鉄筋が無い曲げ照査、対象断面力が 0 の照査、スターラップが無い疲労せん断照査などは省略またはエラーになり得る (`observed`)。

## Current fastening-device example

2026-09-30 に内容を確認した WDJ は、当初指定された
`02_pre/11_締結装置の照査/WebDan (1).wdj` と同じ内容である。作業中に配置が変わり、
直近の確認時点では `02_pre/11_締結装置の照査/111_rcdan.wdj` に置かれている
(`observed`)。作業ツリーが並行変更され得るため、実行直前に列挙して現在位置を確認する。

- H16 鉄道標準、断面力モード、矩形部材「締結装置」
- 現在の断面は 340 x 340 mm。依頼の 350 x 350 mm と不一致
- 算出点「アンカーボルト」、Mz-Vy、上下引張、曲げのみ
- 上側・下側とも D19-2本、芯かぶり 60 mm、隣接間隔 220 mm
- 軸方向鉄筋 SD345、コンクリート Fc24、最大骨材 25 mm
- Md0/Md1 = 13.2 kN·m、Nd0/Nd1 = 101.8 kN

依頼文「断面350x350, 鉄筋D19-2本(SD345)」から未確定な点:

- D19-2本を上側・下側の両方に置くか
- 芯かぶり 60 mm と既存断面力・材料・基準を継承するか
- 350 mm 幅で隣接間隔を 220 mm のまま保持するか、左右対称 1 段として 230 mm にするか

これらは自動補完しない。既存 WDJ を base とする場合も、どの値を継承したかを報告する。

## Validation gates

1. UTF-8 JSON として読める。
2. root に `ver`, `basic`, `members`, `points`, `bar`, `safety`, `force`, `calc` がある。
3. 適用・仕様の `selected` が各 1 件。
4. 対象 `m_no` と `index` が一意で、参照先が存在する。
5. 断面、配筋、材料、断面力、計算選択に矛盾がない。
6. `validation.requestComparison` が request の全 leaf を列挙し、全件 `matched` である。
7. サマリーにコンクリート、非 null 断面力、計算・帳票選択、requested/inherited の区別が出る。
8. Capacita が ready なら `webdan_calculate` で engine validation を通す。

Capacita unavailable の場合、1～7 は実施できるが 8 は未実施として扱う。readiness は保存した時点情報で判断せず、実行ごとに最新の `get_capabilities` を使う。
