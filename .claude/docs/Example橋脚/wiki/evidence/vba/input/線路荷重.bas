Attribute VB_Name = "線路荷重"

Public Sub 計算()

    Dim 線路荷重Book As Workbook
    Set 線路荷重Book = comon.OpenBook(計算印刷.tmpPath & 計算印刷.線路荷重BOOKNAME)
    
    Call set骨組図(線路荷重Book)
    Call set荷重計算(線路荷重Book)
    
    線路荷重Book.Save
    線路荷重Book.Close
    Set 線路荷重Book = Nothing
End Sub

Private Sub set荷重計算(線路荷重Book As Workbook)
    Dim i As Integer
    Dim name As String
   
    
    With 線路荷重Book.Worksheets("荷重計算")
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
        
        .Range("起点側f") = 上部構造Sheet.Range("起点側f")
        .Range("終点側f") = 上部構造Sheet.Range("終点側f")
        
        
        .Range("フーチングN") = 上部工反力.フーチング(1)
        .Range("フーチングxL") = 上部工反力.フーチング(2)
       
        .Range("D1B") = 上部工反力Sheet.Range("ΣD1B")
        .Range("D1C") = 上部工反力Sheet.Range("ΣD1C")
       
        .Range("桁受けN") = 上部工反力.桁受け(1)
        .Range("桁受けxL") = 上部工反力.桁受け(2)
       
        .Range("はりN") = 上部工反力.はり(1)
        .Range("はりxL") = 上部工反力.はり(2)
       
        .Range("上載土N") = 上部工反力.上載土(1)
        .Range("上載土xL") = 上部工反力.上載土(2)
       
        .Range("D2B") = 上部工反力Sheet.Range("ΣD2B")
        .Range("D2C") = 上部工反力Sheet.Range("ΣD2C")
       
        .Range("高水位N") = 上部工反力.高水位(1)
        .Range("高水位xL") = 上部工反力.高水位(2)
       
        .Range("平水位N") = 上部工反力.平水位(1)
        .Range("平水位xL") = 上部工反力.平水位(2)
       
        .Range("低水位N") = 上部工反力.低水位(1)
        .Range("低水位xL") = 上部工反力.低水位(2)
        
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
        
        
        Set outData = .Range("線路荷重")
        For i = 1 To 10
            outData.Cells(i, 1) = 上部工反力.線路荷重強度(i).RB
            outData.Cells(i, 5) = 上部工反力.線路荷重強度(i).RC
        Next i
        Set outData = Nothing
        
        .Range("桁受けhG") = 上部工反力.桁受け(4)
        
    End With
    
    
    
End Sub
Private Sub set骨組図(線路荷重Book As Workbook)

    Dim i As Integer
    Dim j As Integer
    Dim name As String
   
    
    With 線路荷重Book.Worksheets("骨組図")
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
        
        .Range("形状XL") = 上部工反力.柱(2)
        .Range("形状fg") = 上部工反力.フーチング(4)
        
        .Range("基礎形式") = Trim(下部構造Sheet.Range("基礎形式"))
        
    End With

End Sub
