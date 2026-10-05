@echo off
rem Video Factory - inicia o servidor local e abre o navegador
start "" http://localhost:8765
"D:\video_loan_shark\python\python.exe" "%~dp0server.py"
pause
