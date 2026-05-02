# SignalRankAI Fix Plan

## Task: Fix NameError import issues in production logs

### Issues to Fix:
1. **Error 1**: `name 'Any' is not defined` - during engine loop start
2. **Error 2**: `name 'require_tier' is not defined` - during Telegram webhook setup

### Plan:

#### Step 1: Fix require_tier import issue
- [x] Analyze where require_tier is defined and used
- Actions:
  - commands.py line 52 defines require_tier locally
  - utils.py line 67 has another version exported in __all__
  - Need to ensure commands.py properly imports or defines require_tier BEFORE decorators use it

#### Step 2: Fix Any type error in engine
- [x] Analyze typing imports in engine modules
- Actions:
  - Check engine/core.py typing imports (line 4 shows `from typing import Any`)
  - The error occurs during import from railway_main trying to start engine loop
  - Need to ensure the import is properly accessible

### Dependent Files:
- signalrank_telegram/commands.py
- signalrank_telegram/utils.py  
- signalrank_telegram/bot.py
- engine/core.py
- railway_main.py

### Execution Steps:
1. First, fix require_tier by ensuring proper import ordering in bot.py
2. Then verify typing imports work correctly across modules

### Testing:
- Run deploy and check logs for absence of the two NameErrors
- Confirm Telegram bot webhook setup succeeds without require_tier errors
- Confirm engine loop starts properly

Status: ANALYSIS COMPLETE - Ready to implement fixes
