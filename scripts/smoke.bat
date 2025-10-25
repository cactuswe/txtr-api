@echo off
REM Smoke test script for URL Insights Mini

echo Testing health endpoint...
curl -s http://localhost:8000/v1/health
if %ERRORLEVEL% NEQ 0 (
    echo Health check failed!
    exit /b 1
)

echo.
echo Testing parse endpoint...
curl -s http://localhost:8000/v1/parse ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://en.wikipedia.org/wiki/Artificial_intelligence\"}"
if %ERRORLEVEL% NEQ 0 (
    echo Parse test failed!
    exit /b 1
)

echo.
echo All tests passed!
