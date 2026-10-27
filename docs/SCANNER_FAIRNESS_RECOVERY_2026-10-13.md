# Scanner fairness recovery

The scanner previously truncated the full eligible list to `ENGINE_UNIVERSE_CAP`
before passing it to its persistent queue. Repeated wakeups therefore scanned
the same prefix. Coverage anchors could also replace a popped tail member
without returning that member to pending work.

The scheduler now queues the full observed eligible universe and uses
`ENGINE_UNIVERSE_CAP` only to bound each cycle's work. Rotating class anchors
retain their coverage slots; displaced members return to the front in their
original order. Completed, disabled and already queued members cannot be
reintroduced by this return operation. Runtime class, market-hours, blacklist,
provider, expectancy and risk qualification still apply.

Prospective observations use format 2 and policy `engine-class-round-robin-v2`.
The `scheduled` stage records the full eligible queue input and the policy
explicitly records `universe_cap_scope: per_cycle_work`. Format 1 observations
retain their original prefix semantics, payloads and hashes on restoration.
Historical observations are never relabeled as evidence of the new policy.

Behavioral regressions exercise the actual engine scheduling function: 45
members across five classes with a five-slot work budget, rotating anchors,
disabled members, a budget smaller than the class count, and complete rounds.
The skewed-class scenario must scan all 41 crypto members while preserving
four other class slots, without advancing past unfinished work.

This fixes scanner selection, not end-to-end signal delivery. The database
discovery query still has a sorted result limit, and provider failures,
expectancy availability and risk rejections remain separate acceptance gaps.
Do not force a signal or weaken those checks to demonstrate delivery. The
new scheduler requires application release acceptance before production use;
the independently verified UI candidate remains pinned for its own soak.
