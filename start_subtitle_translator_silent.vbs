Option Explicit

Dim shell, fso, repo, code
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repo = fso.GetParentFolderName(WScript.ScriptFullName)

shell.CurrentDirectory = repo
code = shell.Run("uv run --locked --no-dev python """ & repo & "\launcher.py""", 0, True)
If code <> 0 Then
    MsgBox "Startup failed. Check .data\launcher-error.log or use the visible launcher.", vbExclamation, "Subtitle Translator"
End If

