import os

# Keep pytest runs hermetic and avoid import-time daemon workers that can race
# with the test runner or hit live services in smoke tests.
os.environ.setdefault("SIGNALRANK_DISABLE_BACKGROUND_THREADS", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
