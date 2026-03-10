import threading
import time

class ReadinessFlag:
    def __init__(self):
        self.lock = threading.Lock()
        self.ready = False
        self.error = None

    def set_ready(self, ok: bool, error: str = None):
        with self.lock:
            self.ready = ok
            self.error = error

    def is_ready(self) -> bool:
        with self.lock:
            return self.ready

    def get_status(self) -> dict:
        with self.lock:
            return {'ready': self.ready, 'error': self.error}

    def wait_forever(self, poll_seconds=1):
        while True:
            with self.lock:
                if self.ready:
                    break
            time.sleep(poll_seconds)

readiness_flag = ReadinessFlag()