Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
Set ws = CreateObject("Wscript.Shell")
ws.CurrentDirectory = root & "\backend"
cmd = """" & root & "\backend\venv\Scripts\pythonw.exe"" ""desktop.py"""
ws.Run cmd, 0, False
