# ソースは層別のパッケージにし、段階は登録表に集める

旧 `src/` を、パッケージ `webpier/` の下の `core`・`inputs`・`calc`・`reporting`・`export`・`pipeline`・`gui` の層別パッケージに分け、依存の向き（core ← inputs ← calc ← reporting/export ← pipeline ← gui）を境界テストで強制する。段階（0500〜0720）の依存関係・計算・帳票・成果物・外部出力は `pipeline` の登録表（StageSpec）1か所に定義し、段階ごとの分岐を他の場所に書かない。段階別のパッケージ（`stage_0600/` など）は、骨組・ばね・移動荷重のように段階をまたぐ部品の置き場が曖昧になり、計算が帳票に依存しないことを構造で強制できないため採らなかった。
