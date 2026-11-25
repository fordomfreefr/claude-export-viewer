@echo off
rem Double-click (Windows): installs CEV from this folder, makes its icon and opens the Library.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 claude-export-viewer.py --installer) else (python claude-export-viewer.py --installer)
if errorlevel 1 pause
