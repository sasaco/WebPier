# 受入の補助（スキルではない）

このフォルダーの `scripts/save-ndu.ps1`・`roundtrip.cs`・`check-ndu-header.ps1` は、`scripts/accept_jrsnap_ndu.py` の `HELPER` が使い、`tests/fixtures/acceptance/jrsnap_v52/record.json` が SHA を記録し、`.gitattributes` が LF に固定している受入の補助です。パスと中身を変えると受入のやり直しが要るので、動かしません。

使い方と JRSNAP の知識の正は、structural-mcp のグローバルのスキル `structural-jrsnap-input`（同じスクリプトの複製を持つ）です。WebPier が JRSNAP を使う実装はスキル `webpier-jrsnap`。
