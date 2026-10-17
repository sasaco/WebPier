Attribute VB_Name = "列車荷重Module"
Private Const padding = 15
Private Const FontHeight = 9
Private KeyPosX As Single
Private KeyPosY As Single
Private Width   As Single
Private Height  As Single
Private Lx      As Variant
Private 桁LineY As Single
Private scaleX  As Single

Private Type LiveLoad
    p As Single
    X As Single
End Type
Public Type Reaction
    Rd       As Single
    Formula  As String
    p As Single
    W As Single
    X As Single
    L As Single
End Type

Sub test_Click()
    '桁の情報
    Dim L1 As Single
    Dim L2 As Single
    Dim L3 As Single
    Dim L4 As Single
    Dim L5 As Single
    Dim L6 As Single
    Dim n As Integer
    Dim Lb As Single
    Dim a1 As Single
    Dim a2 As Single
    Dim a3 As Single
    Dim p As Single
    Dim W As Single
    
    'テストデ－タ ------------------------
    With 列車荷重Sheet
        L1 = .Range("起点側L1")
        L2 = .Range("起点側スパン")
        L3 = .Range("起点側L2")
        L4 = .Range("終点側L1")
        L5 = .Range("終点側スパン")
        L6 = .Range("終点側L2")
    
        n = .Range("編成数")
        Lb = .Range("車両長")
        a1 = .Range("軸距a1")
        a2 = .Range("軸距a2")
        a3 = 0 'まだ作ってない
        p = .Range("軸重p")
        W = 0
    End With
    '------------------------------------
    列車荷重Sheet.Range("RAFormula") = ""
    列車荷重Sheet.Range("RAValue") = 0
    列車荷重Sheet.Range("RBFormula") = ""
    列車荷重Sheet.Range("RBValue") = 0
    列車荷重Sheet.Range("RCFormula") = ""
    列車荷重Sheet.Range("RCValue") = 0
    列車荷重Sheet.Range("RDFormula") = ""
    列車荷重Sheet.Range("RDValue") = 0
    Dim RR() As Reaction
    RR = Get反力(列車荷重Sheet.Range("列車載荷図"), _
                 L1, L2, L3, L4, L5, L6, _
                 n, Lb, a1, a2, a3, p, W)
    '反力の計算式を描く
    列車荷重Sheet.Range("RAFormula") = RR(1).Formula
    列車荷重Sheet.Range("RAValue") = RR(1).Rd
    列車荷重Sheet.Range("RBFormula") = RR(2).Formula
    列車荷重Sheet.Range("RBValue") = RR(2).Rd
    列車荷重Sheet.Range("RCFormula") = RR(3).Formula
    列車荷重Sheet.Range("RCValue") = RR(3).Rd
    列車荷重Sheet.Range("RDFormula") = RR(4).Formula
    列車荷重Sheet.Range("RDValue") = RR(4).Rd
    
End Sub

Public Function Get反力(targetRange As Range, L1 As Single, L2 As Single, L3 As Single, L4 As Single, L5 As Single, L6 As Single, _
                        n As Integer, Lb As Single, a1 As Single, a2 As Single, a3 As Single, p As Single, W As Single) As Reaction()

On Error GoTo errorHandler

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
    
    
    '桁の図を描く
    If print桁(targetRange, L1, L2, L3, L4, L5, L6) = False Then GoTo errorHandler
    
    '列車の軸配置をセットする
    Dim Li() As LiveLoad
    Li = Set列車配置(n, Lb, a1, a2, a3, p, W)
    If UBound(Li) = 0 Then GoTo errorHandler
    
    '反力を求める
    Dim RR() As Reaction
    Dim LR() As LiveLoad
    LR = Li
    RR = Get列車反力1(L1, L2, L3, L4, L5, L6, LR, "RB+RC")
    
    '列車の軸配置を描く
    Call print列車(targetRange, L1, L2, L3, L4, L5, L6, LR)
    

    Get反力 = RR
    Set targetSheet = Nothing
    Set Lt = Nothing
    Exit Function
   
errorHandler:
    Set targetSheet = Nothing
    Set Lt = Nothing
    Erase Get反力
    
End Function


Private Function Get列車反力1(L1 As Single, L2 As Single, L3 As Single, L4 As Single, L5 As Single, L6 As Single, Li() As LiveLoad, RdType As String) As Reaction()
    
    Dim i As Integer
    Dim j As Integer
    Dim k As Integer
    
    Dim keyR As Single
    Dim RR() As Reaction
    Dim LR() As LiveLoad

On Error GoTo errorHandler
    
    
    Dim Rd() As Reaction
    Dim Lj() As LiveLoad
    Dim Lk() As LiveLoad
    Dim t    As LiveLoad
    Dim Lxx  As Variant
    
    Lxx = Array(0, L1, L1 + L2, L1 + L2 + L3, L1 + L2 + L3 + L4, L1 + L2 + L3 + L4 + L5, L1 + L2 + L3 + L4 + L5 + L6)
    m = UBound(Li)

    
    For i = 1 To m '列車の車軸
       
        '列車の車軸を１つずつずらしていく
        Lj = Li
        t = Li(i) '最初の軸位置
        For j = 1 To m
            Lj(j).X = Lj(j).X - t.X '最初の軸位置を控除する
        Next j
        
        For j = 6 To 0 Step -1 '支点の数
            '各支点の直上に１つめの車軸が載った時のその他の車軸の位置関係
            Dim L As Single
            Erase Lk
            Dim ii As Integer: ii = 0
            For k = 1 To m
                t = Lj(k)
                L = Round(Lxx(j) - t.X, 3)
                If L < 0 Then Exit For
                If L <= L1 + L2 + L3 + L4 + L5 + L6 Then
                    t.X = L
                    ii = ii + 1
                    ReDim Preserve Lk(1 To ii)
                    Lk(ii) = t
                End If
            Next k
            
            If ii = 0 Then
                '何かしんないけどエラー回避
            Else
                Rd = Get列車反力2(L1, L2, L3, L4, L5, L6, Lk)
                
                If UBound(Rd) > 0 Then  '反力の算出時にエラーが出ても続ける
                    Dim p As Single
                    Select Case RdType
                        Case "RA" 'RA に着目
                            p = Rd(1).Rd
                        Case "RB" 'RB に着目
                            p = Rd(2).Rd
                        Case "RC" 'RC に着目
                            p = Rd(3).Rd
                        Case "RD" 'RD に着目
                            p = Rd(4).Rd
                        Case "RA+RB" 'RA+RB に着目
                            p = Rd(1).Rd + Rd(2).Rd
                        Case "RB+RC" 'RB+RC に着目
                            p = Rd(2).Rd + Rd(3).Rd
                        Case "RC+RD" 'RC+RD に着目
                            p = Rd(3).Rd + Rd(4).Rd
                        Case "RA+RB+RC+RD" 'RC+RD に着目
                            p = Rd(1).Rd + Rd(2).Rd + Rd(3).Rd + Rd(4).Rd
                    End Select
                    If p > keyR Then
                        LR = Lk
                        RR = Rd
                        keyR = p
                    End If
                End If
            End If
        Next j
    Next i
    
    Li = LR
    Get列車反力1 = RR
    
    Exit Function
    
errorHandler:

    
    Erase Get列車反力1

End Function

Private Function Get列車反力2(L1 As Single, L2 As Single, L3 As Single, L4 As Single, L5 As Single, L6 As Single, Lk() As LiveLoad) As Reaction()
    
    Dim Rd(1 To 4) As Reaction
    Dim i As Integer
    Dim j As Integer
    Dim k As Integer
    
On Error GoTo errorHandler
    Dim La As Single
    La = L1 + L2 + L3
    Dim Lb As Single
    Lb = L4 + L5 + L6

    Dim Px As LiveLoad
    Dim n As Integer
    n = UBound(Lk)
    Dim B As Integer:     B = 0
    Dim Rb() As Reaction: ReDim Rb(1 To n)
    Dim c As Integer:     c = 0
    Dim Rc() As Reaction: ReDim Rc(1 To n)
    
    For i = LBound(Lk) To UBound(Lk)
        Px = Lk(i)
        If Px.X < La Then
            B = B + 1
            Rb(B) = Get集中反力(L1, L2, L3, Px)
        ElseIf Px.X > La Then
            Px.X = Lb - (Px.X - La)
            c = c + 1
            Rc(c) = Get集中反力(L6, L5, L4, Px)
        ElseIf Px.X = La Then
            Dim tb As Reaction
            Dim tc As Reaction
            tb = Get集中反力(L1, L2, L3, Px)
            Px.X = Lb - (Px.X - La)
            tc = Get集中反力(L6, L5, L4, Px)
            If tb.Rd > tc.Rd Then
                B = B + 1
                Rb(B) = tb
            Else
                c = c + 1
                Rc(c) = tc
            End If
            
        End If
    Next i


    Dim Formula() As String
    
    
    If B > 0 Then
        'RBの集計 ===========================================================
        ReDim Formula(1 To B, 1 To 3)
        j = 0
        k = 0
        With Rd(2)
            '反力
            For i = 1 To B
                .Rd = .Rd + Rb(i).Rd
            Next i
            '計算式
            For i = 1 To B
                If Rb(i).p <> .p Or Rb(i).L <> .L Or Rb(i).W <> .W Then
                    If j > 0 And k > 0 Then Formula(j, 3) = "(" & Formula(j, 3) & ")"
                    j = j + 1
                    If Rb(i).W >= 0 Then
                        Formula(j, 1) = Format(Rb(i).p, "0.00")
                    Else
                        Formula(j, 1) = Format(-Rb(i).W, "0.00") & "×" & Format(Rb(i).p, "0.000")
                    End If
                    Formula(j, 2) = Format(Rb(i).L, "0.000")
                    Formula(j, 3) = Format(Rb(i).X, "0.000")
                    
                    .p = Rb(i).p
                    .L = Rb(i).L
                    .W = Rb(i).W
                    k = 0
                Else
                    Formula(j, 3) = Formula(j, 3) & "＋" & Format(Rb(i).X, "0.000")
                    k = k + 1
                End If
            Next i
            If k > 0 Then Formula(j, 3) = "(" & Formula(j, 3) & ")"
            '最初
            .Formula = Formula(1, 1) & "×" & Formula(1, 3) & "/" & Formula(1, 2)
            For i = 2 To j
                .Formula = .Formula & "＋" & Formula(i, 1) & "×" & Formula(i, 3) & "/" & Formula(i, 2)
            Next i
        End With
        
        
        'RAの集計 -----------------------------------------------------------
        ReDim Formula(1 To B, 1 To 2)
        j = 0
        k = 0
        With Rd(1)
            '反力
            For i = 1 To B
                .Rd = .Rd + Rb(i).p * IIf(Rb(i).p > 0, 1, -Rb(i).W)
            Next i
            .Rd = .Rd - Rd(2).Rd
            '計算式
            For i = 1 To B
                If Rb(i).p <> .p Or Rb(i).L <> .L Or Rb(i).W <> .W Then
                    j = j + 1
                    If Rb(i).W >= 0 Then
                        Formula(j, 1) = Format(Rb(i).p, "0.00")
                    Else
                        Formula(j, 1) = Format(-Rb(i).W, "0.00") & "×" & Format(Rb(i).p, "0.000")
                    End If
                    .p = Rb(i).p
                    .L = Rb(i).L
                    .W = Rb(i).W
                    k = 1
                Else
                    k = k + 1
                End If
                Formula(j, 2) = Format(k, "0")
            Next i
            '最初
            .Formula = Formula(1, 1) & "×" & Formula(1, 2)
            For i = 2 To j
                .Formula = .Formula & "＋" & Formula(i, 1) & "×" & Formula(i, 2)
            Next i
            .Formula = .Formula & "-" & Format(Rd(2).Rd, "0.00")
        End With
    End If
    
    If c > 0 Then
        'RCの集計 ===========================================================
        ReDim Formula(1 To c, 1 To 3)
        j = 0
        k = 0
        With Rd(3)
            '反力
            For i = 1 To c
                .Rd = .Rd + Rc(i).Rd
            Next i
            '計算式
            For i = 1 To c
                If Rc(i).p <> .p Or Rc(i).L <> .L Or Rc(i).W <> .W Then
                    If j > 0 And k > 0 Then Formula(j, 3) = "(" & Formula(j, 3) & ")"
                    j = j + 1
                    If Rc(i).W >= 0 Then
                        Formula(j, 1) = Format(Rc(i).p, "0.00")
                    Else
                        Formula(j, 1) = Format(-Rc(i).W, "0.00") & "×" & Format(Rc(i).p, "0.000")
                    End If
                    Formula(j, 2) = Format(Rc(i).L, "0.000")
                    Formula(j, 3) = Format(Rc(i).X, "0.000")
                    
                    .p = Rc(i).p
                    .L = Rc(i).L
                    .W = Rc(i).W
                    k = 0
                Else
                    Formula(j, 3) = Formula(j, 3) & "＋" & Format(Rc(i).X, "0.000")
                    k = k + 1
                End If
            Next i
            If k > 0 Then Formula(j, 3) = "(" & Formula(j, 3) & ")"
            '最初
            .Formula = Formula(1, 1) & "×" & Formula(1, 3) & "/" & Formula(1, 2)
            For i = 2 To j
                .Formula = .Formula & "＋" & Formula(i, 1) & "×" & Formula(i, 3) & "/" & Formula(i, 2)
            Next i
        End With
        
        
        'RDの集計 -----------------------------------------------------------
        ReDim Formula(1 To c, 1 To 2)
        j = 0
        k = 0
        With Rd(4)
            '反力
            For i = 1 To c
                .Rd = .Rd + Rc(i).p * IIf(Rc(i).p > 0, 1, -Rc(i).W)
            Next i
            .Rd = .Rd - Rd(3).Rd
            '計算式
            For i = 1 To c
                If Rc(i).p <> .p Or Rc(i).L <> .L Or Rc(i).W <> .W Then
                    j = j + 1
                    If Rc(i).W >= 0 Then
                        Formula(j, 1) = Format(Rc(i).p, "0.00")
                    Else
                        Formula(j, 1) = Format(-Rc(i).W, "0.00") & "×" & Format(Rc(i).p, "0.000")
                    End If
                    .p = Rc(i).p
                    .L = Rc(i).L
                    .W = Rc(i).W
                    k = 1
                Else
                    k = k + 1
                End If
                Formula(j, 2) = Format(k, "0")
            Next i
            '最初
            .Formula = Formula(1, 1) & "×" & Formula(1, 2)
            For i = 2 To j
                .Formula = .Formula & "＋" & Formula(i, 1) & "×" & Formula(i, 2)
            Next i
            .Formula = .Formula & "-" & Format(Rd(3).Rd, "0.00")
        End With
    End If
    
    
    Get列車反力2 = Rd


    Exit Function
    
errorHandler:

    
    Erase Get列車反力2
    
End Function

Private Function Get集中反力(L1 As Single, L2 As Single, L3 As Single, Px As LiveLoad) As Reaction
    Dim a As Single
    Dim R As Reaction
    
On Error GoTo errorHandler
    
    If Px.p > 0 Then
        a = Px.X - L1
        R.Rd = Px.p * a / L2
        R.p = Px.p
        R.W = 0
        R.X = a
        R.L = L2
    Else '分布荷重
        a = (Px.X / 2) - L1
        R.Rd = -Px.p * Px.X * a / L2
        R.W = Px.p
        R.p = Px.X
        R.X = a
        R.L = L2
    End If
    Get集中反力 = R
    Exit Function
    
errorHandler:
    Dim err As Reaction
    Get集中反力 = err
    
End Function


Private Function Set列車配置(n As Integer, Lb As Single, a1 As Single, a2 As Single, a3 As Single, p As Single, W As Single) As LiveLoad()
    
    Dim Li() As LiveLoad
    Dim i As Integer
    Dim j As Integer
    
On Error GoTo errorHandler
    
    Dim a4 As Single

    Dim ni As Integer
    Dim np As Integer
    
    
    If a2 > 0 Then
        ni = 4 * n
        a4 = Lb - a1 - a2 - a2
    Else
        ni = 2 * n
        a4 = Lb - a1
    End If
    If W > 0 Then
        ni = ni + 1
    End If
    
    ReDim Li(1 To ni)
    
    Dim t As LiveLoad
    t.p = p
    t.X = 0
    
    For j = 1 To n
        If a2 > 0 Then
            i = (j - 1) * 4
            Li(i + 1) = t
            t.X = t.X + a2
            Li(i + 2) = t
            t.X = t.X + a4
            Li(i + 3) = t
            t.X = t.X + a2
            Li(i + 4) = t
            t.X = t.X + a1
        ElseIf a1 > 0 Then
            i = (j - 1) * 2
            Li(i + 1) = t
            t.X = t.X + a4
            Li(i + 2) = t
            t.X = t.X + a1
        End If
    Next j
    If W > 0 Then
        t.p = -W
        t.X = (Lb * n) - a1 + a3
        Li(ni) = t
    End If
    Set列車配置 = Li
    Exit Function
    
errorHandler:
    Erase Set列車配置

End Function

Private Function print桁(targetRange As Range, L1 As Single, L2 As Single, L3 As Single, L4 As Single, L5 As Single, L6 As Single) As Boolean

    Dim i As Integer
    
On Error GoTo errorHandler
    Dim targetSheet As Worksheet
    Set targetSheet = targetRange.Parent
    
    '桁の線長を決定、描画
    Dim 桁LineXi As Single
    Dim 桁LineXj As Single
    桁LineY = KeyPosY + Height / 2
    桁LineXi = KeyPosX + padding
    桁LineXj = KeyPosX + Width - padding
    
    Dim MyShape As Shape
    Set MyShape = targetSheet.Shapes.AddLine(桁LineXi, 桁LineY, 桁LineXj, 桁LineY)
    With MyShape
        .Line.Weight = 1.5
    End With
    
    'スケールを決定
    scaleX = (桁LineXj - 桁LineXi) / (L1 + L2 + L3 + L4 + L5 + L6)
    
    '支点位置を決定
    Lx = Array(桁LineXi, L1, L2, L3, L4, L5, 桁LineXj)
    For i = 1 To 5
        Lx(i) = Lx(i - 1) + Lx(i) * scaleX
    Next i
     
    '支点位置を描画
    Dim 支点Width As Single
    Dim 支点Height As Single
    支点Width = 7
    支点Height = 7
    
    Dim 支点LineY As Single
    Dim 支点LineX As Single
    支点LineY = 桁LineY
    For i = 1 To 2
        支点LineX = Lx(i)
        Set MyShape = targetSheet.Shapes.AddShape(msoShapeIsoscelesTriangle, 支点LineX - 支点Width / 2, 支点LineY, 支点Width, 支点Height)
        With MyShape
            .Fill.Visible = msoFalse
        End With
    Next i
    For i = 4 To 5
        支点LineX = Lx(i)
        Set MyShape = targetSheet.Shapes.AddShape(msoShapeIsoscelesTriangle, 支点LineX - 支点Width / 2, 支点LineY, 支点Width, 支点Height)
        With MyShape
            .Fill.Visible = msoFalse
        End With
    Next i
    
    '支点寸法
    Dim 寸法Yi As Single
    Dim 寸法Yj As Single
    Dim 値y As Single
    Dim 値x As Single

    Dim 寸法Y1 As Single
    Dim 寸法Y2 As Single
    
    '支点寸法縦│線を描画
    寸法Yi = 桁LineY + 支点Height
    寸法Y1 = KeyPosY + Height - padding
    寸法Yj = 寸法Y1
    For i = 0 To 6 Step 3
        With targetSheet.Shapes.AddLine(Lx(i), 寸法Yi, Lx(i), 寸法Yj).Line
            .Weight = 0.25
        End With
    Next i
    
    '支点寸法横←→線を描画
    Set MyShape = targetSheet.Shapes.AddLine(Lx(0), 寸法Y1, Lx(3), 寸法Y1)
    With MyShape.Line
        .Weight = 0.25
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    Set MyShape = targetSheet.Shapes.AddLine(Lx(3), 寸法Y1, Lx(6), 寸法Y1)
    With MyShape.Line
        .Weight = 0.25
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    
    '支点寸法値を描画
    値y = 寸法Y1
    値x = Lx(1) + (Lx(2) - Lx(1)) / 2
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 値x, 値y, 10, FontHeight)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = Format(L1 + L2 + L3, "0.000")
                With .Font
                    .Size = FontHeight
                    .name = "ＭＳ 明朝"
                End With
            End With
'            .HorizontalAlignment = xlHAlignCenter
            .VerticalAlignment = xlVAlignBottom
            .AutoSize = True
        End With
        .Top = 寸法Y1 - .Height
        .Left = .Left - .Width / 2
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        寸法Y2 = .Top
    End With
    
    値y = 寸法Y1
    値x = Lx(4) + (Lx(5) - Lx(4)) / 2
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 値x, 値y, 10, FontHeight)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = Format(L4 + L5 + L6, "0.000")
                With .Font
                    .Size = FontHeight
                    .name = "ＭＳ 明朝"
                End With
            End With
'            .HorizontalAlignment = xlHAlignCenter
            .VerticalAlignment = xlVAlignBottom
            .AutoSize = True
        End With
        .Top = 寸法Y1 - .Height
        .Left = .Left - .Width / 2
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
        寸法Y2 = IIf(寸法Y2 < .Top, 寸法Y2, .Top)
    End With
    
    '支点寸法縦│線を描画
    寸法Yj = 寸法Y2
    For i = 1 To 2
        With targetSheet.Shapes.AddLine(Lx(i), 寸法Yi, Lx(i), 寸法Yj).Line
            .Weight = 0.25
        End With
    Next i
    For i = 4 To 5
        With targetSheet.Shapes.AddLine(Lx(i), 寸法Yi, Lx(i), 寸法Yj).Line
            .Weight = 0.25
        End With
    Next i
    
    '支点寸法横←→線を描画
    Set MyShape = targetSheet.Shapes.AddLine(KeyPosX, 寸法Y2, Lx(0), 寸法Y2)
    With MyShape.Line
        .Weight = 0.25
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    Set MyShape = targetSheet.Shapes.AddLine(Lx(0), 寸法Y2, Lx(1), 寸法Y2)
    With MyShape.Line
        .Weight = 0.25
    End With
    Set MyShape = targetSheet.Shapes.AddLine(Lx(1), 寸法Y2, Lx(2), 寸法Y2)
    With MyShape.Line
        .Weight = 0.25
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    Set MyShape = targetSheet.Shapes.AddLine(Lx(2), 寸法Y2, Lx(4), 寸法Y2)
    With MyShape.Line
        .Weight = 0.25
    End With
    Set MyShape = targetSheet.Shapes.AddLine(Lx(4), 寸法Y2, Lx(5), 寸法Y2)
    With MyShape.Line
        .Weight = 0.25
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
        .EndArrowheadStyle = msoArrowheadOpen
        .EndArrowheadLength = msoArrowheadShort
        .EndArrowheadWidth = msoArrowheadNarrow
    End With
    Set MyShape = targetSheet.Shapes.AddLine(Lx(5), 寸法Y2, Lx(6), 寸法Y2)
    With MyShape.Line
        .Weight = 0.25
    End With
    Set MyShape = targetSheet.Shapes.AddLine(Lx(6), 寸法Y2, KeyPosX + Width, 寸法Y2)
    With MyShape.Line
        .Weight = 0.25
        .BeginArrowheadStyle = msoArrowheadOpen
        .BeginArrowheadLength = msoArrowheadShort
        .BeginArrowheadWidth = msoArrowheadNarrow
    End With
    
    '支点寸法値を描画
    Dim tx As New Collection
    
    値y = 寸法Y2
    値x = KeyPosX
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 値x, 値y, 10, FontHeight)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = Format(L1, "0.000")
                With .Font
                    .Size = FontHeight
                    .name = "ＭＳ 明朝"
                End With
            End With
'            .HorizontalAlignment = xlHAlignCenter
            .VerticalAlignment = xlVAlignBottom
            .AutoSize = True
        End With
        .Top = 寸法Y2 - .Height
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
    End With
    tx.Add MyShape
    
    値y = 寸法Y2
    値x = Lx(1) + (Lx(2) - Lx(1)) / 2
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 値x, 値y, 10, FontHeight)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = Format(L2, "0.000")
                With .Font
                    .Size = FontHeight
                    .name = "ＭＳ 明朝"
                End With
            End With
'            .HorizontalAlignment = xlHAlignCenter
            .VerticalAlignment = xlVAlignBottom
            .AutoSize = True
        End With
        .Top = 寸法Y2 - .Height
        .Left = .Left - .Width / 2
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
    End With
    tx.Add MyShape
     
    値y = 寸法Y2
    値x = Lx(3)
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 値x, 値y, 10, FontHeight)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = Format(L3, "0.000")
                With .Font
                    .Size = FontHeight
                    .name = "ＭＳ 明朝"
                End With
            End With
'            .HorizontalAlignment = xlHAlignCenter
            .VerticalAlignment = xlVAlignBottom
            .AutoSize = True
        End With
        .Top = 寸法Y2 - .Height
        .Left = .Left - .Width
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
    End With
    tx.Add MyShape
    
     
    値y = 寸法Y2
    値x = Lx(3)
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 値x, 値y, 10, FontHeight)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = Format(L4, "0.000")
                With .Font
                    .Size = FontHeight
                    .name = "ＭＳ 明朝"
                End With
            End With
'            .HorizontalAlignment = xlHAlignCenter
            .VerticalAlignment = xlVAlignBottom
            .AutoSize = True
        End With
        .Top = 寸法Y2 - .Height
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
    End With
    tx.Add MyShape
     
    値y = 寸法Y2
    値x = Lx(4) + (Lx(5) - Lx(4)) / 2
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 値x, 値y, 10, FontHeight)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = Format(L5, "0.000")
                With .Font
                    .Size = FontHeight
                    .name = "ＭＳ 明朝"
                End With
            End With
'            .HorizontalAlignment = xlHAlignCenter
            .VerticalAlignment = xlVAlignBottom
            .AutoSize = True
        End With
        .Top = 寸法Y2 - .Height
        .Left = .Left - .Width / 2
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
    End With
    tx.Add MyShape
     
    値y = 寸法Y2
    値x = KeyPosX + Width
    Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, 値x, 値y, 10, FontHeight)
    With MyShape
        With .TextFrame
            With .Characters
                .Text = Format(L6, "0.000")
                With .Font
                    .Size = FontHeight
                    .name = "ＭＳ 明朝"
                End With
            End With
'            .HorizontalAlignment = xlHAlignCenter
            .VerticalAlignment = xlVAlignBottom
            .AutoSize = True
        End With
        .Top = 寸法Y2 - .Height
        .Left = .Left - .Width
        .Line.Visible = msoFalse
        .Fill.Visible = msoFalse
    End With
    tx.Add MyShape
    
    '重なった支点寸法値をずらす
    Dim X1 As Single
    Dim X2 As Single
    Set MyShape = tx(2)
    X2 = MyShape.Left
    Set MyShape = tx(1)
    X1 = MyShape.Left + MyShape.Width
    If X1 > X2 Then
        MyShape.Top = MyShape.Top - MyShape.Height / 2
    End If
    Set MyShape = tx(2)
    X2 = MyShape.Left + MyShape.Width
    Set MyShape = tx(3)
    X1 = MyShape.Left
    If X2 > X1 Then
        MyShape.Top = MyShape.Top - MyShape.Height / 2
    End If
    '''''
    Set MyShape = tx(5)
    X2 = MyShape.Left
    Set MyShape = tx(4)
    X1 = MyShape.Left + MyShape.Width
    If X1 > X2 Then
        MyShape.Top = MyShape.Top - MyShape.Height / 2
    End If
    Set MyShape = tx(5)
    X2 = MyShape.Left + MyShape.Width
    Set MyShape = tx(6)
    X1 = MyShape.Left
    If X2 > X1 Then
        MyShape.Top = MyShape.Top - MyShape.Height / 2
    End If

    Set targetSheet = Nothing
    Set MyShape = Nothing
    Set tx = Nothing
    print桁 = True
    Exit Function
    
errorHandler:
    print桁 = False
    Set targetSheet = Nothing
    Set MyShape = Nothing
    Set tx = Nothing

End Function

Private Sub print列車(targetRange As Range, L1 As Single, L2 As Single, L3 As Single, L4 As Single, L5 As Single, L6 As Single, LR() As LiveLoad)
    
    Dim i As Integer
    
On Error GoTo errorHandler
    Dim targetSheet As Worksheet
    Set targetSheet = targetRange.Parent
    
    Dim MyShape As Shape
    
    Dim Y As Single
    Dim X As Single
    Dim v As Variant
    Dim 寸法Yi As Single
    Dim 寸法Yj As Single
    
    Dim d As New Collection
    
    Y = 桁LineY
    寸法Yi = KeyPosY + padding + FontHeight
    寸法Yj = Y - 30 - 2
    For i = LBound(LR) To UBound(LR)
        X = KeyPosX + padding + LR(i).X * scaleX
        With targetSheet.Shapes.AddLine(X, Y, X, Y - 30).Line
            .Weight = 1#
            .BeginArrowheadStyle = msoArrowheadTriangle
            .BeginArrowheadLength = msoArrowheadLengthMedium
            .BeginArrowheadWidth = msoArrowheadNarrow
        End With
        With targetSheet.Shapes.AddLine(X, 寸法Yi, X, 寸法Yj).Line
            .Weight = 0.25
            d.Add LR(i).X
        End With
    Next i
    
    '支点寸法縦│線を描画
    Dim G1 As Variant
    Dim G2 As Variant
    G1 = Array(Lx(1), Lx(3), Lx(5))
    G2 = Array(L1, L1 + L2 + L3, L1 + L2 + L3 + L4 + L5)
    
    寸法Yj = 桁LineY - 2
    
    Dim e As Boolean
    For i = 0 To 2
        e = False
        For Each v In d
            If Int(1000 * v) = Int(1000 * G2(i)) Then
                e = True
                Exit For
            End If
        Next
        If e = False Then
            With targetSheet.Shapes.AddLine(G1(i), 寸法Yi, G1(i), 寸法Yj).Line
                .Weight = 0.25
                For j = d.Count To 1 Step -1
                    If d(j) > G2(i) Then
                        Call d.Add(G2(i), , , j)
                        e = True
                        Exit For
                    End If
                Next j
                If e = False Then
                    Call d.Add(G2(i), , 1)
                End If
            End With
        End If
    Next i
    
    '支点寸法横←→線を描画
    Dim X1 As Single
    Dim X2 As Single
    Dim tx As New Collection

    For i = 2 To d.Count
        X1 = d(i)
        X2 = d(i - 1)
        X = X2 - X1
        X1 = KeyPosX + padding + X1 * scaleX
        X2 = KeyPosX + padding + X2 * scaleX
        
        With targetSheet.Shapes.AddLine(X1, 寸法Yi, X2, 寸法Yi).Line
            .Weight = 0.25
            .BeginArrowheadStyle = msoArrowheadOpen
            .BeginArrowheadLength = msoArrowheadShort
            .BeginArrowheadWidth = msoArrowheadNarrow
            .EndArrowheadStyle = msoArrowheadOpen
            .EndArrowheadLength = msoArrowheadShort
            .EndArrowheadWidth = msoArrowheadNarrow
        End With
        
        '支点寸法値を描画
        Set MyShape = targetSheet.Shapes.AddTextbox(msoTextOrientationHorizontal, (X1 + X2) / 2, 寸法Yi, 10, FontHeight)
        With MyShape
            With .TextFrame
                With .Characters
                    .Text = Format(X, "0.000")
                    With .Font
                        .Size = FontHeight
                        .name = "ＭＳ 明朝"
                    End With
                End With
    '            .HorizontalAlignment = xlHAlignCenter
                .VerticalAlignment = xlVAlignBottom
                .AutoSize = True
            End With
            .Top = 寸法Yi - .Height
            .Left = .Left - .Width / 2
            .Line.Visible = msoFalse
            .Fill.Visible = msoFalse
        End With
        tx.Add MyShape
    Next i
    
    '重なった支点寸法値をずらす
    For i = 2 To tx.Count
        Set MyShape = tx(i - 1)
        X2 = MyShape.Left
        Y = MyShape.Top
        Set MyShape = tx(i)
        X1 = MyShape.Left + MyShape.Width
        If X1 > X2 Then
            If MyShape.Top >= Y Then
                MyShape.Top = MyShape.Top + MyShape.Height
            End If
        End If
    Next i
    
    Set targetSheet = Nothing
    Set d = Nothing
    Set MyShape = Nothing
    Set tx = Nothing
    Exit Sub
    
errorHandler:
    Set targetSheet = Nothing
    Set d = Nothing
    Set MyShape = Nothing
    Set tx = Nothing

End Sub

