Attribute VB_Name = "comon"
Public Function OpenBook(FilePath As String) As Workbook

    'ブックが開かれているかどうか調べる
    Dim FSO As Scripting.FileSystemObject
    Set FSO = CreateObject("Scripting.FileSystemObject")
    Dim FileName As String
    FileName = FSO.GetFileName(FilePath)
    Set FSO = Nothing
    
    Dim i As Long
    For i = 1 To Workbooks.Count
        If FileName = Workbooks(i).name Then
            Set OpenBook = Workbooks(i)
            Exit Function
        End If
    Next i
    
    'ブックが開かれていなければ開く
    Set OpenBook = Workbooks.Open(FilePath)
    Exit Function
    
    
End Function
