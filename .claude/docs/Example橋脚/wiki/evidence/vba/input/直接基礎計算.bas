Attribute VB_Name = "直接基礎計算"
Public Kv(1 To 2) As Single
Public Ks(1 To 2) As Single
Public Kr(1 To 2) As Single

Public Sub 計算()
Attribute 計算.VB_Description = "マクロ記録日 : 2017/6/6  ユーザー名 : sasaco"
Attribute 計算.VB_ProcData.VB_Invoke_Func = " \n14"

    Dim i As Integer
    Dim j As Integer
    Dim B As Single
    Dim L As Single
    With 下部構造Sheet
        B = 0
        B = B + .Range("形状B7")
        B = B + .Range("形状B8")
        B = B + .Range("形状B9")
        L = 0
        L = L + .Range("形状W7")
        L = L + .Range("形状W8")
        L = L + .Range("形状W9")
    End With
    
    Dim バネBook As Workbook
    Dim outData As Range
    Dim inpData As Range
    
    Set バネBook = comon.OpenBook(計算印刷.tmpPath & 計算印刷.直接基礎BOOKNAME)
    With バネBook
        With .Worksheets("支持層")
            '地盤情報をセット
            Set outData = .Range("地盤の一覧表")
            Set inpData = 地盤データSheet.Range("地盤の一覧表")
            For i = 1 To inpData.Rows.Count
                outData.Cells(i, 1) = inpData.Cells(i, 1) '層番
                outData.Cells(i, 4) = inpData.Cells(i, 4) '層厚
                outData.Cells(i, 8) = inpData.Cells(i, 8) '土質区分
                outData.Cells(i, 12) = inpData.Cells(i, 12) 'Ｎ値
                outData.Cells(i, 15) = inpData.Cells(i, 15) '湿潤重量
                outData.Cells(i, 19) = inpData.Cells(i, 19) '水中重量
                outData.Cells(i, 23) = inpData.Cells(i, 23) '内部摩擦角
                outData.Cells(i, 25) = inpData.Cells(i, 25) '内部摩擦角の上限値
                outData.Cells(i, 27) = inpData.Cells(i, 27) '一軸圧縮強度
                outData.Cells(i, 31) = inpData.Cells(i, 31) '変形係数
            Next i
            Set outData = Nothing
            Set inpData = Nothing
            '基礎幅をセット
            .Range("基礎幅B") = B
            .Range("基礎幅L") = L
            'バネ値を取得
            Kv(1) = .Range("Kv長期")
            Kv(2) = .Range("Kv短期")
            Ks(1) = .Range("Ks長期")
            Ks(2) = .Range("Ks短期")
            Kr(1) = .Range("Kr長期")
            Kr(2) = .Range("Kr短期")
        End With
        .Save
    End With
    バネBook.Close
    Set バネBook = Nothing
    
End Sub
