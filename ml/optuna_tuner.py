from __future__ import annotations

from typing import Any


def tune_xgboost_params(train_func, n_trials: int = 50, *, record_trial=None, random_seed: int = 0) -> dict[str, Any]:
    """Run Optuna tuning when available; fallback safely when unavailable."""
    try:
        import optuna
    except Exception:
        return {"enabled": False, "reason": "optuna_not_installed", "best_params": {}}
    if record_trial is None:
        return {"enabled": False, "reason": "durable_research_trial_recorder_required", "best_params": {}}
    if not isinstance(n_trials, int) or not 1 <= n_trials <= 1000:
        raise ValueError("optuna_trial_budget_invalid")

    def objective(trial):
        params = {
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 50, 600),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        }
        experiment_id = record_trial("STARTED", trial.number, params, None)
        if not experiment_id:
            raise ValueError("durable_trial_id_required_before_objective")
        try:
            score = float(train_func(params))
            import math
            if not math.isfinite(score):
                raise ValueError("non_finite_optimization_score")
        except Exception:
            record_trial("FAILED", trial.number, params, {"experiment_id": experiment_id})
            raise
        record_trial("COMPLETED", trial.number, params, {"experiment_id": experiment_id, "score": score})
        return score

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=random_seed))
    study.optimize(objective, n_trials=n_trials)
    return {
        "enabled": True,
        "best_score": float(study.best_value),
        "best_params": dict(study.best_params or {}),
        "trials": int(n_trials),
        "random_seed": random_seed,
        "production_activation_allowed": False,
    }
