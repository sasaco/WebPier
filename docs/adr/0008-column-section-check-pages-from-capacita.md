# 柱の断面照査の結果は Capacita のページを差し込み、判定は記録しない

0611・0621 の計算書の柱の断面照査（8.5〜8.9・9.5〜9.9）では、WebPier は見出しと解説（照査式・記号・フローチャート）だけを描く。断面力の総括と照査結果の表は、Capacita（RcDan）の `report.pdf` のページを、Capacita が返す節ごとのページ範囲で切り分けて差し込む。`.pik` から `pickup_data` への変換も Capacita の Headless に足し、WebPier は `.pik` の断面力を読まない（柱下端の着目点が何番目かだけを着目点の並びから求める。0621 の骨組では柱の途中に着目点が入るため。決定48）。RC 断面照査の式・印字桁・表の項目、FEMPython のピックアップの読み方（軸力の符号、上側・下側）を WebPier が二重に持たないためで、ADR-0005（荷重図）・ADR-0006（責務の分担）と同じ形にした。WebPier が `result.json` を読んで表を組む案は、見本の体裁に寄せられるが照査の表の中身を WebPier が持つことになるので採らなかった。

## Consequences

- Capacita の `result.json` には照査値も OK/NG もなく、Capacita も直さないので、WebPier は照査を実行したこと（`engineeringStatus: not_evaluated`）だけを記録する。判定は計算書のページで人が確かめ、NG でも生成は止まらない。判定を機械で扱うには Capacita に結果を返させる変更が要る。
- WebPier の解説には、WDJ に書く値（γi・γb・kr・k4）だけを同じ定数から印刷する。Capacita の中にだけある RC標準の制限値の表は印刷しないので、解説と結果ページの値が食い違うことはないが、制限値は結果ページでしか読めない。
- 差し込むページの中身・決定性は Capacita の責務で、0611・0621 の計算書は毎回同じバイトになるとは限らない。
- Capacita は断面力0の照査を RC標準の規則で飛ばし、その節を返さない（理由は info のメッセージ）。WebPier はその節の見出しと解説に省略の理由を付けて印刷するので、どの照査を省いたかは計算書と結果JSONでわかる。省略を判断するのは Capacita で、WebPier は断面力を見ない。
- 細目は `.claude/docs/plans/refactoring-decisions.md` の決定48。
