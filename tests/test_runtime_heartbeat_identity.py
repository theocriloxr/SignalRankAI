from datetime import datetime, timezone

import pytest

from core.redis_state import state
from engine.admin_pulse import _shadow_tracker_health


@pytest.mark.parametrize(
    'reported_sha, expected_sha, matches',
    [('a' * 40, 'a' * 40, True), ('b' * 40, 'a' * 40, False),
     (None, 'a' * 40, False), ('', 'a' * 40, False), (None, '', True)],
)
def test_shadow_readiness_rejects_previous_or_unidentified_release(monkeypatch, reported_sha, expected_sha, matches):
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA', expected_sha)
    monkeypatch.delenv('GIT_COMMIT_SHA', raising=False)
    heartbeat = {'status': 'healthy', 'heartbeat_at': datetime.now(timezone.utc).isoformat(),
                 'interval_seconds': 60, 'git_sha': reported_sha}
    monkeypatch.setattr(state, 'get_sync', lambda key: heartbeat.copy())
    health = _shadow_tracker_health()
    assert health['release_match'] is matches
    assert health['proven'] is matches


def test_git_commit_fallback_also_requires_matching_worker(monkeypatch):
    monkeypatch.delenv('RAILWAY_GIT_COMMIT_SHA', raising=False)
    monkeypatch.setenv('GIT_COMMIT_SHA', 'a' * 40)
    heartbeat = {'status': 'healthy', 'heartbeat_at': datetime.now(timezone.utc).isoformat(), 'git_sha': 'b' * 40}
    monkeypatch.setattr(state, 'get_sync', lambda key: heartbeat.copy())
    assert _shadow_tracker_health()['proven'] is False
