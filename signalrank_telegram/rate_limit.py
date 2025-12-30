import time
from config import OWNER_IDS

MAX_COMMANDS_PER_MIN = 20
user_command_times = {}

def rate_limited(user_id):
    if user_id in OWNER_IDS:
        return False
    now = time.time()
    times = user_command_times.get(user_id, [])
    # Remove commands older than 60 seconds
    times = [t for t in times if now - t < 60]
    if len(times) >= MAX_COMMANDS_PER_MIN:
        return True
    times.append(now)
    user_command_times[user_id] = times
    return False
