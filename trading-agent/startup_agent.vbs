Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run chr(34) & currentDir & "\start_agent.bat" & Chr(34), 0
Set fso = Nothing
Set WshShell = Nothing
