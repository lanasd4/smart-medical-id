# Development server: http://127.0.0.1:8000  (frontend + API on the same origin)
$ErrorActionPreference = 'Stop'
Set-Location "$PSScriptRoot\backend"
if (-not (Test-Path .venv)) {
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
}
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
