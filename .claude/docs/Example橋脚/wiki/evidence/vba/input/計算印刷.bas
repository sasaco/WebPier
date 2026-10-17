Attribute VB_Name = "計算印刷"
Public MyPath As String
Public tmpPath As String
''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
''' 固定変数 ''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
Public Const 直接基礎BOOKNAME = "0500_直接基礎.xls"
Public Const 上部工反力BOOKNAME = "0600_上部工反力.xls"
Public Const 線路荷重BOOKNAME = "0610_線路方向荷重.xls"
Public Const 直角荷重BOOKNAME = "0620_直角方向荷重.xls"

Public Sub 計算スタートボタン_Click()

    '準備 '''''''''''''''''''''''''''''''''''
    tmpPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(ThisWorkbook.Path)
    '''''''''''''''''''''''''''''''''''''''''

    Dim 基礎形式 As String
    基礎形式 = 下部構造Sheet.Range("基礎形式")
    
    If Trim(基礎形式) = "直接基礎" Then
        Call 直接基礎計算.計算
        Call 上部工反力.計算
        Call 線路荷重.計算
        Call 直角荷重.計算
    Else
        MsgBox "まだ、作成途中"
    End If


    Call MsgBox("計算が完了しました。")

End Sub
