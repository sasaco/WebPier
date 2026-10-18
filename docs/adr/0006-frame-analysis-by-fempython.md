# 骨組解析は FEMPython に任せ、WebPier は結果を解釈しない

これまで構造解析は対象外で、FrameWeb 入力（`post/線路方向.json` など）を作るところまでが WebPier の範囲だった。骨組解析にも着手するにあたり、解析は WebPier の中には実装しない。生成した FrameWeb 入力をそのまま FEMPython の Headless runner に渡して計算させ、ピックアップ断面力とピックアップ変位量のファイルを、返ったままの形で `post/` に公開する。WebPier は解析の値を読み直さない。照合・丸め・計算書への印刷もしない。部材の断面照査と寸法・配筋の最適化は、引き続き対象外とする。解析と作図の責務を FEMPython の一か所に集め、WebPier が持つ解析エンジンを二重にしないためである（ADR-0005 の荷重図と同じ扱い）。

## Consequences

- 解析結果の中身、形式、決定性は FEMPython の責務とする。WebPier は付帯JSONに `engineVersion` を記録するだけで、結果のバイトを実装の同一性（`dependency_hashes`）には結び付けない。Headless は結果を `engineeringStatus: "not_checked"` として返す。その結果を設計照査の済んだ値として扱わない。
- 荷重図だけを描く通常の生成（決定44）には、構造解析を持ち込まない。骨組解析は、利用者が選んだときだけ行う。
