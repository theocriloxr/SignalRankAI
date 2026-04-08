from __future__ import annotations

from typing import Any


def tune_xgboost_params(train_func, n_trials: int = 50) -> dict[str, Any]:
    """Run Optuna tuning when available; fallback safely when unavailable."""
    try:
        import optuna
    except Exception:
        return {"enabled": False, "reason": "optuna_not_installed", "best_params": {}}

    def objective(trial):
        params = {
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 50, 600),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        }
        score = train_func(params)
        return float(score)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=max(1, int(n_trials)))
    return {
        "enabled": True,
        "best_score": float(study.best_value),
        "best_params": dict(study.best_params or {}),
        "trials": int(n_trials),
    }
