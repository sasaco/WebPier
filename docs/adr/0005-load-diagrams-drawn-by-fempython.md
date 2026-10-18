# 荷重図は FEMPython に描かせ、計算書へページごと差し込む

0610・0620 の荷重図（8.3・9.3）は WebPier では描かない。同じ生成で公開する FrameWeb 入力（`post/線路方向.json`・`post/線路直角方向.json`）をそのまま FEMPython の Headless runner（`load_diagram`、FEM の計算はしない）に渡し、返った PDF のページを、GridLayoutPdf で描いた計算書の前半と後半の間に pypdf で差し込む。計算書にはページ番号を印刷しない（体裁の見本どおり）。計算書の荷重図を FrameWeb に渡した荷重そのものの図にするためで、WebPier 内で描いていた 0620 の荷重図（見本どおり複数ケースを1図にまとめ値を右に並べる体裁）は廃止した。runner の場所は `.env` の `STRUCTURAL_MCP_FEMPYTHON_RUNNER` で受け取り、なければ 0610・0620 の生成は止まる。

## Consequences

- FEMPython の出力（中身・ページ数・体裁・決定性）は FEMPython の責務とし、WebPier はどんな状態でも受け入れる。このため 0610・0620 の計算書は荷重図のページを含めると毎回同じバイトになるとは限らない。WebPier が描く部分は従来どおり決定的にする。
- FEMPython は保存形式を現行形式（y 下向き）として描くので、WebPier の FrameWeb 出力は節点の y と、節点荷重の ty・rz、部材荷重の gy の符号を反転して書く（橋脚を上下に鏡に映した同等のモデル）。`ver` は書かないので、FrameWebforJS（ブラウザ版）で開くと上下逆になる。
- runner のバイナリは実装の同一性（`dependency_hashes`）に入れず、付帯JSONに `engineVersion` だけを記録する。開発ビルドが同じ版番号のまま変わっても検出しない。
- 通常のテストは Headless のやり取りをまねる代役の runner を使い、本物は `.env` があるときだけ1件で確かめる。FEMPython のやり取りが変わったら代役も更新する。
- 細目（体裁の指定、対象ケース、配置）は `.claude/docs/plans/refactoring-decisions.md` の決定44。
