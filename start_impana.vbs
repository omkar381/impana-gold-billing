' Impana Gold — Silent Launcher
' Double-click this file to start the standalone backend

Dim objShell, objFSO
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Find install directory (where this script lives)
Dim scriptDir
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

Dim serverExe
serverExe = scriptDir & "\ImpanaServer.exe"

If Not objFSO.FileExists(serverExe) Then
    MsgBox "ImpanaServer.exe not found." & vbCrLf & _
           "Please reinstall Impana Gold.", vbCritical, "Impana Gold"
    WScript.Quit
End If

' Check if already running
Dim alreadyRunning
alreadyRunning = False
Dim objWMI, processes, process
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
Set processes = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='ImpanaServer.exe'")
For Each process In processes
    alreadyRunning = True
Next

If Not alreadyRunning Then
    objShell.CurrentDirectory = scriptDir
    ' Set production environment
    Dim envCmd
    envCmd = "cmd /c set FLASK_ENV=production&& """ & serverExe & """"
    objShell.Run envCmd, 0, False   ' 0 = hidden window, False = don't wait
    
    ' Wait for Flask to start (3 seconds)
    WScript.Sleep 3000
End If

' Open app in default browser
objShell.Run "http://127.0.0.1:5000", 1, False

Set objShell = Nothing
Set objFSO = Nothing
