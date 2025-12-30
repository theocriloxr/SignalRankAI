SYSTEM_ACTIVE = True

def check_system():
    if not SYSTEM_ACTIVE:
        raise Exception("System halted by admin")
