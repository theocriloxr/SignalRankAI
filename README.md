# SignalRankAI

SignalRankAI is a professional-grade, monetizable trading signal platform with tiered Telegram bot access, secure payment integration, and robust audit logging.

## Features
- **Tiered Telegram Bot**: Free, Premium, VIP, and Owner access levels
- **Centralized SignalController**: Deduplication, correlation, exposure, and kill-switch logic
- **Secure Payments**: Paystack integration with webhook verification
- **Audit Logging**: All critical actions logged to `audit.log`
- **Admin Kill-Switch**: Emergency shutdown via Telegram command
- **.env-based Secrets**: All keys and tokens loaded from environment variables

## Quick Start
1. **Setup Environment**
   - Copy `.env.example` to `.env` and fill in all required secrets
   - Ensure `.env` is in `.gitignore`
2. **Install Dependencies**
   - `pip install -r requirements.txt`
3. **Run the Bot and Engine**
   - `python -m telegram.bot` (Telegram bot)
   - `python main.py` (Signal engine)
4. **Configure Paystack Webhook**
   - Set webhook to your server endpoint as specified in `.env`
5. **Admin Controls**
   - Use `/killswitch on <reason>` and `/killswitch off` as owner for emergency shutdown

## Deployment
- Use `start.sh` for local multi-process launch
- Use `Procfile` or `railway.json` for cloud deployment
- See `deploy_checklist.txt` for full deployment and security checklist

## Security
- All secrets must be in `.env` (never hardcoded)
- Audit logs are written to `audit.log`
- Rotate secrets regularly and restrict access to sensitive files

## Contributing
Pull requests and issues are welcome. Please ensure all code is secure, auditable, and production-ready.

---
For more details, see `deploy_checklist.txt` and `.env.example`.
