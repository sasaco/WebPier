# 静的非線形解析は JRSNAP の Headless runner に任せ、WebPier は JRSNAP を直接起動しない

これまで WebPier の範囲は、JRSNAP の入力（`post/線路方向.ndu`・`post/線路直角方向.ndu`）を作るところまでだった。静的非線形解析も生成の中で行うことにした。ただし WebPier の中から JRSNAP_Input.exe や S_ANALYSIS.exe を起動するのではなく、structural-mcp の新しいサブモジュールに JRSNAP の Headless runner（FrameWebforCS.Headless と同じ protocol v1）を作り、WebPier はそれを呼ぶだけにする。JRSNAP は x86 の .NET Framework の第三者製品で、画面のない入口を持たない。そのため、「解析用データ出力」を画面なしで呼ぶ処理、共用の作業ファイル（`work.wk3`・`renzoku.flg`）の扱い、確認画面の自動操作は、どこかに作る必要がある。それを WebPier の pipeline に入れるのではなく、JRSNAP の結果を使う他の利用者（structural-mcp、Aggre-SE）と共有できる一か所に集めるためである。

## Considered Options

- WebPier の pipeline に C# の補助を置き、その場でコンパイルする（`scripts/accept_jrsnap_ndu.py` と同じ方式）：作るものは少ないが、JRSNAP を動かす知識が WebPier と skill のスクリプトに分かれて重複する。
- Batch サブモジュール（Aggre-SE）に置く：JRSNAP の結果を集計する側と同じ場所にそろうが、解析の実行と集計は別の責務なので分けた。

## Consequences

- runner のやり取り（`run` の引数、envelope、出力の一覧）を変えたら、WebPier の代役 runner も合わせて更新する（ADR-0005 と同じ）。
- JRSNAP のインストール先と版は runner の設定ファイルが持つ。WebPier は runner の exe の場所（`STRUCTURAL_MCP_JRSNAP_RUNNER`）だけを知る。
- 解析結果の中身・決定性・確認画面の初期状態は JRSNAP の責務とし、WebPier は付帯JSONに版と押した状態を記録するだけで、`dependency_hashes` には結び付けない。
- 細目は `.claude/docs/plans/refactoring-decisions.md` の決定47。
