"""Synthetic operator UI evidence in an explicitly owned local database."""
import asyncio
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.engine import make_url
from db.session import get_session, dispose_engine_for_event_loop
from services.platform.identity import create_email_account
from engine.adaptive.dataset import AdaptiveDatasetRow
from engine.adaptive.walk_forward import walk_forward_evaluate
from engine.adaptive.statistics import return_diagnostics
from engine.adaptive.integrity import audit_adaptive_dataset
from engine.adaptive.research_ledger import register_hypothesis, start_experiment, complete_experiment

async def main():
    parsed = make_url(os.environ['DATABASE_URL'])
    if (os.environ.get('APP_ENV') != 'test' or parsed.get_backend_name() != 'postgresql'
            or parsed.host not in {'127.0.0.1', 'localhost'}
            or not (parsed.database or '').startswith('signalrank_research_browser_test_')):
        raise RuntimeError('seed requires an explicitly owned local browser-test database')
    try:
        async with get_session() as session:
            for tier in ('admin', 'free'):
                uid = await create_email_account(session, email=f'research-{tier}@example.test',
                    password='LocalDrill-Only-20261003!', display_name=f'Synthetic research {tier}')
                await session.execute(text("UPDATE users SET email_verified_at=NOW(),accepted_terms=TRUE,"
                    "terms_accepted_at=NOW(),tier=:tier,premium_until=NOW()+INTERVAL '1 day' WHERE id=:uid"), {'tier': tier, 'uid': uid})
            await session.execute(text("INSERT INTO adaptive_dataset_versions(dataset_version,content_hash) VALUES('synthetic-ui-dataset',:hash)"), {'hash': '1' * 64})
            await session.execute(text("INSERT INTO adaptive_feature_versions(feature_version,content_hash) VALUES('synthetic-ui-features',:hash)"), {'hash': '2' * 64})
            hypothesis = await register_hypothesis(session, trial_family='synthetic_ui_fixture',
                spec={'description': 'Synthetic UI fixture <img src=x onerror=window.injected=true>',
                      'mechanism_status': 'mechanism_unproven'}, code_commit='synthetic-ui-fixture', created_by='local_browser_test')
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            rows = [AdaptiveDatasetRow(str(uuid4()), start+timedelta(hours=i), 'BTCUSDT', 'crypto_spot', '1h',
                'trend', 'trend', 'long', 0.4 if i % 5 else -0.5, 'shadow',
                outcome_known_at=start+timedelta(hours=i, minutes=30)) for i in range(160)]
            wfo = walk_forward_evaluate(rows, family_weights={'trend': 1}, cost_r=0.01)
            base = {'parameter_set': {'weight': 1}, 'dataset_version': 'synthetic-ui-dataset',
                'feature_version': 'synthetic-ui-features', 'label_version': 'synthetic-R',
                'execution_model_version': 'synthetic_UI_no_fills', 'risk_model_version': 'synthetic_UI',
                'code_commit': 'synthetic-ui-fixture', 'random_seed': 0, 'asset_scope': ['BTCUSDT'],
                'timeframe_scope': ['1h'], 'regime_scope': ['trend'], 'evidence_category': 'shadow'}
            experiment = await start_experiment(session, hypothesis_id=hypothesis, strategy_id='Synthetic strategy',
                strategy_version='1', specification=base)
            await complete_experiment(session, experiment, {'walk_forward': wfo.to_dict(),
                'integrity': audit_adaptive_dataset(rows, wfo), 'return_diagnostics': return_diagnostics([row.r_multiple for row in rows]),
                'evidence_category': 'shadow', 'multiple_testing': {'status': 'UNVERIFIED'}, 'promotion_eligible': False})
            failed = await start_experiment(session, hypothesis_id=hypothesis, strategy_id='Synthetic failed variant',
                strategy_version='1', specification={**base, 'parameter_set': {'weight': 2}})
            await complete_experiment(session, failed, {'failure_reason': 'synthetic_objective_failure', 'promotion_eligible': False}, status='FAILED')
            await session.commit()
    finally:
        await dispose_engine_for_event_loop()

if __name__ == "__main__":
    asyncio.run(main())
