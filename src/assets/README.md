# 入力フォームの参照図

元の入力PDFの1ページ目から、寸法記号・支点・列車軸距の図だけを切り出したPNGです。入力値に応じて変形する設計図ではありません。通常表示用と、図を拡大して確認するための `_large.png` を対で保持しています。Tkinter標準の `PhotoImage` で読み込み、実行時にPDF画像変換ライブラリは不要です。

| ファイル | 元資料 | 切り出し範囲（PDFポイント、左・上・右・下） |
| --- | --- | --- |
| substructure | .claude/docs/Example橋脚/pre/input-下部構造.pdf | 70, 250, 655, 618 |
| skew | .claude/docs/Example橋脚/pre/input-下部構造.pdf | 732, 78, 1060, 258 |
| superstructure | .claude/docs/Example橋脚/pre/input-上部構造.pdf | 103, 149, 900, 315 |
| train | .claude/docs/Example橋脚/pre/input-上部構造.pdf | 304, 430, 728, 572 |
| reactions | .claude/docs/Example橋脚/pre/input-上部工反力.pdf | 94, 86, 680, 245 |

拡大用はPyMuPDFの `page.get_pixmap(matrix=Matrix(2, 2), clip=Rect(...), alpha=False)` で生成。通常用の目標幅は順に580、320、520、480、600ピクセル（クリップ端の丸めで1ピクセル大きくなる場合があります）。
