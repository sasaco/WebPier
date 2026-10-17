Attribute VB_Name = "上部工反力"
Public 桁受け(1 To 4)     As Single '桁受け　　{重量, 偏心量(線路方向), 偏心量(線路直角方向),重心高さ}
Public はり(1 To 4)       As Single 'はり　　　{重量, 偏心量(線路方向), 偏心量(線路直角方向),重心高さ}
Public 柱(1 To 4)         As Single '柱　　　　{重量, 偏心量(線路方向), 偏心量(線路直角方向),重心高さ}
Public フーチング(1 To 4) As Single 'フーチング{重量, 偏心量(線路方向), 偏心量(線路直角方向),重心高さ}
Public 上載土(1 To 3)     As Single '上載土　　{重量, 偏心量(線路方向), 偏心量(線路直角方向)}
Public 高水位(1 To 3)     As Single '高水位　　{重量, 偏心量(線路方向), 偏心量(線路直角方向)}
Public 平水位(1 To 3)     As Single '平水位　　{重量, 偏心量(線路方向), 偏心量(線路直角方向)}
Public 低水位(1 To 3)     As Single '低水位　　{重量, 偏心量(線路方向), 偏心量(線路直角方向)}

Public 列車荷重 As 荷重項目
Public 地震列車 As 設計反力
Public 衝撃荷重 As 荷重項目

Public 複線分担率(1 To 10) As 設計反力
Public 線路荷重強度(1 To 10) As 設計反力
Public 直角荷重強度(1 To 8) As 設計反力
Public 直角荷重位置(1 To 8) As 設計反力

Public Type 設計反力
    RB As Single
    RC As Single
End Type
Public Type 列車Type
    単線 As 設計反力
    複線 As 設計反力
End Type
Public Type 荷重項目
    安全性 As 列車Type
    使用性 As 列車Type
End Type



Public Sub 計算()

    Dim 反力Book As Workbook
    Set 反力Book = comon.OpenBook(計算印刷.tmpPath & 計算印刷.上部工反力BOOKNAME)
    
    Call Set死荷重反力(反力Book)
    Call Set橋脚自重(反力Book)
    Call Set列車荷重(反力Book)
    Call Set線路荷重(反力Book)
    Call Set直角荷重(反力Book)
    
    '計算結果を取得
    Dim name As String
    Dim v As Variant
    v = Array("N", "xL", "xC", "hG")
    With 反力Book.Worksheets("橋脚自重")
        For i = 0 To 3
            name = "桁受け" & Trim(v(i))
            桁受け(i + 1) = .Range(name)
            name = "はり" & Trim(v(i))
            はり(i + 1) = .Range(name)
            name = "柱" & Trim(v(i))
            柱(i + 1) = .Range(name)
            name = "フーチング" & Trim(v(i))
            フーチング(i + 1) = .Range(name)
        Next i
        For i = 0 To 2
            name = "上載土" & Trim(v(i))
            上載土(i + 1) = .Range(name)
            name = "高水位" & Trim(v(i))
            高水位(i + 1) = .Range(name)
            name = "平水位" & Trim(v(i))
            平水位(i + 1) = .Range(name)
            name = "低水位" & Trim(v(i))
            低水位(i + 1) = .Range(name)
        Next i
    End With
    
    Dim inpData As Range
    With 反力Book.Worksheets("列車荷重")
        Set inpData = .Range("列車反力")
    
        列車荷重.安全性.単線.RB = inpData.Cells(1, 1)
        列車荷重.安全性.単線.RC = inpData.Cells(1, 5)
        衝撃荷重.安全性.単線.RB = inpData.Cells(3, 1)
        衝撃荷重.安全性.単線.RC = inpData.Cells(3, 5)
    
        列車荷重.安全性.複線.RB = inpData.Cells(4, 1)
        列車荷重.安全性.複線.RC = inpData.Cells(4, 5)
        衝撃荷重.安全性.複線.RB = inpData.Cells(6, 1)
        衝撃荷重.安全性.複線.RC = inpData.Cells(6, 5)
    
        列車荷重.使用性.単線.RB = inpData.Cells(7, 1)
        列車荷重.使用性.単線.RC = inpData.Cells(7, 5)
        衝撃荷重.使用性.単線.RB = inpData.Cells(9, 1)
        衝撃荷重.使用性.単線.RC = inpData.Cells(9, 5)
    
        列車荷重.使用性.複線.RB = inpData.Cells(10, 1)
        列車荷重.使用性.複線.RC = inpData.Cells(10, 5)
        衝撃荷重.使用性.複線.RB = inpData.Cells(12, 1)
        衝撃荷重.使用性.複線.RC = inpData.Cells(12, 5)

        Set inpData = Nothing
    
        地震列車.RB = .Range("地震LB")
        地震列車.RC = .Range("地震LC")
    End With
    
    With 反力Book.Worksheets("線路荷重")
        Set inpData = .Range("線路荷重")
        For i = 1 To 10
            線路荷重強度(i).RB = inpData.Cells(i, 1)
            線路荷重強度(i).RC = inpData.Cells(i, 5)
        Next i
        Set inpData = Nothing
    End With
    
    With 反力Book.Worksheets("直角荷重")
        Set inpData = .Range("直角荷重")
        For i = 1 To 8
            直角荷重強度(i).RB = inpData.Cells(i, 1)
            直角荷重強度(i).RC = inpData.Cells(i, 9)
            直角荷重位置(i).RB = inpData.Cells(i, 5)
            直角荷重位置(i).RC = inpData.Cells(i, 13)
        Next i
        Set inpData = Nothing
    End With

    
    反力Book.Save
    反力Book.Close
    Set 反力Book = Nothing

End Sub

Private Sub Set線路荷重(反力Book As Workbook)

    Dim s1 As Variant
    Dim s2 As Variant
    Dim name As String
    
    Dim v1 As Variant
    Dim v2 As Variant
    v1 = Array("起点側", "終点側")
    v2 = Array("μ", "支承")

    With 反力Book.Worksheets("線路荷重")
        For Each s1 In v1
            For Each s2 In v2
                name = Trim(s1) & Trim(s2)
                .Range(name) = 上部構造Sheet.Range(name)
            Next
        Next
    End With
    
End Sub

Private Sub Set直角荷重(反力Book As Workbook)

    Dim r As Integer
    Dim c As Integer
    
    Dim s1 As Variant
    Dim s2 As Variant
    Dim name As String
    
    Dim v1 As Variant
    Dim v2 As Variant
    v1 = Array("起点側", "終点側")
    v2 = Array("R", "V")

    With 反力Book.Worksheets("直角荷重")
        For Each s1 In v1
            For Each s2 In v2
                name = Trim(s1) & Trim(s2)
                .Range(name) = 上部構造Sheet.Range(name)
            Next
        Next
        
        
        Dim outData As Range
        Dim inpData As Range
        
        For Each s1 In v1
            name = Trim(s1) & "hs"
            Set inpData = 上部構造Sheet.Range(name)
            Set outData = .Range(name)
            For c = 1 To 13 Step 3
                outData.Cells(1, c) = inpData.Cells(1, c)
            Next c
        Next
        
        Set inpData = 上部構造Sheet.Range("車両高")
        Set outData = .Range("車両高")
        For r = 1 To 3
            outData.Cells(r, 1) = inpData.Cells(r, 1)
        Next r
      
        Set outData = Nothing
        Set inpData = Nothing
        
    End With
    
    Call Application.Run("'0600_上部工反力.xls'!車両横荷重_Click")
End Sub

Private Sub Set列車荷重(反力Book As Workbook)

    Dim s1 As Variant
    Dim s2 As Variant
    Dim name As String
    
    Dim v1 As Variant
    Dim v2 As Variant
    Dim v3 As Variant
    v1 = Array("起点側", "終点側")
    v2 = Array("L1", "スパン", "L2", "i")
    v3 = Array("車両長", "軸距a1", "軸距a2", "軸重p", "軸重e", "編成数", "ρf使用", "ρf破壊", "ρf疲労")

    With 反力Book.Worksheets("列車荷重")
        For Each s1 In v1
            For Each s2 In v2
                name = Trim(s1) & Trim(s2)
                .Range(name) = 上部構造Sheet.Range(name)
            Next
        Next
        For Each s1 In v3
            name = Trim(s1)
            .Range(name) = 上部構造Sheet.Range(name)
        Next
    End With
    
    Call Application.Run("'0600_上部工反力.xls'!test_Click")
    
End Sub




Private Sub Set橋脚自重(反力Book As Workbook)

    
    Dim i As Integer
    Dim name As String
   
    
    With 反力Book.Worksheets("橋脚自重")
        For i = 1 To 9
            name = "形状B" & Trim(Str(i))
            .Range(name) = 下部構造Sheet.Range(name)
        Next i
        For i = 1 To 9
            name = "形状W" & Trim(Str(i))
            .Range(name) = 下部構造Sheet.Range(name)
        Next i
        For i = 1 To 6
            name = "形状H" & Trim(Str(i))
            .Range(name) = 下部構造Sheet.Range(name)
        Next i
        For i = 1 To 2
            name = "形状df" & Trim(Str(i))
            .Range(name) = 下部構造Sheet.Range(name)
        Next i
        For i = 1 To 3
            name = "形状hw" & Trim(Str(i))
            .Range(name) = 下部構造Sheet.Range(name)
        Next i
        
        Dim outData As Range
        Dim inpData As Range
        
        Set inpData = 下部構造Sheet.Range("単位体積重量")
        Set outData = .Range("単位体積重量")
    
        outData.Cells(1, 1) = inpData.Cells(1, 1)
        outData.Cells(2, 1) = inpData.Cells(2, 1)
        outData.Cells(3, 1) = inpData.Cells(5, 1)
        outData.Cells(4, 1) = inpData.Cells(6, 1)
      
        Set outData = Nothing
        Set inpData = Nothing
       
    End With
    
    Call Application.Run("'0600_上部工反力.xls'!橋脚形状作成_Click")
End Sub

Private Sub Set死荷重反力(反力Book As Workbook)
    Dim i As Integer
    Dim j As Integer
    Dim a As Integer
    Dim r As Integer
    Dim c As Integer

    Dim name As String
    
    Dim outData As Range
    Dim inpData As Range
    
    With 反力Book.Worksheets("死荷重")
        'RA
        .Range("D1A") = 上部工反力Sheet.Range("D1A")
        .Range("D2A") = 上部工反力Sheet.Range("D2A")
        
        'RB
        For j = 1 To 2
            name = "D" & Trim(Str(j)) & "B"
            Set inpData = 上部工反力Sheet.Range(name)
            Set outData = .Range(name)
            a = 1
            c = 1
            For i = 1 To inpData.Columns.Count Step 4
                With outData.Areas(a)
                    .Cells(1, c) = inpData.Cells(1, i)
                    c = c + 3
                End With
                If c > 13 Then
                    a = a + 1
                    c = 1
                End If
            Next i
        Next j
        
        'RC
        For j = 1 To 2
            name = "D" & Trim(Str(j)) & "C"
            Set inpData = 上部工反力Sheet.Range(name)
            Set outData = .Range(name)
            a = 1
            c = 1
            For i = 1 To inpData.Columns.Count Step 4
                With outData.Areas(a)
                    .Cells(1, c) = inpData.Cells(1, i)
                    c = c + 3
                End With
                If c > 13 Then
                    a = a + 1
                    c = 1
                End If
            Next i
        Next j
        
        'RD
        .Range("D1D") = 上部工反力Sheet.Range("D1D")
        .Range("D2D") = 上部工反力Sheet.Range("D2D")
        
        
        
        '列車分担率B
        Set inpData = 上部工反力Sheet.Range("列車分担率B")
        Set outData = .Range("列車分担率B")
        a = 1
        c = 1
        For j = 1 To inpData.Columns.Count Step 4
            r = 1
            For i = 1 To inpData.Rows.Count
                With outData.Areas(a)
                    .Cells(r, c) = inpData.Cells(i, j)
                    r = r + 1
                End With
                If i >= 2 Then Exit For 'まだ２線しか作ってない
            Next i
            c = c + 3
            If c > 13 Then
                a = a + 1
                c = 1
            End If
        Next j
        
        i = 1
        For a = 1 To 2
            For c = 1 To 13 Step 3
                複線分担率(i).RB = outData.Areas(a).Cells(3, c)
                i = i + 1
            Next c
        Next a
        
        
         '列車分担率C
        Set inpData = 上部工反力Sheet.Range("列車分担率C")
        Set outData = .Range("列車分担率C")
        a = 1
        c = 1
        For j = 1 To inpData.Columns.Count Step 4
            r = 1
            For i = 1 To inpData.Rows.Count
                With outData.Areas(a)
                    .Cells(r, c) = inpData.Cells(i, j)
                    r = r + 1
                End With
                If i >= 2 Then Exit For 'まだ２線しか作ってない
            Next i
            c = c + 3
            If c > 13 Then
                a = a + 1
                c = 1
            End If
        Next j
        
        i = 1
        For a = 1 To 2
            For c = 1 To 13 Step 3
                複線分担率(i).RC = outData.Areas(a).Cells(3, c)
                i = i + 1
            Next c
        Next a
       
        Set outData = Nothing
        Set inpData = Nothing
       
    End With
End Sub
