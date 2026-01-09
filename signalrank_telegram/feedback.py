# feedback.py
"""
User Feedback Handler for SignalRankAI Telegram Bot
Allows users to rate signals or report issues. Stores feedback for analytics and ML improvement.
"""
import threading
import time
from collections import defaultdict

class FeedbackStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.feedback = defaultdict(list)  # signal_id -> list of feedback dicts
        self.last_flush = time.time()

    def add_feedback(self, user_id, signal_id, rating=None, issue=None, comment=None):
        with self.lock:
            entry = {
                'user_id': user_id,
                'signal_id': signal_id,
                'rating': rating,
                'issue': issue,
                'comment': comment,
                'timestamp': time.time(),
            }
            self.feedback[signal_id].append(entry)

    def get_feedback(self, signal_id=None):
        with self.lock:
            if signal_id:
                return list(self.feedback.get(signal_id, []))
            return dict(self.feedback)

    def flush(self):
        # Placeholder: Write feedback to DB, file, or analytics system
        print("[feedback] Flushing feedback:", dict(self.feedback), flush=True)
        self.last_flush = time.time()
        with self.lock:
            self.feedback.clear()

# Singleton instance
feedback_store = FeedbackStore()
