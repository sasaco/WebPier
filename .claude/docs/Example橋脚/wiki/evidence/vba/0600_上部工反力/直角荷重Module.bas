Attribute VB_Name = "直角荷重Module"
Sub 車両横荷重_Click()
    
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
    With 直角荷重Sheet
        L1 = .Range("E4")
        L2 = .Range("H4")
        L3 = .Range("K4")
        L4 = .Range("E5")
        L5 = .Range("H5")
        L6 = .Range("K5")
    
        n = 1
        a1 = .Range("K7")
        a2 = .Range("K8")
        Lb = (a1 + a2) * 2
        a3 = 0 'まだ作ってない
        p = .Range("Lf集中移動荷重")
        W = 0
    End With
    '------------------------------------
    直角荷重Sheet.Range("FBFormula") = ""
    直角荷重Sheet.Range("FBValue") = 0
    直角荷重Sheet.Range("FCFormula") = ""
    直角荷重Sheet.Range("FCValue") = 0
    Dim RR() As 列車荷重Module.Reaction
    RR = 列車荷重Module.Get反力(直角荷重Sheet.Range("車両横荷重載荷図"), _
                                L1, L2, L3, L4, L5, L6, _
                                n, Lb, a1, a2, a3, p, W)
    '反力の計算式を描く
    直角荷重Sheet.Range("FBFormula") = RR(2).Formula
    直角荷重Sheet.Range("FBValue") = RR(2).Rd
    直角荷重Sheet.Range("FCFormula") = RR(3).Formula
    直角荷重Sheet.Range("FCValue") = RR(3).Rd
    
    
  


End Sub
