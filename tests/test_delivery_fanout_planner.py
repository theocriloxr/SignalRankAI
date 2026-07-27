from delivery.fanout import delivery_shard, iter_delivery_batches


def test_fanout_is_deterministic_and_duplicate_free():
    users = [5, 1, 2, 5, 3, 4]
    first = list(iter_delivery_batches(users, shard_count=3, batch_size=2))
    second = list(iter_delivery_batches(reversed(users), shard_count=3, batch_size=2))
    first_users = sorted(uid for batch in first for uid in batch.user_ids)
    second_users = sorted(uid for batch in second for uid in batch.user_ids)
    assert first_users == [1, 2, 3, 4, 5]
    assert second_users == first_users
    assert [batch.idempotency_key for batch in first] == [batch.idempotency_key for batch in second]


def test_100k_user_plan_has_exact_coverage():
    batches = list(iter_delivery_batches(range(1, 100_001), shard_count=32, batch_size=100))
    users = [uid for batch in batches for uid in batch.user_ids]
    assert len(users) == 100_000
    assert len(set(users)) == 100_000
    assert all(len(batch.user_ids) <= 100 for batch in batches)
    assert all(0 <= delivery_shard(uid, 32) < 32 for uid in users[:100])
