#!/usr/bin/env python3
"""Quick script to fix require_tier decorator"""

file_path = r"c:\Users\sammm\Desktop\SignalRankAI\signalrank_telegram\commands.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the tier check section (using tabs as in the file)
old_section = '''\t\t\ttier = _effective_tier(user_id)
\t\t\tif tier_rank(tier) < tier_rank(min_tier):
\t\t\t\tawait update.message.reply_text(
\t\t\t\t\tf"🔒 You can't access this on {str(tier).upper()} tier.\\n"
\t\t\t\t\t"Use /upgrade to subscribe to unlock it."
\t\t\t\t)
\t\t\t\treturn
\t\t\tresult = func(update, context)
\t\t\tif inspect.isawaitable(result):
\t\t\t\treturn await result
\t\t\treturn result
\t\treturn inner
\treturn wrapper'''

new_section = '''\t\t\ttier = _effective_tier(user_id)
\t\t\tif tier_rank(tier) < tier_rank(min_tier):
\t\t\t\ttry:
\t\t\t\t\tfrom .command_access import check_command_access
\t\t\t\t\tcmd_name = func.__name__.replace("_command", "").replace("async ", "").strip()
\t\t\t\t\t_, reason = check_command_access(cmd_name, tier)
\t\t\t\texcept Exception:
\t\t\t\t\treason = f"🔒 You can't access this on {str(tier).upper()} tier.\\nUse /upgrade to subscribe to unlock it."
\t\t\t\tawait update.message.reply_text(reason)
\t\t\t\treturn
\t\t\tresult = func(update, context)
\t\t\tif inspect.isawaitable(result):
\t\t\t\treturn await result
\t\t\treturn result
\t\treturn inner
\treturn wrapper'''

if old_section in content:
    print("Found old section, replacing...")
    content = content.replace(old_section, new_section)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ require_tier decorator updated successfully")
else:
    print("Old section not found, checking individual lines...")
    lines = content.split('\n')
    for i, line in enumerate(lines[1280:1300], start=1280):
        print(f"{i}: {repr(line)}")
