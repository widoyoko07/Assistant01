Attribute VB_Name = "TarikInbox"
Option Explicit
' Menarik baris baru dari Inbox Transaksi.tsv (ditulis bot) ke tabel _transaction di 04.record.
' Aman dijalankan berulang: ID yang sudah ditarik dicatat di sheet tersembunyi "inbox_log".
' Simpan di PERSONAL.XLSB (Module1) bersama kode ThisWorkbook di docs/pribadi_inbox_thisworkbook.txt.
' TarikInbox = manual (ada kotak pesan). Otomatis: saat file dibuka dan tiap INTERVAL selama Excel terbuka.

Private Const SHEET_NAME As String = "04.record"
Private Const TABLE_NAME As String = "_transaction"
Private Const LOG_SHEET As String = "inbox_log"
Private Const INBOX_FILE As String = "\Documents\Inbox Transaksi.tsv"
Private Const TARGET_PATTERN As String = "Doku Keluarga*"   ' nama file yang ikut otomatis
Private Const INTERVAL As String = "00:05:00"                ' jeda penarikan berkala (jj:mm:dd)
Private nextTick As Date

Public Sub TarikInbox()
    Pull ActiveWorkbook, False
End Sub

Public Function IsTarget(wb As Workbook) As Boolean
    Dim lo As ListObject
    If wb.ReadOnly Then Exit Function
    If Not (wb.Name Like TARGET_PATTERN) Then Exit Function
    On Error Resume Next
    Set lo = wb.Worksheets(SHEET_NAME).ListObjects(TABLE_NAME)
    On Error GoTo 0
    IsTarget = Not lo Is Nothing
End Function

Public Sub Pull(wb As Workbook, quiet As Boolean)
    Dim lo As ListObject, path As String, logWs As Worksheet
    Dim done As Object, r As Long, lines() As String, f() As String, i As Long, added As Long
    On Error GoTo Fail
    Set lo = wb.Worksheets(SHEET_NAME).ListObjects(TABLE_NAME)
    path = Environ("OneDriveConsumer") & INBOX_FILE
    If Dir(path) = "" Then
        If Not quiet Then MsgBox "File inbox tidak ditemukan:" & vbLf & path, vbExclamation
        Exit Sub
    End If

    Application.ScreenUpdating = False
    Set logWs = GetLogSheet(wb)
    Set done = CreateObject("Scripting.Dictionary")
    For r = 1 To logWs.Cells(logWs.Rows.Count, 1).End(xlUp).Row
        If CStr(logWs.Cells(r, 1).Value) <> "" Then done(CStr(logWs.Cells(r, 1).Value)) = True
    Next r

    lines = Split(Replace(ReadUtf8(path), vbCrLf, vbLf), vbLf)
    For i = 1 To UBound(lines)                        ' baris 0 = header
        If Len(lines(i)) > 0 Then
            f = Split(lines(i), vbTab)
            If UBound(f) >= 7 Then                    ' 8 kolom lengkap; baris setengah tertulis dilewati
                If Not done.Exists(f(0)) Then
                    AddRow lo, f
                    logWs.Cells(logWs.Cells(logWs.Rows.Count, 1).End(xlUp).Row + 1, 1).Value = f(0)
                    done(f(0)) = True
                    added = added + 1
                End If
            End If
        End If
    Next i
    Application.ScreenUpdating = True
    If Not quiet Then MsgBox added & " transaksi baru ditarik ke " & TABLE_NAME & ".", vbInformation
    Exit Sub
Fail:
    Application.ScreenUpdating = True
    If Not quiet Then MsgBox "Gagal menarik inbox: " & Err.Description, vbExclamation
End Sub

Private Sub AddRow(lo As ListObject, f() As String)
    Dim prev As Range, lr As ListRow, c As ListColumn
    Set prev = lo.ListRows(lo.ListRows.Count).Range          ' baris terakhir sebelum ditambah = sumber rumus
    Set lr = lo.ListRows.Add
    With lr.Range
        .Cells(1, lo.ListColumns("Date").Index).Value = DateSerial(CInt(Left(f(1), 4)), CInt(Mid(f(1), 6, 2)), CInt(Mid(f(1), 9, 2)))
        .Cells(1, lo.ListColumns("Account").Index).Value = f(2)
        .Cells(1, lo.ListColumns("Description").Index).Value = f(3)
        .Cells(1, lo.ListColumns("Debit (Spend)").Index).Value = Val(f(4))
        .Cells(1, lo.ListColumns("Credit (Income)").Index).Value = Val(f(5))
        .Cells(1, lo.ListColumns("Subcategory").Index).Value = f(6)
    End With
    For Each c In lo.ListColumns                              ' kolom rumus: salin dari baris sebelumnya
        Select Case c.Name
            Case "Date", "Account", "Description", "Debit (Spend)", "Credit (Income)", "Subcategory"
            Case Else
                If prev.Cells(1, c.Index).HasFormula Then CopyFormula prev.Cells(1, c.Index), lr.Range.Cells(1, c.Index)
        End Select
    Next c
    If prev.Cells(1, 1).Offset(0, -1).HasFormula Then         ' kolom B (subtotal berjalan) di luar tabel
        CopyFormula prev.Cells(1, 1).Offset(0, -1), lr.Range.Cells(1, 1).Offset(0, -1)
    End If
End Sub

' Salin rumus tanpa clipboard (clipboard Anda tidak tertimpa). Formula2 = perilaku Excel 365; fallback untuk Excel lama.
Private Sub CopyFormula(src As Range, dst As Range)
    On Error Resume Next
    CallByName dst, "Formula2R1C1", VbLet, CallByName(src, "Formula2R1C1", VbGet)
    If Err.Number <> 0 Then
        Err.Clear
        dst.FormulaR1C1 = src.FormulaR1C1
    End If
End Sub

Private Function GetLogSheet(wb As Workbook) As Worksheet
    Dim keep As Object
    On Error Resume Next
    Set GetLogSheet = wb.Worksheets(LOG_SHEET)
    On Error GoTo 0
    If GetLogSheet Is Nothing Then
        Set keep = wb.ActiveSheet
        Set GetLogSheet = wb.Worksheets.Add(After:=wb.Sheets(wb.Sheets.Count))
        GetLogSheet.Name = LOG_SHEET
        GetLogSheet.Visible = xlSheetVeryHidden
        keep.Activate
    End If
End Function

Private Function ReadUtf8(p As String) As String
    With CreateObject("ADODB.Stream")
        .Type = 2: .Charset = "utf-8": .Open
        .LoadFromFile p
        ReadUtf8 = .ReadText
        .Close
    End With
End Function

' ---- otomatis ----
Public Sub PullAllOpen()
    Dim wb As Workbook
    For Each wb In Application.Workbooks
        If IsTarget(wb) Then Pull wb, True
    Next wb
End Sub

Public Sub TimerTick()
    On Error Resume Next
    PullAllOpen
    On Error GoTo 0
    ScheduleNext
End Sub

Public Sub ScheduleNext()
    nextTick = Now + TimeValue(INTERVAL)
    Application.OnTime nextTick, "PERSONAL.XLSB!TimerTick"
End Sub

Public Sub CancelTimer()
    On Error Resume Next
    Application.OnTime nextTick, "PERSONAL.XLSB!TimerTick", , False
End Sub
