@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_AND_START_PC2.ps1"
if errorlevel 1 pause
