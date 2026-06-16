# TODO: Rate Limiting for Gemini Audits & Signal Commands Fix

## Task 1: Rate Limiting for Gemini Audits
- [ ] Add daily rate limit for Gemini audit commands
- [ ] Standard users: 2 per day
- [ ] Premium users: Unlimited
- [ ] Track in Redis with daily key
- [ ] Add check in gemini_audit_command and related commands

## Task 2: Register All Commands in bot.py
- [ ] Verify all gemini commands are registered
- [ ] Verify /signal and /signals commands work

## Task 3: Fix/Improve Signal Commands
- [ ] Add outcome status display to /signals output
- [ ] Add better error handling
- [ ] Verify status tracking works
