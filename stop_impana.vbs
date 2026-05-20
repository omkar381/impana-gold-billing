' Impana Gold — Stop Server
' Run this to cleanly shut down the billing server

Dim objShell, objWMI, processes, process
Set objShell = CreateObject("WScript.Shell")
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")

Dim killed
killed = 0

' Kill ImpanaServer instances
Set processes = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='ImpanaServer.exe'")
For Each process In processes
    process.Terminate()
    killed = killed + 1
Next

If killed > 0 Then
    MsgBox "Impana Gold has been stopped.", vbInformation, "Impana Gold"
Else
    MsgBox "Impana Gold was not running.", vbInformation, "Impana Gold"
End If

Set objShell = Nothing
Set objWMI = Nothing
