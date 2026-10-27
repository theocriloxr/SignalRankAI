"""One-shot fix: repair the corrupted format_signal call in bot.py resend path."""
import re

path = "signalrank_telegram/bot.py"
content = open(path, "r", encoding="utf-8").read()

old_block = (
    "                        # Format and send\n"
    "                        display_tier = 'vip' if user_tier in ('owner', 'admin') else user_tier\n"
    "                        text = format_signal(sig_dict, display_tier=display_tier)\n"
    "                            text = format_signal(sig_dict, user_tier=user_tier, display_tier=display_tier)\n"
    "                            if not text or not str(text).strip():\n"
    "                            logger.info(\n"
    "                                f\"[resend] Skipped signal {signal_id} for user {user_id} \"\n"
    "                                f\"(tier={user_tier}): formatter returned empty text\"\n"
    "                            )\n"
    "                            continue"
)

new_block = (
    "                        # Format and send\n"
    "                        display_tier = 'vip' if user_tier in ('owner', 'admin') else user_tier\n"
    "                        text = format_signal(sig_dict, user_tier=user_tier, display_tier=display_tier)\n"
    "                        if not text or not str(text).strip():\n"
    "                            logger.info(\n"
    "                                f\"[resend] Skipped signal {signal_id} for user {user_id} \"\n"
    "                                f\"(tier={user_tier}): formatter returned empty text\"\n"
    "                            )\n"
    "                            continue"
)

if old_block in content:
    content = content.replace(old_block, new_block, 1)
    open(path, "w", encoding="utf-8").write(content)
    print("Fixed successfully.")
else:
    print("ERROR: target block not found — check indentation")
    # Show nearby context for debugging
    idx = content.find("# Format and send")
    if idx != -1:
        print("Found '# Format and send' at index", idx)
        print(repr(content[idx:idx+600]))
