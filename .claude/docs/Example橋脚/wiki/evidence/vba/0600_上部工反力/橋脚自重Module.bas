Attribute VB_Name = "橋脚自重Module"
Option Explicit

Private Const padding = 15
Private Const Margin = 15
Private Const FontHeight = 9
Private KeyPosX As Single
Private KeyPosY As Single
Private Width   As Single
Private Height  As Single

Sub 橋脚形状作成_Click()

    Dim targetRange As Range
    Set targetRange = 橋脚自重Sheet.Range("橋脚形状図")
    
    Call Delete形状図(targetRange)
    
    Dim B1 As Single
    Dim B2 As Single
    Dim B3 As Single
    Dim B4 As Single
    Dim B5 As Single
    Dim B6 As Single
    Dim B7 As Single
    Dim B8 As Single
    Dim B9 As Single
    
    Dim W1 As Single
    Dim W2 As Single
    Dim W3 As Single
    Dim W4 As Single
    Dim W5 As Single
    Dim W6 As Single
    Dim W7 As Single
    Dim W8 As Single
    Dim W9 As Single
    
    Dim H1 As Single
    Dim H2 As Single
    Dim H3 As Single
    Dim H4 As Single
    Dim H5 As Single
    Dim H6 As Single
    
    Dim df1 As Single
    Dim df2 As Single
    
    Dim hw1 As Single
    Dim hw2 As Single
    Dim hw3 As Single
    
    'テストデータ-----------
    With 橋脚自重Sheet
    
        B1 = .Range("形状B1")
        B2 = .Range("形状B2")
        B3 = .Range("形状B3")
        B4 = .Range("形状B4")
        B5 = .Range("形状B5")
        B6 = .Range("形状B6")
        B7 = .Range("形状B7")
        B8 = .Range("形状B8")
        B9 = .Range("形状B9")
        
        W1 = .Range("形状W1")
        W2 = .Range("形状W2")
        W3 = .Range("形状W3")
        W4 = .Range("形状W4")
        W5 = .Range("形状W5")
        W6 = .Range("形状W6")
        W7 = .Range("形状W7")
        W8 = .Range("形状W8")
        W9 = .Range("形状W9")
        
        H1 = .Range("形状H1")
        H2 = .Range("形状H2")
        H3 = .Range("形状H3")
        H4 = .Range("形状H4")
        H5 = .Range("形状H5")
        H6 = .Range("形状H6")
        
        df1 = .Range("形状df1")
        df2 = .Range("形状df2")
        
        hw1 = .Range("形状hw1")
        hw2 = .Range("形状hw2")
        hw3 = .Range("形状hw3")
    End With
    '-----------------------
    
    Call drawLines(targetRange, _
                   B1, B2, B3, B4, B5, B6, B7, B8, B9, _
                   W1, W2, W3, W4, W5, W6, W7, W8, W9, _
                   H1, H2, H3, H4, H5, H6, _
                   df1, df2, hw1, hw2, hw3)

    
    Set targetRange = Nothing
    
End Sub

Public Sub drawLines(targetRange As Range, _
                          B1 As Single, B2 As Single, B3 As Single, B4 As Single, B5 As Single, B6 As Single, B7 As Single, B8 As Single, B9 As Single, _
                          W1 As Single, W2 As Single, W3 As Single, W4 As Single, W5 As Single, W6 As Single, W7 As Single, W8 As Single, W9 As Single, _
                          H1 As Single, H2 As Single, H3 As Single, H4 As Single, H5 As Single, H6 As Single, _
                          df1 As Single, df2 As Single, hw1 As Single, hw2 As Single, hw3 As Single)

    Dim i As Integer

    Dim targetSheet As Worksheet
    Set targetSheet = targetRange.Parent
    
    Dim MyShape As Shape
    
    '既存の図を削除
    Dim Top As Single
    Dim Buttom As Single
    With targetRange
        Top = .Top
        Buttom = Top + .Height
    End With
    Dim s As Shape
    For Each s In targetSheet.Shapes
        If Buttom > s.Top And s.Top > Top Then
            s.Delete
        End If
    Next
    
    'パラメータをセット
    With targetRange
        KeyPosX = .Left
        KeyPosY = .Top
        Width = .Width
        Height = .Height
    End With
    
    Dim 倍率 As Single
    Dim 橋脚高 As Single
    Dim 側面開始点 As Single
    Dim 側面寸法点 As Single
    Dim 正面開始点 As Single
    Dim 水位 As Single
    Dim 土かぶり As Single
    
    倍率 = 12
    橋脚高 = 350
    側面開始点 = targetRange.Width - ((B7 + B8 + B9) * 倍率 / 2 + 170)
    側面寸法点 = targetRange.Width - 170
    正面開始点 = targetRange.Width - ((W7 + W8 + W9) * 倍率 / 2 + 170)
    水位 = 450
    土かぶり = 110
    
    '側面
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面開始点 + ((B1 + B2 + B3) * 倍率), 橋脚高 - 90, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = "側 面 図"
                .Font.Size = 10
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    
    If H5 = 0 Then
        targetSheet.Shapes.AddShape msoShapeRectangle, 側面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高, (B7 + B8 + B9) * 倍率, (H5 + H6) * 倍率
    Else
        targetSheet.Shapes.AddLine 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高, 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 - H6 * 倍率
        targetSheet.Shapes.AddLine 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 - H6 * 倍率, B7 * 倍率 + 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 - (H6 + H5) * 倍率
        targetSheet.Shapes.AddLine B7 * 倍率 + 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 - (H6 + H5) * 倍率, (B7 + B8) * 倍率 + 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 - (H6 + H5) * 倍率
        targetSheet.Shapes.AddLine (B7 + B8) * 倍率 + 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 - (H6 + H5) * 倍率, (B7 + B8 + B9) * 倍率 + 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 - H6 * 倍率
        targetSheet.Shapes.AddLine (B7 + B8 + B9) * 倍率 + 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 - H6 * 倍率, (B7 + B8 + B9) * 倍率 + 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高
        targetSheet.Shapes.AddLine (B7 + B8 + B9) * 倍率 + 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高, 側面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高
    End If
    
    targetSheet.Shapes.AddShape msoShapeRectangle, (B7 + (B8 / 2) - (B6 / 2)) * 倍率 + 側面開始点, (H1 + H2 + H3) * 倍率 + 橋脚高, B6 * 倍率, H4 * 倍率
    
    If H3 = 0 Then
        targetSheet.Shapes.AddShape msoShapeRectangle, (B7 + (B8 / 2) - (B1 / 2)) * 倍率 + 側面開始点, 橋脚高, B1 * 倍率, ((H1 + H2) * 倍率)
    Else
        targetSheet.Shapes.AddShape msoShapeRectangle, (B7 + (B8 / 2) - (B1 / 2)) * 倍率 + 側面開始点, 橋脚高, B1 * 倍率, ((H1 + H2) * 倍率)
        targetSheet.Shapes.AddShape msoShapeRectangle, (B7 + (B8 / 2) - (B1 / 2)) * 倍率 + 側面開始点, 橋脚高 + (H1 + H2) * 倍率, B1 * 倍率, (H3) * 倍率
    End If
    
    If H1 <> 0 Then
        targetSheet.Shapes.AddShape msoShapeRectangle, (B7 + (B8 / 2) - (B1 / 2) + B2) * 倍率 + 側面開始点, 橋脚高 - H1 * 倍率, B3 * 倍率, H1 * 倍率
    End If
    
    
    '側面土かぶり
    If df1 <> 0 And df1 = df2 Then
        targetSheet.Shapes.AddLine 土かぶり - 3, ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高, 土かぶり + 400, ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高
        For i = 1 To 6
            If i < 4 Then
                targetSheet.Shapes.AddLine 土かぶり + (3 * i), ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高, 土かぶり + (3 * i) - 3, ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高 + 5
                targetSheet.Shapes.AddLine 土かぶり + 3 + (3 * i), ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高, 土かぶり + (3 * i) + 6, ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高 + 5
            Else
                targetSheet.Shapes.AddLine 土かぶり + 6 + (3 * i), ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高, 土かぶり + (3 * i) + 3, ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高 + 5
                targetSheet.Shapes.AddLine 土かぶり + 9 + (3 * i), ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高, 土かぶり + (3 * i) + 12, ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高 + 5
            End If
        Next i
    
        Set MyShape = targetSheet.Shapes.AddLine(土かぶり + 60, ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高, 土かぶり + 60, ((H1 + H2 + H3 + H4 + H5) * 倍率) + 橋脚高)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 土かぶり + 60, ((H1 + H2 + H3 + H4 + H5) * 倍率) + 橋脚高, 土かぶり + 100, ((H1 + H2 + H3 + H4 + H5) * 倍率) + 橋脚高

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 土かぶり + 40, 橋脚高 + (H1 + H2 + H3 + H4 - df1 / 2) * 倍率 + 5, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = df1 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
        
    '側面寸法
    'B1
    Set MyShape = targetSheet.Shapes.AddLine((B7 + (B8 / 2) - (B1 / 2)) * 倍率 + 側面開始点, 橋脚高 - 50, (B7 + (B8 / 2) + (B1 / 2)) * 倍率 + 側面開始点, 橋脚高 - 50)
    With MyShape.Line
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    
    targetSheet.Shapes.AddLine (B7 + (B8 / 2) - (B1 / 2)) * 倍率 + 側面開始点, 橋脚高 - 50, (B7 + (B8 / 2) - (B1 / 2)) * 倍率 + 側面開始点, 橋脚高 - 5
    targetSheet.Shapes.AddLine (B7 + (B8 / 2) + (B1 / 2)) * 倍率 + 側面開始点, 橋脚高 - 50, (B7 + (B8 / 2) + (B1 / 2)) * 倍率 + 側面開始点, 橋脚高 - 5
    
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (B7 + (B8 / 2)) * 倍率 + 側面開始点 - 15, 橋脚高 - 66, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = B1 * 1000
                .Font.Size = 8
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    'B2-B3
    If B3 <> 0 Then
        If B2 <> 0 Then
            Set MyShape = targetSheet.Shapes.AddLine((B7 + (B8 / 2) - (B1 / 2)) * 倍率 + 側面開始点, 橋脚高 - 20, (B7 + (B8 / 2) - (B1 / 2) + B2) * 倍率 + 側面開始点, 橋脚高 - 20)
            With MyShape.Line
                .BeginArrowheadStyle = msoArrowheadOpen
                .BeginArrowheadLength = msoArrowheadShort
                .BeginArrowheadWidth = msoArrowheadNarrow
                .EndArrowheadStyle = msoArrowheadOpen
                .EndArrowheadLength = msoArrowheadShort
                .EndArrowheadWidth = msoArrowheadNarrow
            End With
            
            Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (B7 + (B8 / 2) - (B1 / 2)) * 倍率 + 側面開始点 - 15, 橋脚高 - 36, 1, 1)
            With MyShape
                With .TextFrame
                    With .Characters
                        .Text = B2 * 1000
                        .Font.Size = 8
                    End With
                .AutoSize = True
                End With
            .Line.Visible = msoFalse
            .Fill.Visible = msoFalse
            End With
                
        End If
        
        Set MyShape = targetSheet.Shapes.AddLine((B7 + (B8 / 2) - (B1 / 2) + B2) * 倍率 + 側面開始点, 橋脚高 - 20, (B7 + (B8 / 2) - (B1 / 2) + B2 + B3) * 倍率 + 側面開始点, 橋脚高 - 20)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine (B7 + (B8 / 2) - (B1 / 2) + B2) * 倍率 + 側面開始点, 橋脚高 - 20, (B7 + (B8 / 2) - (B1 / 2) + B2) * 倍率 + 側面開始点, 橋脚高 - 5
        targetSheet.Shapes.AddLine (B7 + (B8 / 2) - (B1 / 2) + B2 + B3) * 倍率 + 側面開始点, 橋脚高 - 20, (B7 + (B8 / 2) - (B1 / 2) + B2 + B3) * 倍率 + 側面開始点, 橋脚高 - 5
        
        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (B7 + (B8 / 2) - (B1 / 2) + B2) * 倍率 + 側面開始点 - 5, 橋脚高 - 36, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = B3 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'B6
    If B6 <> B1 Then
        Set MyShape = targetSheet.Shapes.AddLine((B7 + (B8 / 2) - (B6 / 2)) * 倍率 + 側面開始点, 橋脚高 + (H2 + H3) * 倍率 + 30, (B7 + (B8 / 2) + (B6 / 2)) * 倍率 + 側面開始点, 橋脚高 + (H2 + H3) * 倍率 + 30)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (B7 + (B8 / 2) - (B6 / 2)) * 倍率 + 側面開始点 - 5, 橋脚高 + (H2 + H3) * 倍率 + 16, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = B6 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'B7
    Set MyShape = targetSheet.Shapes.AddLine(側面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20, B7 * 倍率 + 側面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20)
    With MyShape.Line
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    
    targetSheet.Shapes.AddLine 側面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 5, 側面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20
    targetSheet.Shapes.AddLine 側面開始点 + B7 * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 5, 側面開始点 + B7 * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20
    
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面開始点 + B7 / 2, ((H1 + H2 + H3 + H4 - H5) * 倍率) + 橋脚高 - 22, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = B7 * 1000
                .Font.Size = 8
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    'B8
    Set MyShape = targetSheet.Shapes.AddLine(B7 * 倍率 + 側面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20, (B7 + B8) * 倍率 + 側面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20)
    With MyShape.Line
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    
    targetSheet.Shapes.AddLine 側面開始点 + (B7 + B8) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 5, 側面開始点 + (B7 + B8) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20
    
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面開始点 + B7 * 倍率, ((H1 + H2 + H3 + H4 - H5) * 倍率) + 橋脚高 - 22, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = B8 * 1000
                .Font.Size = 8
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    'B9
    Set MyShape = targetSheet.Shapes.AddLine(側面開始点 + (B7 + B8) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20, 側面開始点 + (B7 + B8 + B9) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20)
    With MyShape.Line
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    
    targetSheet.Shapes.AddLine 側面開始点 + (B7 + B8 + B9) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 5, 側面開始点 + (B7 + B8 + B9) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 - 20
    
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面開始点 + (B7 + B8 + B9 / 4) * 倍率, ((H1 + H2 + H3 + H4 - H5) * 倍率) + 橋脚高 - 22, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = B9 * 1000
                .Font.Size = 8
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    'H1横断
    If H1 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 - H1 * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 - H1 * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 - 10, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H1 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H2横断
    If H2 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 + (H1 + H2) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率, 橋脚高 + (H1 + H2 / 2) * 倍率 - 10, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H2 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H3横断
    If H3 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 + (H1 + H2 + H3) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 + (H1 + H2 + H3) * 倍率 - 10, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H3 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H4横断
    If H4 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3 + H4) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3 + H4) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 + (H1 + H2 + H3 + H4) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 + (H1 + H2 + H3 + H4 / 2) * 倍率 - 15, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H4 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H5横断
    If H5 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3 + H4) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3 + H4 + H5) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3 + H4 + H5) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 + (H1 + H2 + H3 + H4 + H5) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 + (H1 + H2 + H3 + H4 + H5 / 2) * 倍率 - 10, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H5 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H6横断
    If H6 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3 + H4 + H5) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3 + H4 + H5 + H6) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 + (H1 + H2 + H3 + H4 + H5 + H6) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 + (H1 + H2 + H3 + H4 + H5 + H6) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 + (H1 + H2 + H3 + H4 + H5 + H6 / 2) * 倍率 - 5, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H6 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    '正面
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面開始点 + ((B1 + B2 + B3) * 倍率), 橋脚高 * 2 - 90, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = "正 面 図"
                .Font.Size = 10
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    If H5 = 0 Then
        targetSheet.Shapes.AddShape msoShapeRectangle, 正面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2, (W7 + W8 + W9) * 倍率, (H5 + H6) * 倍率
    Else
        targetSheet.Shapes.AddLine 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2, 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2 - H6 * 倍率
        targetSheet.Shapes.AddLine 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2 - H6 * 倍率, W7 * 倍率 + 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2 - (H6 + H5) * 倍率
        targetSheet.Shapes.AddLine W7 * 倍率 + 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2 - (H6 + H5) * 倍率, (W7 + W8) * 倍率 + 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2 - (H6 + H5) * 倍率
        targetSheet.Shapes.AddLine (W7 + W8) * 倍率 + 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2 - (H6 + H5) * 倍率, (W7 + W8 + W9) * 倍率 + 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2 - H6 * 倍率
        targetSheet.Shapes.AddLine (W7 + W8 + W9) * 倍率 + 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2 - H6 * 倍率, (W7 + W8 + W9) * 倍率 + 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2
        targetSheet.Shapes.AddLine (W7 + W8 + W9) * 倍率 + 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2, 正面開始点, (H1 + H2 + H3 + H4 + H5 + H6) * 倍率 + 橋脚高 * 2
    End If
    
    targetSheet.Shapes.AddShape msoShapeRectangle, (W7 + (W8 / 2) - (W6 / 2)) * 倍率 + 正面開始点, (H1 + H2 + H3) * 倍率 + 橋脚高 * 2, W6 * 倍率, H4 * 倍率
    
    If H3 = 0 Then
        targetSheet.Shapes.AddShape msoShapeRectangle, (W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2, W1 * 倍率, ((H1 + H2) * 倍率)
    Else
        targetSheet.Shapes.AddShape msoShapeRectangle, (W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2, W1 * 倍率, ((H1 + H2) * 倍率)
        targetSheet.Shapes.AddLine (W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点, (H1 + H2) * 倍率 + 橋脚高 * 2, ((W7 + (W8 / 2) - (W1 / 2) + W4) * 倍率) + 正面開始点, (H1 + H2 + H3) * 倍率 + 橋脚高 * 2
        targetSheet.Shapes.AddLine ((W7 + (W8 / 2) - (W1 / 2) + W1) * 倍率) + 正面開始点, (H1 + H2) * 倍率 + 橋脚高 * 2, ((W7 + (W8 / 2) - (W1 / 2) + W1 - W5) * 倍率) + 正面開始点, (H1 + H2 + H3) * 倍率 + 橋脚高 * 2
    End If
    
    If H1 <> 0 Then
        targetSheet.Shapes.AddShape msoShapeRectangle, (W7 + (W8 / 2) - (W1 / 2) + W2) * 倍率 + 正面開始点, 橋脚高 * 2 - H1 * 倍率, W3 * 倍率, H1 * 倍率
    End If
    
    '正面土かぶり
    If df1 <> 0 And df1 = df2 Then
        targetSheet.Shapes.AddLine 土かぶり - 3, ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2, 土かぶり + 400, ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2
        For i = 1 To 6
            If i < 4 Then
                targetSheet.Shapes.AddLine 土かぶり + (3 * i), ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2, 土かぶり + (3 * i) - 3, ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2 + 5
                targetSheet.Shapes.AddLine 土かぶり + 3 + (3 * i), ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2, 土かぶり + (3 * i) + 6, ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2 + 5
            Else
                targetSheet.Shapes.AddLine 土かぶり + 6 + (3 * i), ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2, 土かぶり + (3 * i) + 3, ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2 + 5
                targetSheet.Shapes.AddLine 土かぶり + 9 + (3 * i), ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2, 土かぶり + (3 * i) + 12, ((H1 + H2 + H3 + H4 + H5 - (df1 + df2) / 2) * 倍率) + 橋脚高 * 2 + 5
            End If
        Next i
        
        Set MyShape = targetSheet.Shapes.AddLine(土かぶり + 60, ((H1 + H2 + H3 + H4 + H5 - df1) * 倍率) + 橋脚高 * 2, 土かぶり + 60, ((H1 + H2 + H3 + H4 + H5) * 倍率) + 橋脚高 * 2)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 土かぶり + 60, ((H1 + H2 + H3 + H4 + H5) * 倍率) + 橋脚高 * 2, 土かぶり + 100, ((H1 + H2 + H3 + H4 + H5) * 倍率) + 橋脚高 * 2

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 土かぶり + 40, 橋脚高 * 2 + (H1 + H2 + H3 + H4 - df1 / 2) * 倍率 + 5, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = df1 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
        
    '正面寸法
    'W1
    Set MyShape = targetSheet.Shapes.AddLine((W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 - 50, (W7 + (W8 / 2) + (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 - 50)
    With MyShape.Line
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    
    targetSheet.Shapes.AddLine (W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 - 50, (W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 - 5
    targetSheet.Shapes.AddLine (W7 + (W8 / 2) + (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 - 50, (W7 + (W8 / 2) + (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 - 5
    
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (W7 + (W8 / 2)) * 倍率 + 側面開始点 - 15, 橋脚高 * 2 - 66, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = W1 * 1000
                .Font.Size = 8
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    'W2-W3
    If W3 <> 0 Then
        If W2 <> 0 Then
            Set MyShape = targetSheet.Shapes.AddLine((W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 - 20, (W7 + (W8 / 2) - (W1 / 2) + W2) * 倍率 + 正面開始点, 橋脚高 * 2 - 20)
            With MyShape.Line
                .BeginArrowheadStyle = msoArrowheadOpen
                .BeginArrowheadLength = msoArrowheadShort
                .BeginArrowheadWidth = msoArrowheadNarrow
                .EndArrowheadStyle = msoArrowheadOpen
                .EndArrowheadLength = msoArrowheadShort
                .EndArrowheadWidth = msoArrowheadNarrow
            End With
            
            Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点 - 15, 橋脚高 * 2 - 36, 1, 1)
            With MyShape
                With .TextFrame
                    With .Characters
                        .Text = W2 * 1000
                        .Font.Size = 8
                    End With
                .AutoSize = True
                End With
            .Line.Visible = msoFalse
            .Fill.Visible = msoFalse
            End With
                
        End If
        
        Set MyShape = targetSheet.Shapes.AddLine((W7 + (W8 / 2) - (W1 / 2) + W2) * 倍率 + 正面開始点, 橋脚高 * 2 - 20, (W7 + (W8 / 2) - (W1 / 2) + W2 + W3) * 倍率 + 正面開始点, 橋脚高 * 2 - 20)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine (W7 + (W8 / 2) - (W1 / 2) + W2) * 倍率 + 正面開始点, 橋脚高 * 2 - 20, (W7 + (W8 / 2) - (W1 / 2) + W2) * 倍率 + 正面開始点, 橋脚高 * 2 - 5
        targetSheet.Shapes.AddLine (W7 + (W8 / 2) - (W1 / 2) + W2 + W3) * 倍率 + 正面開始点, 橋脚高 * 2 - 20, (W7 + (W8 / 2) - (W1 / 2) + W2 + W3) * 倍率 + 正面開始点, 橋脚高 * 2 - 5
        
        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (W7 + (W8 / 2) - (W1 / 2) + W2 + W3 / 2) * 倍率 + 側面開始点 - 15, 橋脚高 * 2 - 36, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = W3 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'W4
    If W4 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine((W7 + (W8 / 2) - (W6 / 2) - W4) * 倍率 + 正面開始点, 橋脚高 * 2 + (H2 + H3) * 倍率 + 30, (W7 + (W8 / 2) - (W6 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + (H2 + H3) * 倍率 + 30)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine (W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + ((H1 + H2) * 倍率) + 5, (W7 + (W8 / 2) - (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + (H2 + H3) * 倍率 + 30
        
        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (W7 + (W8 / 2) - (W6 / 2) - W4) * 倍率 + 正面開始点 - 10, 橋脚高 * 2 + (H2 + H3) * 倍率 + 16, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = W4 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'W5
    If W5 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine((W7 + (W8 / 2) + (W6 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + (H2 + H3) * 倍率 + 30, (W7 + (W8 / 2) + (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + (H2 + H3) * 倍率 + 30)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine (W7 + (W8 / 2) + (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + ((H1 + H2) * 倍率) + 5, (W7 + (W8 / 2) + (W1 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + (H2 + H3) * 倍率 + 30
        
        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (W7 + (W8 / 2) - (W6 / 2) + W6) * 倍率 + 正面開始点 - 5, 橋脚高 * 2 + (H2 + H3) * 倍率 + 16, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = W5 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'W6
    If W6 <> W1 Then
        Set MyShape = targetSheet.Shapes.AddLine((W7 + (W8 / 2) - (W6 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + (H2 + H3) * 倍率 + 30, (W7 + (W8 / 2) + (W6 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + (H2 + H3) * 倍率 + 30)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (W7 + (W8 / 2) - (W6 / 2)) * 倍率 + 正面開始点, 橋脚高 * 2 + (H2 + H3) * 倍率 + 16, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = W6 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'W7
    Set MyShape = targetSheet.Shapes.AddLine(正面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20, W7 * 倍率 + 正面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20)
    With MyShape.Line
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    
    targetSheet.Shapes.AddLine 正面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 5, 正面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20
    targetSheet.Shapes.AddLine 正面開始点 + W7 * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 5, 正面開始点 + W7 * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20
    
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 正面開始点 + B7 / 2, ((H1 + H2 + H3 + H4 - H5) * 倍率) + 橋脚高 * 2 - 22, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = W7 * 1000
                .Font.Size = 8
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    'W8
    Set MyShape = targetSheet.Shapes.AddLine(W7 * 倍率 + 正面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20, (W7 + W8) * 倍率 + 正面開始点, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20)
    With MyShape.Line
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    
    targetSheet.Shapes.AddLine 正面開始点 + (W7 + W8) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 5, 正面開始点 + (W7 + W8) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20
    
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 正面開始点 + (W7 + W8 / 4) * 倍率, ((H1 + H2 + H3 + H4 - H5) * 倍率) + 橋脚高 * 2 - 22, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = W8 * 1000
                .Font.Size = 8
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    'W9
    Set MyShape = targetSheet.Shapes.AddLine(正面開始点 + (W7 + W8) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20, 正面開始点 + (W7 + W8 + W9) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20)
    With MyShape.Line
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    
    targetSheet.Shapes.AddLine 正面開始点 + (W7 + W8 + W9) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 5, 正面開始点 + (W7 + W8 + W9) * 倍率, ((H1 + H2 + H3 + H4) * 倍率) + 橋脚高 * 2 - 20
    
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 正面開始点 + (W7 + W8 + W9 / 4) * 倍率, ((H1 + H2 + H3 + H4 - H5) * 倍率) + 橋脚高 * 2 - 22, 1, 1)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = W9 * 1000
                .Font.Size = 8
            End With
        .AutoSize = True
        End With
    .Line.Visible = msoFalse
    .Fill.Visible = msoFalse
    End With
    
    'H1横断
    If H1 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 - H1 * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 - H1 * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 * 2 - 10, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H1 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H2横断
    If H2 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 + (H1 + H2) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率, 橋脚高 * 2 + (H1 + H2 / 2) * 倍率 - 10, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H2 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H3横断
    If H3 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 + (H1 + H2 + H3) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 * 2 + (H1 + H2 + H3) * 倍率 - 10, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H3 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H4横断
    If H4 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3 + H4) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3 + H4) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 + (H1 + H2 + H3 + H4) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 * 2 + (H1 + H2 + H3 + H4 / 2) * 倍率 - 15, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H4 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H5横断
    If H5 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3 + H4) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3 + H4 + H5) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3 + H4 + H5) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 + (H1 + H2 + H3 + H4 + H5) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 * 2 + (H1 + H2 + H3 + H4 + H5 / 2) * 倍率 - 10, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H5 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If
    
    'H6横断
    If H6 <> 0 Then
        Set MyShape = targetSheet.Shapes.AddLine(側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3 + H4 + H5) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3 + H4 + H5 + H6) * 倍率)
        With MyShape.Line
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 - H1 * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 - H1 * 倍率
        targetSheet.Shapes.AddLine 側面寸法点 + (B7 + B8 + B9) * 倍率 + 20, 橋脚高 * 2 + (H1 + H2 + H3 + H4 + H5 + H6) * 倍率, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 50, 橋脚高 * 2 + (H1 + H2 + H3 + H4 + H5 + H6) * 倍率

        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 側面寸法点 + (B7 + B8 + B9) * 倍率 - 3, 橋脚高 * 2 + (H1 + H2 + H3 + H4 + H5 + H6 / 2) * 倍率 - 5, 1, 1)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = H6 * 1000
                    .Font.Size = 8
                End With
            .AutoSize = True
            End With
        .IncrementRotation 270
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        End With
    End If

End Sub

Private Sub Delete形状図(ByVal targetRange As Range)
    
    Dim targetSheet As Worksheet
    Set targetSheet = targetRange.Parent
    
    
    '既存の図を削除
    Dim Top As Single
    Dim Buttom As Single
    With targetRange
        Top = .Top
        Buttom = Top + .Height
    End With
    Dim s As Shape
    For Each s In targetSheet.Shapes
        If Buttom > s.Top And s.Top > Top Then
            s.Delete
        End If
    Next
    
    
    'パラメータをセット
    With targetRange
        KeyPosX = .Left
        KeyPosY = .Top
        Width = .Width
        Height = .Height
    End With
    
    Set targetSheet = Nothing
    Set targetRange = Nothing
    
End Sub

