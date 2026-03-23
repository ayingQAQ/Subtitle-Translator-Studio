Option Explicit

Dim shell, fso, repo, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repo = fso.GetParentFolderName(WScript.ScriptFullName)

cmd = "cmd /c cd /d """ & repo & """ " & _
      "&& if not exist "".env"" if exist "".env.example"" copy /y "".env.example"" "".env"" >nul " & _
      "&& if not exist "".venv\Scripts\python.exe"" uv sync --all-groups " & _
      "&& uv run streamlit run app.py"

' Run hidden (0), do not wait for completion (False)
shell.Run cmd, 0, False

' Open browser after a short delay
WScript.Sleep 1500
shell.Run "http://localhost:8501", 1, False

