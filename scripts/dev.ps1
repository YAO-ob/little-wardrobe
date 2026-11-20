param([switch]$ApiOnly, [switch]$Reload)

# One command: API on 127.0.0.1:8000 + web on 127.0.0.1:5173
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
    Write-Host 'WEB  -> http://127.0.0.1:5173' -ForegroundColor Cyan
    & (Join-Path $nodeDir 'node.exe') $pnpm --dir (Join-Path $root 'frontend') dev
  }
} finally {
  if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}
