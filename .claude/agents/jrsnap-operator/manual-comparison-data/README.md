# マニュアル比較データの説明

最終的な判断と主要な変更点は、親フォルダーの [比較レポート](../JRSNAP_5.2と5.3体験版2_マニュアル比較レポート.md) に記載した。

- `summary.json`：各組のPDFページ数、原本のSHA-256、抽出本文の比較集計。
- `<マニュアル名>.json`：原本のメタデータ、全ページの抽出本文、推定したページ対応、本文差分、描画差分の数値。
- `<マニュアル名>.diff.txt`：上記のページ対応に沿った、空行・フッター除去後の本文のunified diff。本文は正規化一致を判定した後、元の文字列で差分表示するため、改行・空白の差も表示される。
- `Soil-JR.ocr.json`：5.2 PDF 27–90、5.3 PDF 29–110の計146ページの日本語OCR。Windows内蔵のローカルOCRを使用。誤認識・読取り順序の乱れを含むため、数値・式・用語の確定にはPDF原本を参照する。
- `*_compare_旧ページ_新ページ.png`：選択した原本ページを左に5.2、右に5.3として描画した比較画像。
- `*_52_p*.png`、`*_53_p*.png`：個別の原本ページ描画。

## 集計値の注意

`equal_normalized_pages` は抽出テキストをNFKC正規化し、空白と版表示・ページフッターを除いた後の一致数である。画像だけの出力例は、画像が違っても一致に数えられる。

`alignment`、`inserted_pages`、`deleted_pages` は本文に基づく機械的な対応結果である。特に画像中心のSoil-JR出力例では、抽出本文が空白・見出しだけのページが多く、対応の確度が低い。これらを実際の内容の追加・削除件数として使用しない。レポートの帳票比較は、OCRとページ画像で内容を確認して対応付け直している。

`visual_changes` は60 dpiのグレースケール画像比較であり、下端45 ptを除く。`mae` は輝度差の平均、`changed_pixel_fraction` は輝度差が20/255以上の画素の割合である。余白・配置・描画方法、フッターの一部の差も検出する。値が大きいことは機能変更が大きいことを意味しない。`visual_diff_pages` も機能変更のページ数ではない。

PDFページ番号は1始まり。`printed_page` は下端から読み取った章別ページで、取得できない場合は空文字。原本の章別ページ表記はPDF内の目次等で確認できる。

## OCRの再現

WebPier のルートから次を実行する。Windowsに日本語OCR言語が必要。

```powershell
$env:PYTHONUTF8 = '1'
uv run --with pymupdf --with pillow python .claude/agents/jrsnap-operator/scripts/compare_manuals.py --render 52 Soil-JR 27-90 --dpi 160 --output tmp/pdfs/jrsnap-manual-ocr
uv run --with pymupdf --with pillow python .claude/agents/jrsnap-operator/scripts/compare_manuals.py --render 53 Soil-JR 29-110 --dpi 160 --output tmp/pdfs/jrsnap-manual-ocr
.claude/agents/jrsnap-operator/scripts/ocr_manual_pages.ps1 -ImageDir tmp/pdfs/jrsnap-manual-ocr -Output .claude/agents/jrsnap-operator/manual-comparison-data/Soil-JR.ocr.json
```

描画はPyMuPDFを使用した。Pythonは `uv run --with pymupdf --with pillow` で利用でき、Python本体やPopplerがPATHにない環境でも実行できる。
