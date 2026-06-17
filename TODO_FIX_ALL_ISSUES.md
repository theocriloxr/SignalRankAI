# TODO: Fix All Issues from Railway Diagnostic Report

## Issues to Fix (Priority Order)

### 1. Railway Log Misclassification (INFO as ERROR)
- Status: PENDING
- Files: main.py, railway_main.py
- Task: Configure uvicorn to use log_config=None and route all logs to stdout

### 2. Binance Pair Discovery Broken
- Status: PENDING  
- Files: data/pair_discovery.py
- Task: Make CryptoCompare primary, add Bybit as alternative

### 3. Database Pool Too Small
- Status: PENDING
- Files: db/session.py
- Task: Increase pool_size to 10, max_overflow to 20

### 4. Engine Heartbeat Confirmation
- Status: PENDING
- Files: engine/core.py
- Task: Add [engine] main loop started and heartbeat logs

### 5. Background Task Monitoring
- Status: ALREADY DONE
- Notes: _log_task_failure callback already exists in railway_main.py

## Implementation Checklist
- [ ] 1. Fix Railway logging in main.py
- [ ] 2. Fix Railway logging in railway_main.py  
- [ ] 3. Update pair discovery to prefer CryptoCompare
- [ ] 4. Add Bybit pair discovery
- [ ] 5. Increase DB pool settings
- [ ] 6. Add engine startup confirmation
- [ ] 7. Test all changes locally
