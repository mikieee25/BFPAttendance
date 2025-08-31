@echo off
echo Starting BFP Sorsogon Attendance System...
echo.

cd /d "%~dp0"

:: Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo Error: Virtual environment not found!
    echo Please run: python -m venv .venv
    echo Then run: .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

:: Activate virtual environment and run the application
echo Starting Flask application...
echo Open your browser and go to: http://localhost:5000
echo.
echo Default login credentials:
echo Username: admin
echo Password: admin123
echo.
echo Press Ctrl+C to stop the server
echo.

.venv\Scripts\python.exe app.py

pause
