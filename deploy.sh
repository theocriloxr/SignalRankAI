#!/bin/bash
# SignalRankAI Bot Fixes & TradingView Integration
# Quick Deployment Script
# Status: ✅ READY FOR PRODUCTION
# Date: January 4, 2026

set -e  # Exit on error

echo "═══════════════════════════════════════════════════════════════"
echo "  SignalRankAI Bot Fixes & TradingView Integration Deploy"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Validate Code
echo -e "${BLUE}Step 1: Validating code syntax...${NC}"
python -m py_compile signalrank_telegram/commands.py && echo -e "${GREEN}✅ commands.py OK${NC}" || echo -e "${RED}❌ commands.py FAILED${NC}"
python -m py_compile data/fetcher.py && echo -e "${GREEN}✅ fetcher.py OK${NC}" || echo -e "${RED}❌ fetcher.py FAILED${NC}"
python -m py_compile strategies/tradingview.py && echo -e "${GREEN}✅ tradingview.py OK${NC}" || echo -e "${RED}❌ tradingview.py FAILED${NC}"
echo ""

# Step 2: Validate Imports
echo -e "${BLUE}Step 2: Validating imports...${NC}"
python -c "from signalrank_telegram.commands import signals_command; print('✅ commands.py imports OK')" || echo "❌ Import failed"
python -c "from data.fetcher import get_tradingview_candles, discover_tradingview_symbols; print('✅ fetcher.py imports OK')" || echo "❌ Import failed"
python -c "from strategies.tradingview import get_tradingview_signals; print('✅ tradingview.py imports OK')" || echo "❌ Import failed"
echo ""

# Step 3: Check Database Connection
echo -e "${BLUE}Step 3: Checking database connection...${NC}"
python -c "
import os
from db.session import ENGINE
if ENGINE is not None:
    print('✅ Database connection OK')
else:
    print('⚠️  Database not configured (non-critical)')
" || echo "⚠️  Database check skipped"
echo ""

# Step 4: Optional TradingView Installation
echo -e "${BLUE}Step 4: TradingView Integration (Optional)${NC}"
read -p "Install tradingview-ta library? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing tradingview-ta..."
    pip install tradingview-ta
    echo -e "${GREEN}✅ tradingview-ta installed${NC}"
    
    # Test installation
    python -c "from tradingview_ta import TA_Handler; print('✅ TradingView library verified')" || echo "❌ TradingView verification failed"
else
    echo "Skipping tradingview-ta installation"
    echo "To enable TradingView later: pip install tradingview-ta"
fi
echo ""

# Step 5: Configuration
echo -e "${BLUE}Step 5: Configuration${NC}"
echo "Choose configuration:"
echo "1) Minimal (just fixes, no TradingView)"
echo "2) Enhanced (crypto only with TradingView)"
echo "3) Full (crypto + forex with TradingView)"
echo "4) Custom (manual configuration)"
echo ""
read -p "Enter choice (1-4): " CONFIG_CHOICE

case $CONFIG_CHOICE in
    1)
        echo "Configuration: Minimal"
        export TRADINGVIEW_ENABLED=false
        export CONSENSUS_MIN_SCORE=0.85
        ;;
    2)
        echo "Configuration: Enhanced"
        export TRADINGVIEW_ENABLED=true
        export TRADINGVIEW_MIN_CONFIDENCE=0.40
        export TRADINGVIEW_SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT"
        export CONSENSUS_MIN_SCORE=0.85
        ;;
    3)
        echo "Configuration: Full"
        export TRADINGVIEW_ENABLED=true
        export TRADINGVIEW_MIN_CONFIDENCE=0.40
        export TRADINGVIEW_SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,EURUSD,GBPUSD,USDJPY"
        export CRYPTO_TIMEFRAMES="5m,15m,1h,4h,1d"
        export FX_TIMEFRAMES="1h,4h,1d"
        export CONSENSUS_MIN_SCORE=0.85
        ;;
    4)
        echo "Manual configuration selected"
        echo "Set environment variables manually in .env or shell"
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac
echo ""

# Step 6: Stop Current Bot
echo -e "${BLUE}Step 6: Stopping current bot...${NC}"
pkill python || echo "No Python process running"
sleep 2
echo -e "${GREEN}✅ Bot stopped${NC}"
echo ""

# Step 7: Start New Bot
echo -e "${BLUE}Step 7: Starting bot with fixes...${NC}"
python main.py &
BOT_PID=$!
echo -e "${GREEN}✅ Bot started (PID: $BOT_PID)${NC}"
echo ""

# Step 8: Testing
echo -e "${BLUE}Step 8: Waiting for bot startup (10 seconds)...${NC}"
sleep 10
echo ""

# Check if bot is running
if ps -p $BOT_PID > /dev/null; then
    echo -e "${GREEN}✅ Bot is running!${NC}"
else
    echo -e "${RED}❌ Bot failed to start${NC}"
    exit 1
fi
echo ""

# Step 9: Final Instructions
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ DEPLOYMENT COMPLETE!${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next Steps:"
echo "1. Open Telegram and test your bot:"
echo "   • Send /signals (should show ALL signals)"
echo "   • Send /outcome abc (test reference lookup)"
echo "   • Send /help (test command response)"
echo ""
echo "2. Monitor bot logs:"
echo "   tail -f logs.txt | grep -i error"
echo ""
echo "3. For TradingView configuration details:"
echo "   cat TRADINGVIEW_SETUP.md"
echo ""
echo "4. For deployment checklist:"
echo "   cat DEPLOYMENT_CHECKLIST.md"
echo ""
echo "5. To stop bot:"
echo "   kill $BOT_PID"
echo ""
echo -e "${GREEN}Happy trading! 🚀${NC}"
echo ""
