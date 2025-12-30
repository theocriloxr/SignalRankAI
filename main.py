import os
from engine.core import main_loop

if __name__ == "__main__":
    DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
    main_loop(DRY_RUN)
