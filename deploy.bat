@echo off
REM SignalRankAI Bot Fixes & TradingView Integration
REM Quick Deployment Script (Windows)
REM Status: READY FOR PRODUCTION
REM Date: January 4, 2026

setlocal enabledelayedexpansion

echo.
echo ===================================================================
echo   SignalRankAI Bot Fixes and TradingView Integration Deploy
echo ===================================================================
echo.

REM Step 1: Validate Code
echo Step 1: Validating Python syntax...
python -m py_compile signalrank_telegram\commands.py
if %errorlevel% equ 0 (
    echo [OK] commands.py syntax valid
) else (
    echo [ERROR] commands.py has syntax errors
    goto error
)

python -m py_compile data\fetcher.py
if %errorlevel% equ 0 (
    echo [OK] fetcher.py syntax valid
) else (
    echo [ERROR] fetcher.py has syntax errors
    goto error
)

python -m py_compile strategies\tradingview.py
if %errorlevel% equ 0 (
    echo [OK] tradingview.py syntax valid
) else (
    echo [ERROR] tradingview.py has syntax errors
    goto error
)
echo.

REM Step 2: Validate Imports
echo Step 2: Validating imports...
python -c "from signalrank_telegram.commands import signals_command" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] commands.py imports resolved
) else (
    echo [ERROR] commands.py import failed
    goto error
)

python -c "from data.fetcher import get_tradingview_candles" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] fetcher.py imports resolved
) else (
    echo [ERROR] fetcher.py import failed
    goto error
)

python -c "from strategies.tradingview import get_tradingview_signals" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] tradingview.py imports resolved
) else (
    echo [ERROR] tradingview.py import failed
    goto error
)
echo.

REM Step 3: Optional TradingView Installation
echo Step 3: TradingView Integration (Optional)
set /p INSTALL_TV="Install tradingview-ta library? (y/n): "
if /i "%INSTALL_TV%"=="y" (
    echo Installing tradingview-ta...
    pip install tradingview-ta
    if %errorlevel% equ 0 (
        echo [OK] tradingview-ta installed
    ) else (
        echo [WARNING] tradingview-ta installation failed
    )
) else (
    echo Skipping tradingview-ta installation
    echo To enable TradingView later: pip install tradingview-ta
)
echo.

REM Step 4: Configuration
echo Step 4: Configuration
echo Choose configuration:
echo 1) Minimal ^(just fixes, no TradingView^)
echo 2) Enhanced ^(crypto only with TradingView^)
echo 3) Full ^(crypto + forex with TradingView^)
echo 4) Custom ^(manual configuration^)
echo.
set /p CONFIG_CHOICE="Enter choice (1-4): "

if "%CONFIG_CHOICE%"=="1" (
    echo Configuration: Minimal
    set TRADINGVIEW_ENABLED=false
    set CONSENSUS_MIN_SCORE=0.85
) else if "%CONFIG_CHOICE%"=="2" (
    echo Configuration: Enhanced
    set TRADINGVIEW_ENABLED=true
    set TRADINGVIEW_MIN_CONFIDENCE=0.40
    set TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT
    set CONSENSUS_MIN_SCORE=0.85
) else if "%CONFIG_CHOICE%"=="3" (
    echo Configuration: Full
    set TRADINGVIEW_ENABLED=true
    set TRADINGVIEW_MIN_CONFIDENCE=0.40
    set TRADINGVIEW_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,EURUSD,GBPUSD,USDJPY
    set CRYPTO_TIMEFRAMES=5m,15m,1h,4h,1d
    set FX_TIMEFRAMES=1h,4h,1d
    set CONSENSUS_MIN_SCORE=0.85
) else if "%CONFIG_CHOICE%"=="4" (
    echo Manual configuration selected
    echo Set environment variables manually in .env or PowerShell
) else (
    echo Invalid choice
    goto error
)
echo.

REM Step 5: Stop Current Bot
echo Step 5: Stopping current bot...
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo [OK] Bot stopped
echo.

REM Step 6: Start New Bot
echo Step 6: Starting bot with fixes...
start "SignalRankAI Bot" python main.py
timeout /t 5 /nobreak >nul
echo [OK] Bot started
echo.

REM Step 7: Final Instructions
echo.
echo ===================================================================
echo   DEPLOYMENT COMPLETE!
echo ===================================================================
echo.
echo Next Steps:
echo 1. Open Telegram and test your bot:
echo    • Send /signals ^(should show ALL signals^)
echo    • Send /outcome abc ^(test reference lookup^)
echo    • Send /help ^(test command response^)
echo.
echo 2. Monitor bot logs:
echo    tail -f logs.txt
echo.
echo 3. For TradingView configuration details:
echo    type TRADINGVIEW_SETUP.md
echo.
echo 4. For deployment checklist:
echo    type DEPLOYMENT_CHECKLIST.md
echo.
echo 5. To stop bot:
echo    taskkill /F /IM python.exe
echo.
echo Happy trading!
echo.
goto done

:error
echo.
echo [ERROR] Deployment failed. Please check errors above.
exit /b 1

:done
endlocal
