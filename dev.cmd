@echo off
rem Start API (:8000) and web (:5173) with one command.
rem Bypass is used because local .ps1 files are not signed on this machine.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1" %*
