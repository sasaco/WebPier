# 柱の断面照査の結果は Capacita のページを差し込み、判定は記録しない

0611 の計算書の柱の断面照査（8.5〜8.9）では、WebPier は見出しと解説（照査式・記号・フローチャート）だけを描く。断面力の総括と照査結果の表は、Capacita（RcDan）の `report.pdf` のページを、Capacita が返す節ごとのページ範囲で切り分けて差し込む。`.pik` から `pickup_data` への変換も Capacita の Headless に足し、WebPier は `.pik` を読まない。RC 断面照査の式・印字桁・表の項目、FEMPython のピックアップの読み方（軸力の符号、上側・下側）を WebPier が二重に持たないためで、ADR-0005（荷重図）・ADR-0006（責務の分担）と同じ形にした。WebPier が `result.json` を読んで表を組む案は、見本の体裁に寄せられるが照査の表の中身を WebPier が持つことになるので採らなかった。

## Consequences

- Capacita の `result.json` には照査値も OK/NG もなく、Capacita も直さないので、WebPier は照査を実行したこと（`engineeringStatus: not_evaluated`）だけを記録する。判定は計算書のページで人が確かめ、NG でも生成は止まらない。判定を機械で扱うには Capacita に結果を返させる変更が要る。
- WebPier の解説には、WDJ に書く値（γi・γb・kr・k4）だけを同じ定数から印刷する。Capacita の中にだけある RC標準の制限値の表は印刷しないので、解説と結果ページの値が食い違うことはないが、制限値は結果ページでしか読めない。
- 差し込むページの中身・決定性は Capacita の責務で、0611 の計算書は毎回同じバイトになるとは限らない。
- 細目は `.claude/docs/plans/refactoring-decisions.md` の決定48。
