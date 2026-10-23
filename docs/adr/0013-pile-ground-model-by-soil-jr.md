# 杭基礎の地盤のモデル化は SOIL-JR に任せ、WebPier は入力（.sdt）を書くだけにする

杭基礎の 0500（地盤のモデル化）では、杭の地盤反力係数・地盤ばね・支持力・設計限界値を WebPier で計算しない。SOIL-JR（JRSNAP 5.2-L03 の地盤反力特性算定プログラム、基礎標準 H24）に計算させる。WebPier は入力から SOIL-JR の入力 .sdt を書き、JRSNAPHeadless の runner の命令で SOIL-JR を動かす。返った帳票の PDF はバイト列のまま `output/0500_杭基礎.pdf` にし、基礎照査連携データ .sdr と解析連携データ .sdc は post/ に出す。元Excel `0510_杭基礎.xls` は同じ計算を表計算で持っていたが、ここでは再実装しない。後で使う値がどれも SOIL-JR の出力を前提にしているからである。0612・0622 の基礎の照査の設計限界値も、0711・0721 で Aggre-SE が取り込む杭基礎の制限値も .sdr から来る。JRSNAP の杭のモデルの地盤ばねは .sdc から来る。WebPier が自前で計算すると、同じ値を二通りに持つことになり、SOIL-JR と食い違う（ADR-0006・0007・0009 と同じ分担）。直接基礎の 0500 は、いまのまま WebPier が計算する（owner 2026-10-23）。

## Considered Options

- **元Excel 0510 のように WebPier が地盤ばねと支持力を計算し、帳票も描く。** 見本どおりの体裁と印字桁の伝播（ADR-0003）を保てる。しかし .sdr・.sdc を書くために SOIL-JR の計算を再現することになり、基準の改訂も SOIL-JR と WebPier の二か所で追うことになる。
- **SOIL-JR 5.3-L01体験版2 を使う。** 新しい基礎標準の下書き（「令和〇年〇月」準拠）に合わせた版で、既定値が違う（先端支持力に関する地盤修正係数など）。JRSNAP 5.2-L03 と、見本の Example橋脚4（H24 の係数と限界値の名前）とも基準がずれる。
- **画面の自動操作（スキル structural-jrsnap-soil の `run-analysis.ps1`）で動かす。** キー操作なので、実行中は PC に触れない。帳票の PDF も出ない。

## Consequences

- 杭基礎の 0500 には節の番号も WebPier の見出しもなく、SOIL-JR の書式で印刷される。WebPier が地盤の層を切り分けて求めた値（杭頭より上の地盤の γ・γ'）は、帳票の入力一覧に結果だけが出る。
- SOIL-JR は、画面が求めて保存した値を読込で計算し直さない（A・I、Ed、杭の配置の行と K_FLG、地盤抵抗係数）。そのため WebPier の書出しは、これらを SOIL-JR と同じ規則で書く。
- 帳票と .sdr・.sdc の中身・決定性は SOIL-JR の責務とする（5.3 では、同じ .sdt から同じバイトの .sdr になった）。WebPier は付帯JSONに runner と SOIL-JR の版を記録するだけで、`dependency_hashes` には結び付けない。
- runner のやり取りを変えたら、WebPier の代役 runner も合わせて更新する（ADR-0005・0007）。
- 細目は `.claude/docs/plans/refactoring-decisions.md` の決定80 と `.claude/docs/plans/pile-foundation-plan.md`。
