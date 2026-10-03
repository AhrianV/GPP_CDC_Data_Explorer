$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectPath
$pythonExe = "$env:USERPROFILE\.venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}
Start-Process -FilePath $pythonExe -ArgumentList "wsgi.py" -WindowStyle Hidden
