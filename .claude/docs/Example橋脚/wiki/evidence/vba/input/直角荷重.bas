Attribute VB_Name = "直角荷重"

Public Sub 計算()

    Dim 直角荷重Book As Workbook
    Set 直角荷重Book = comon.OpenBook(計算印刷.tmpPath & 計算印刷.直角荷重BOOKNAME)
    
    Call set骨組図(直角荷重Book)
    Call set荷重計算1(直角荷重Book)
    Call set荷重計算2(直角荷重Book)
    
    直角荷重Book.Save
    直角荷重Book.Close
    Set 直角荷重Book = Nothing
End Sub

Private Sub set荷重計算2(直角荷重Book As Workbook)
    Dim i As Integer
    Dim j As Integer
    Dim r As Integer
    Dim c As Integer
    Dim name As String
   
    
    With 直角荷重Book.Worksheets("荷重計算")

        .Range("フーチングN") = 上部工反力.フーチング(1)
        .Range("フーチングxC") = 上部工反力.フーチング(3)

        Dim outData As Range
        Dim inpData  As Range
        
        Set inpData = 上部工反力Sheet.Range("D1B")
        Set outData = .Range("D1B")

        r = 1
        For i = 1 To inpData.Columns.Count Step 4
            outData.Cells(r, 1) = inpData.Cells(1, i)
            r = r + 1
        Next i
        
        Set inpData = 上部工反力Sheet.Range("D1C")
        Set outData = .Range("D1C")

        r = 1
        For i = 1 To inpData.Columns.Count Step 4
            outData.Cells(r, 1) = inpData.Cells(1, i)
            r = r + 1
        Next i

        Set inpData = Nothing
        Set outData = Nothing

        .Range("桁受けN") = 上部工反力.桁受け(1)
        .Range("桁受けxC") = 上部工反力.桁受け(3)

        .Range("はりN") = 上部工反力.はり(1)
        .Range("はりxC") = 上部工反力.はり(3)

        .Range("上載土N") = 上部工反力.上載土(1)
        .Range("上載土xC") = 上部工反力.上載土(3)


        Set inpData = 上部工反力Sheet.Range("D2B")
        Set outData = .Range("D2B")

        r = 1
        For i = 1 To inpData.Columns.Count Step 4
            outData.Cells(r, 1) = inpData.Cells(1, i)
            r = r + 1
        Next i
        
        Set inpData = 上部工反力Sheet.Range("D2C")
        Set outData = .Range("D2C")

        r = 1
        For i = 1 To inpData.Columns.Count Step 4
            outData.Cells(r, 1) = inpData.Cells(1, i)
            r = r + 1
        Next i

        Set inpData = Nothing
        Set outData = Nothing
        
        

        .Range("高水位N") = 上部工反力.高水位(1)
        .Range("高水位xC") = 上部工反力.高水位(3)

        .Range("平水位N") = 上部工反力.平水位(1)
        .Range("平水位xC") = 上部工反力.平水位(3)

        .Range("低水位N") = 上部工反力.低水位(1)
        .Range("低水位xC") = 上部工反力.低水位(3)

        .Range("安全LB") = 上部工反力.列車荷重.安全性.複線.RB
        .Range("安全LC") = 上部工反力.列車荷重.安全性.複線.RC

        .Range("使用LB") = 上部工反力.列車荷重.使用性.単線.RB
        .Range("使用LC") = 上部工反力.列車荷重.使用性.単線.RC

        .Range("地震LB") = 上部工反力.地震列車.RB
        .Range("地震LC") = 上部工反力.地震列車.RC

        .Range("安全IB") = 上部工反力.衝撃荷重.安全性.複線.RB
        .Range("安全IC") = 上部工反力.衝撃荷重.安全性.複線.RC

        .Range("使用IB") = 上部工反力.衝撃荷重.使用性.単線.RB
        .Range("使用IC") = 上部工反力.衝撃荷重.使用性.単線.RC


        Set outData = .Range("直角荷重")
        For i = 1 To 8
            outData.Cells(i, 1) = 上部工反力.直角荷重強度(i).RB
            outData.Cells(i, 9) = 上部工反力.直角荷重強度(i).RC
            outData.Cells(i, 5) = 上部工反力.直角荷重位置(i).RB
            outData.Cells(i, 13) = 上部工反力.直角荷重位置(i).RC
        Next i
        Set outData = Nothing

        .Range("桁受けhG") = 上部工反力.桁受け(4)
        
    End With
    
    
    
End Sub

Private Sub set荷重計算1(直角荷重Book As Workbook)
    Dim i As Integer
    Dim j As Integer
    Dim r As Integer
    Dim c As Integer
    Dim name As String
   
    
    With 直角荷重Book.Worksheets("荷重計算")
        For i = 1 To 2
            name = "形状df" & Trim(Str(i))
            .Range(name) = 下部構造Sheet.Range(name)
        Next i
        For i = 1 To 3
            name = "形状hw" & Trim(Str(i))
            .Range(name) = 下部構造Sheet.Range(name)
        Next i
        
        Dim outData(1 To 2) As Range
        Dim inpData(1 To 2)  As Range
        
        Set inpData(1) = 下部構造Sheet.Range("単位体積重量")
        Set outData(1) = .Range("単位体積重量")
    
        outData(1).Cells(1, 1) = inpData(1).Cells(1, 1)
        outData(1).Cells(2, 1) = inpData(1).Cells(2, 1)
        outData(1).Cells(3, 1) = inpData(1).Cells(5, 1)
        outData(1).Cells(4, 1) = inpData(1).Cells(6, 1)
      
        Set outData(1) = Nothing
        Set inpData(1) = Nothing
        
        
        '支承位置
        Set inpData(1) = 上部工反力Sheet.Range("支承位置B")
        Set outData(1) = .Range("支承位置B")
        r = 1
        For i = 1 To inpData(1).Columns.Count Step 4
            outData(1).Cells(r, 1) = inpData(1).Cells(1, i)
            r = r + 1
        Next i
        Set outData(1) = Nothing
        Set inpData(1) = Nothing
        
        Set inpData(2) = 上部工反力Sheet.Range("支承位置C")
        Set outData(2) = .Range("支承位置C")
        r = 1
        For i = 1 To inpData(2).Columns.Count Step 4
            outData(2).Cells(r, 1) = inpData(2).Cells(1, i)
            r = r + 1
        Next i
        Set outData(2) = Nothing
        Set inpData(2) = Nothing
        
        '列車分担率
        '複線
        Set outData(1) = .Range("複線分担率B")
        r = 1
        For i = LBound(上部工反力.複線分担率) To UBound(上部工反力.複線分担率)
            outData(1).Cells(r, 1) = 上部工反力.複線分担率(i).RB
            r = r + 1
        Next i
        Set outData(1) = Nothing
        
        Set outData(2) = .Range("複線分担率C")
        r = 1
        For i = LBound(上部工反力.複線分担率) To UBound(上部工反力.複線分担率)
            outData(2).Cells(r, 1) = 上部工反力.複線分担率(i).RC
            r = r + 1
        Next i
        Set outData(2) = Nothing
        
        
        '列車分担率
        '単線
        ''''''''''''''''''''
        'D1+D2+L の橋脚天端における偏心量が最も大きいケースを設計ケースとする
        Dim MD1 As Single
        Dim MD2 As Single
        Dim ML As Single
        MD1 = .Range("MD1")
        MD2 = .Range("MD2")
        ''''''''''''''''''''
        Set inpData(1) = 上部工反力Sheet.Range("列車分担率B")
        Set outData(1) = .Range("単線分担率B")
        Set inpData(2) = 上部工反力Sheet.Range("列車分担率C")
        Set outData(2) = .Range("単線分担率C")
        
        Dim keyML As Single
        Dim keyi As Integer
        For i = 1 To inpData(1).Rows.Count
            Dim 合計 As Single
            For j = 1 To 2
                r = 1
                合計 = 0
                For c = 1 To inpData(j).Columns.Count Step 4
                    Dim value As Single
                    value = inpData(j).Cells(i, c)
                    outData(j).Cells(r, 1) = value
                    合計 = 合計 + value
                    r = r + 1
                Next c
            Next j
            If 合計 > 0 Then
                ML = .Range("ML")
                ML = ML + MD1 + MD2
                If ML >= keyML Then
                    keyML = ML
                    keyi = i
                End If
            End If
        Next i
        For j = 1 To 2
            r = 1
            For c = 1 To inpData(j).Columns.Count Step 4
                outData(j).Cells(r, 1) = inpData(j).Cells(keyi, c)
                r = r + 1
            Next c
        Next j
        
        Set outData(1) = Nothing
        Set inpData(1) = Nothing
        Set outData(2) = Nothing
        Set inpData(2) = Nothing
        
    End With
    
    
    
End Sub
Private Sub set骨組図(直角荷重Book As Workbook)

    Dim i As Integer
    Dim j As Integer
    Dim name As String
   
    
    With 直角荷重Book.Worksheets("骨組図")
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
            name = "Kv" & Trim(Str(i))
            .Range(name) = 直接基礎計算.Kv(i)
            name = "Ks" & Trim(Str(i))
            .Range(name) = 直接基礎計算.Ks(i)
            name = "Kr" & Trim(Str(i))
            .Range(name) = 直接基礎計算.Kr(i)
        Next i
        
        .Range("形状XC") = 上部工反力.柱(3)
        .Range("形状fg") = 上部工反力.フーチング(4)
        
        .Range("基礎形式") = Trim(下部構造Sheet.Range("基礎形式"))
        
    End With

End Sub

