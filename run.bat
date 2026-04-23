@echo off
setlocal
echo Starting Privacy Reader Backend...

:: Try to free up port 8000 if it's taken
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo Port 8000 is taken by PID %%a. Cleaning up...
    taskkill /F /PID %%a >nul 2>&1
)

:: Run uvicorn
call uv run uvicorn src.backend.main:app --host 0.0.0.0 --port 8000

endlocal
