#!/usr/bin/env python3
"""Fix require_tier decorator by replacing line-by-line"""

file_path = r"c:\Users\sammm\Desktop\SignalRankAI\signalrank_telegram\commands.py"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the section starting at line 1283 (0-indexed: 1282)
# Replace lines 1283-1295 with new code
new_lines = [
    "\t\t\ttier = _effective_tier(user_id)\n",
    "\t\t\tif tier_rank(tier) < tier_rank(min_tier):\n",
    "\t\t\t\ttry:\n",
    "\t\t\t\t\tfrom .command_access import check_command_access\n",
    "\t\t\t\t\tcmd_name = func.__name__.replace(\"_command\", \"\").replace(\"async \", \"\").strip()\n",
    "\t\t\t\t\t_, reason = check_command_access(cmd_name, tier)\n",
    "\t\t\t\texcept Exception:\n",
    "\t\t\t\t\treason = f\"🔒 You can't access this on {str(tier).upper()} tier.\\nUse /upgrade to subscribe to unlock it.\"\n",
    "\t\t\t\tawait update.message.reply_text(reason)\n",
    "\t\t\t\treturn\n",
    "\t\t\tresult = func(update, context)\n",
    "\t\t\tif inspect.isawaitable(result):\n",
    "\t\t\t\treturn await result\n",
    "\t\t\treturn result\n",
    "\t\treturn inner\n",
    "\treturn wrapper\n",
]

# Replace lines 1283-1295 (indices 1282-1295 in 0-indexed array)
# Keep everything before line 1283 and after 1295
lines[1282:1296] = new_lines

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✓ require_tier decorator updated successfully")
