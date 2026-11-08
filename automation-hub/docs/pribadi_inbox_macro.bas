Attribute VB_Name = "TarikInbox"
Option Explicit
' Menarik baris baru dari file inbox (ditulis bot) ke tiga tabel:
'   Inbox Transaksi.tsv -> _transaction (sheet 04.record)
'   Inbox BBM.tsv       -> _bbmmotor    (sheet BBM)
'   Inbox Listrik.tsv   -> _listrik     (sheet Listrik)
' Aman dijalankan berulang: ID yang sudah ditarik dicatat di sheet tersembunyi "inbox_log".
' Tabel yang tidak ada di sebuah file Excel, atau file inbox yang belum ada, dilewati tanpa pesan.
' Simpan di PERSONAL.XLSB (Module1) bersama kode ThisWorkbook di docs/pribadi_inbox_thisworkbook.txt.
' TarikInbox = manual (ada kotak pesan). Otomatis: saat file dibuka dan tiap INTERVAL selama Excel terbuka.

Private Const LOG_SHEET As String = "inbox_log"
Private Const INBOX_DIR As String = "\Documents\"
Private Const TARGET_PATTERN As String = "Doku Keluarga*"   ' nama file yang ikut otomatis
Private Const INTERVAL As String = "00:05:00"                ' jeda penarikan berkala (jj:mm:dd)
Private nextTick As Date

Public Sub TarikInbox()
    Pull ActiveWorkbook, False
End Sub

' Jenis 1 = transaksi, 2 = BBM motor, 3 = listrik
Private Sub KindInfo(kind As Long, fileName As String, sheetName As String, tableName As String, minCols As Long)
    Select Case kind
        Case 1: fileName = "Inbox Transaksi.tsv": sheetName = "04.record": tableName = "_transaction": minCols = 8
        Case 2: fileName = "Inbox BBM.tsv": sheetName = "BBM": tableName = "_bbmmotor": minCols = 9
        Case 3: fileName = "Inbox Listrik.tsv": sheetName = "Listrik": tableName = "_listrik": minCols = 4
    End Select
End Sub

Public Function IsTarget(wb As Workbook) As Boolean
    Dim lo As ListObject
    If wb.ReadOnly Then Exit Function
    If Not (wb.Name Like TARGET_PATTERN) Then Exit Function
    On Error Resume Next
    Set lo = wb.Worksheets("04.record").ListObjects("_transaction")
    On Error GoTo 0
    IsTarget = Not lo Is Nothing
End Function

Public Sub Pull(wb As Workbook, quiet As Boolean)
    Dim k As Long, n(1 To 3) As Long, msg As String
    On Error GoTo Fail
    Application.ScreenUpdating = False
    For k = 1 To 3
        n(k) = PullOne(wb, k, quiet)
        If n(k) < 0 Then n(k) = 0
    Next k
    Application.ScreenUpdating = True
    If Not quiet Then
        msg = n(1) & " transaksi ke _transaction, " & n(2) & " baris ke _bbmmotor, " & n(3) & " baris ke _listrik."
        MsgBox msg, vbInformation
    End If
    Exit Sub
Fail:
    Application.ScreenUpdating = True
    If Not quiet Then MsgBox "Gagal menarik inbox: " & Err.Description, vbExclamation
End Sub

' Jumlah baris yang ditambahkan, atau -1 bila dilewati (tabel/file tidak ada)
Private Function PullOne(wb As Workbook, kind As Long, quiet As Boolean) As Long
    Dim lo As ListObject, path As String, logWs As Worksheet, done As Object
    Dim r As Long, lines() As String, f() As String, i As Long
    Dim fileName As String, sheetName As String, tableName As String, minCols As Long
    PullOne = -1
    KindInfo kind, fileName, sheetName, tableName, minCols
    On Error Resume Next
    Set lo = wb.Worksheets(sheetName).ListObjects(tableName)
    On Error GoTo 0
    If lo Is Nothing Then Exit Function
    path = Environ("OneDriveConsumer") & INBOX_DIR & fileName
    If Dir(path) = "" Then
        If kind = 1 And Not quiet Then MsgBox "File inbox tidak ditemukan:" & vbLf & path, vbExclamation
        Exit Function
    End If

    PullOne = 0
    Set logWs = GetLogSheet(wb)
    Set done = CreateObject("Scripting.Dictionary")
    For r = 1 To logWs.Cells(logWs.Rows.Count, 1).End(xlUp).Row
        If CStr(logWs.Cells(r, 1).Value) <> "" Then done(CStr(logWs.Cells(r, 1).Value)) = True
    Next r

    lines = Split(Replace(ReadUtf8(path), vbCrLf, vbLf), vbLf)
    For i = 1 To UBound(lines)                        ' baris 0 = header
        If Len(lines(i)) > 0 Then
            f = Split(lines(i), vbTab)
            If UBound(f) >= minCols - 1 Then          ' kolom lengkap; baris setengah tertulis dilewati
                If Not done.Exists(f(0)) Then
                    AddRow lo, kind, f
                    logWs.Cells(logWs.Cells(logWs.Rows.Count, 1).End(xlUp).Row + 1, 1).Value = f(0)
                    done(f(0)) = True
                    PullOne = PullOne + 1
                End If
            End If
        End If
    Next i
End Function

Private Sub SetCell(lr As ListRow, lo As ListObject, colName As String, v As Variant)
    lr.Range.Cells(1, lo.ListColumns(colName).Index).Value = v
End Sub

Private Sub AddRow(lo As ListObject, kind As Long, f() As String)
    Dim prev As Range, lr As ListRow, c As ListColumn, written As String
    If lo.ListRows.Count > 0 Then Set prev = lo.ListRows(lo.ListRows.Count).Range   ' baris terakhir sebelum ditambah = sumber rumus
    Set lr = lo.ListRows.Add
    Select Case kind
        Case 1
            written = "|Date|Account|Description|Debit (Spend)|Credit (Income)|Subcategory|"
            SetCell lr, lo, "Date", DateSerial(CInt(Left(f(1), 4)), CInt(Mid(f(1), 6, 2)), CInt(Mid(f(1), 9, 2)))
            SetCell lr, lo, "Account", f(2)
            SetCell lr, lo, "Description", f(3)
            SetCell lr, lo, "Debit (Spend)", Val(f(4))
            SetCell lr, lo, "Credit (Income)", Val(f(5))
            SetCell lr, lo, "Subcategory", f(6)
        Case 2
            written = "|TANGGAL|SUB KATEGORI|UANG KELUAR|POSISI KAS|KETERANGAN|LITER|HARSAT|KM|"
            SetCell lr, lo, "TANGGAL", DateSerial(CInt(Left(f(1), 4)), CInt(Mid(f(1), 6, 2)), CInt(Mid(f(1), 9, 2)))
            SetCell lr, lo, "SUB KATEGORI", f(2)
            SetCell lr, lo, "UANG KELUAR", Val(f(3))
            SetCell lr, lo, "POSISI KAS", f(4)
            SetCell lr, lo, "KETERANGAN", f(5)
            SetCell lr, lo, "LITER", Val(f(6))
            SetCell lr, lo, "HARSAT", Val(f(7))
            SetCell lr, lo, "KM", Val(f(8))
        Case 3
            written = "|Waktu|kWH Topup|kWH Sisa|"
            SetCell lr, lo, "Waktu", DateSerial(CInt(Left(f(1), 4)), CInt(Mid(f(1), 6, 2)), CInt(Mid(f(1), 9, 2))) _
                + TimeSerial(CInt(Mid(f(1), 12, 2)), CInt(Mid(f(1), 15, 2)), 0)
            If Len(f(2)) > 0 Then SetCell lr, lo, "kWH Topup", Val(f(2))   ' kosong = bukan isi ulang
            SetCell lr, lo, "kWH Sisa", Val(f(3))
    End Select
    If prev Is Nothing Then Exit Sub
    For Each c In lo.ListColumns                              ' kolom rumus: salin dari baris sebelumnya
        If InStr(written, "|" & c.Name & "|") = 0 Then
            If prev.Cells(1, c.Index).HasFormula Then CopyFormula prev.Cells(1, c.Index), lr.Range.Cells(1, c.Index)
        End If
    Next c
    If kind = 1 Then
        If prev.Cells(1, 1).Offset(0, -1).HasFormula Then     ' kolom B (subtotal berjalan) di luar tabel
            CopyFormula prev.Cells(1, 1).Offset(0, -1), lr.Range.Cells(1, 1).Offset(0, -1)
        End If
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
