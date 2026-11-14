# Production-style server (Waitress, multi-threaded) on http://0.0.0.0:8000
# Put HTTPS in front of it (IIS / Caddy / nginx) — service workers and push notifications require HTTPS
# on any address other than localhost.
$ErrorActionPreference = 'Stop'
Set-Location "$PSScriptRoot\backend"
if (-not $env:DJANGO_SECRET_KEY) { throw 'Set DJANGO_SECRET_KEY (see ..\.env.example)' }
$env:DJANGO_DEBUG = '0'
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py collectstatic --noinput
.venv\Scripts\waitress-serve.exe --listen=0.0.0.0:8000 --threads=8 --connection-limit=500 core.wsgi:application
