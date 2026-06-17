# TODO: Rate Limiting for Gemini Audits & Signal Commands Fix

## Task 1: Rate Limiting for Gemini Audits
- [ ] Add daily rate limit check for Gemini audit commands
- [ ] Standard users: 2 Gemini Audits per day
- [ ] Premium users: Unlimited Gemini Audits
- [ ] Track in Redis with daily key like "gemini_audit:{user_id}:{date}"
- [ ] Add check in gemini_audit_command handler
- [ ] Add check in gemini_analyze_command handler
- [ ] Add check in gemini_predict_command handler (if exists)

## Task 2: Verify All Commands Registered in bot.py
- [ ] gemini_command
- [ ] gemini_review_command
- [ ] gemini_analyze_command
- [ ] gemini_audit_command
- [ ] gemini_predict_command
- [ ] signals_command
- [ ] signal_command

## Task 3: Fix/Improve Signal Commands
- [ ] Add outcome status display to /signals output
- [ ] Add better error handling
- [ ] Verify status tracking works
- [ ] Display "Open" for signals without outcome
- [ ] Display "TP" or "SL" for resolved signals
