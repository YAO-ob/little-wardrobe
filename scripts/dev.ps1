param([switch]$ApiOnly, [switch]$Reload, [switch]$Lan)

# One command: API on 127.0.0.1:8000 + web on 127.0.0.1:5173
# -Lan exposes ONLY the web server (vite --host). The API stays on 127.0.0.1:
# the browser talks to vite, and vite proxies /api and /media from inside the
# dev server, so :8000 (and /docs, and every write endpoint) is never exposed.
# Paths can be overridden with EW_PYTHON / EW_NODE_DIR / EW_PNPM.
# NOTE: keep this file ASCII-only; Windows PowerShell 5.1 reads non-UTF8-BOM
# scripts as the system code page and mangles Chinese strings.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$python = $env:EW_PYTHON
if (-not $python) {
  $python = 'C:\Users\YAOob\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
}

$nodeDir = $env:EW_NODE_DIR
if (-not $nodeDir) {
  $nodeDir = 'C:\Users\YAOob\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin'
}

$pnpm = $env:EW_PNPM
if (-not $pnpm) {
  $pnpm = 'C:\Users\YAOob\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs'
}

$env:PYTHONPATH = (Join-Path $root 'backend\.pyenv') + ';' + (Join-Path $root 'backend')
$env:PATH = "$nodeDir;$env:PATH"

if (-not (Test-Path $python)) { throw "Python not found: $python (set EW_PYTHON)" }
if (-not (Test-Path (Join-Path $root 'backend\.pyenv\fastapi'))) {
  throw 'Backend deps missing. Run: python scripts\pipx.py install --target backend\.pyenv -r backend\requirements-dev.txt'
}

Write-Host 'API  -> http://127.0.0.1:8000' -ForegroundColor Cyan

# Apply migrations before starting. Without this a new migration makes every
# query fail with "no such column" and the app looks broken on startup.
$migrateArgs = @('-m', 'alembic', '-c', 'backend\alembic.ini', 'upgrade', 'head')
& $python @migrateArgs
if ($LASTEXITCODE -ne 0) { throw 'alembic upgrade failed; fix the migration before starting.' }

$uvicornArgs = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000')
if ($Reload) { $uvicornArgs += '--reload' }
$api = Start-Process -PassThru -NoNewWindow -FilePath $python `
  -ArgumentList $uvicornArgs `
  -WorkingDirectory (Join-Path $root 'backend')

try {
  if ($ApiOnly) {
    Write-Host 'API only. Ctrl+C to stop.' -ForegroundColor Cyan
    Wait-Process -Id $api.Id
  } else {
    if ($Lan) {
      Write-Host 'WEB  -> http://0.0.0.0:5173 (LAN)' -ForegroundColor Yellow
      Write-Host 'Lan mode: open http://<your-IPv4>:5173 on your phone' -ForegroundColor Yellow
      Write-Host '          (run ipconfig to find the IPv4 address)' -ForegroundColor Yellow
      Write-Host 'API stays on 127.0.0.1:8000 and is NOT exposed to the LAN.' -ForegroundColor Yellow
      Write-Host 'Same WiFi only. Restart with .\dev.cmd for local-only mode.' -ForegroundColor Yellow
      # NOTE: no double-dash separator here. pnpm 11 forwards it into the script,
      # so the separator form makes vite receive it as a flag and ignore --host
      # (verified: it still bound 5173 on 127.0.0.1). Bare "--host" works.
      & (Join-Path $nodeDir 'node.exe') $pnpm --dir (Join-Path $root 'frontend') dev --host
    } else {
      Write-Host 'WEB  -> http://127.0.0.1:5173' -ForegroundColor Cyan
      & (Join-Path $nodeDir 'node.exe') $pnpm --dir (Join-Path $root 'frontend') dev
    }
  }
} finally {
  if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}
