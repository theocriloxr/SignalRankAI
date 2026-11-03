# Steps only the owner can do (3 November 2026)

These need your accounts, your keys or a change on the server that this
assistant is not allowed to make. Each step says where to go, what to do, and
how to check it worked. Never paste a key into a chat, a file in this
repository, or a commit; the server's `sr env-set` asks for secrets with hidden
typing.

All server commands run after `ssh root@157.173.99.72`.

## 1. Stop the Telegram test message on every bot restart

The bot container still has `DEPLOYMENT_TELEGRAM_SEND_TEST=1`, so every deploy
or restart sends a test message. The worker and engine already have `0`.

```bash
sudo sr env-set DEPLOYMENT_TELEGRAM_SEND_TEST=0 bot
```

This restarts only the bot (a few seconds). Check:

```bash
docker exec signalrank-bot-1 sh -c 'echo $DEPLOYMENT_TELEGRAM_SEND_TEST'
```

It should print `0`, and the next deploy sends no test message.

## 2. Replace the rejected OpenAI key

The AI review step logs `openai_startup_probe status=FAIL reason=provider_http_401`:
the key on the server is wrong, revoked or out of credit. Until it is fixed the
engine uses its local review instead (signals are not blocked by this).

1. Sign in at <https://platform.openai.com>, open **API keys**, and create a new
   secret key for the project you pay for. Copy it once; it is shown only once.
2. Under **Billing**, make sure the account has a payment method or credit
   (a 401/429 also happens when the balance is zero).
3. On the server, enter it with hidden typing (do not put the key on the
   command line):

   ```bash
   sudo sr env-set OPENAI_API_KEY backend
   ```

   Paste the key when asked, then press Enter. This restarts the engine,
   worker, bot and analytics containers.
4. Check, about a minute later:

   ```bash
   sudo sr grep analytics "openai_startup_probe" 10m
   ```

   It should say `status=PASS`.
5. Revoke the old key in the OpenAI dashboard.

## 3. Paystack payment channels

Checkout uses Paystack. Which payment methods a customer sees, and whether live
payments are accepted at all, is set in your Paystack account, not in our code.

1. Sign in at <https://dashboard.paystack.com>.
2. **Settings → Preferences → Payment channels**: turn on the channels you want
   (for example Card, Bank transfer, USSD, Bank). Save.
3. **Compliance / Go live**: live payments only work after Paystack has approved
   your business details. If the dashboard shows outstanding items, complete them;
   until then only test mode works.
4. Make sure the server holds the **live** secret key when you take real
   payments (`sk_live_…`), entered the same hidden way:

   ```bash
   sudo sr env-set PAYSTACK_SECRET_KEY backend
   ```

   (`backend` covers the bot, worker, engine and analytics containers, which
   hold the Paystack settings; the website container has none.) If you set a
   webhook secret in Paystack, enter it the same way:
   `sudo sr env-set PAYSTACK_WEBHOOK_SECRET backend`.

5. In **Settings → API Keys & Webhooks**, set the live webhook URL to
   `https://www.signalrank.criloxsolutions.com/webhooks/paystack`, so payments
   are confirmed even when a customer closes the browser. (Checked 3 Nov: the
   route is live and rejects an unsigned empty request with 400, as it should.)
6. Check: open the Plans page on the website while signed in, start a checkout,
   and confirm the payment methods you enabled appear. Use a small real payment
   or Paystack's test mode, then confirm your plan changed in the workspace.

Public live payments stay behind your own launch decision
(`PAYMENTS_PUBLIC_ENABLED`); turning that on is your call, not a setup step.

## 4. What the assistant handles

Everything else in the open list (code, tests, data checks, deploys through the
branch) is handled in the sessions and recorded in
`docs/release/COMPLETION_EVIDENCE.md`.
