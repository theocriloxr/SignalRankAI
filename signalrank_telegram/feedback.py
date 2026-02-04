# feedback.py
"""
User Feedback Handler for SignalRankAI Telegram Bot
Allows users to rate signals or report issues. Stores feedback for analytics and ML improvement.
"""
import threading
import time
from collections import defaultdict
from utils.async_runner import run_sync

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
        data = None
        with self.lock:
            data = dict(self.feedback)
            if not data:
                return

        try:
            from db.session import get_engine_for_event_loop, get_session
            from db.pg_features import record_bot_event
            engine = get_engine_for_event_loop()
            if engine is None:
                raise RuntimeError("DATABASE_URL not configured")

            async def _write() -> None:
                async with get_session() as session:
                    for signal_id, entries in data.items():
                        for entry in entries:
                            await record_bot_event(
                                session,
                                telegram_user_id=int(entry.get("user_id")),
                                username=None,
                                event_type="feedback",
                                meta={
                                    "signal_id": str(signal_id),
                                    "rating": entry.get("rating"),
                                    "issue": entry.get("issue"),
                                    "comment": entry.get("comment"),
                                    "ts": entry.get("timestamp"),
                                },
                            )
                    await session.commit()

            run_sync(_write())
        except Exception:
            # Keep feedback in memory for retry
            return

        self.last_flush = time.time()
        with self.lock:
            self.feedback.clear()

# Singleton instance
feedback_store = FeedbackStore()
