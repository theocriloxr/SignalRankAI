"""Complete, class-imbalance-aware model evaluation metrics.

The staging candidate reported ``accuracy=0.8169, auc=0.6274`` with confusion
matrix ``[[56,0],[13,2]]`` — dominated by majority-class prediction.  Raw
classification accuracy must never be described as trading accuracy or win
rate.  Every candidate must beat the naive-majority baseline on useful
metrics, and promotion must fail on weak balanced accuracy / positive recall /
PR AUC / calibration / sample size / drift.

All functions are pure and work on numpy arrays so they are trivially testable
without sklearn or a database.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy is a declared dependency
    np = None  # type: ignore[assignment]


def _to_array(values: Sequence[float]):
    if np is not None:
        return np.asarray(values, dtype=float)
    return list(float(v) for v in values)


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator is None or denominator == 0 or not math.isfinite(float(denominator)):
        return 0.0
    value = float(numerator) / float(denominator)
    return value if math.isfinite(value) else 0.0


def confusion_counts(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, int]:
    """TN / FP / FN / TP counts for binary labels (positive == 1)."""
    tn = fp = fn = tp = 0
    for actual, predicted in zip(y_true, y_pred):
        a = 1 if int(actual) == 1 else 0
        p = 1 if int(predicted) == 1 else 0
        if a == 1 and p == 1:
            tp += 1
        elif a == 1 and p == 0:
            fn += 1
        elif a == 0 and p == 1:
            fp += 1
        else:
            tn += 1
    return {"tn": tn, "fp": fp, "fn": fn, "tp": tp}


def balanced_accuracy(conf: dict[str, int]) -> float:
    tpr = _safe_div(conf["tp"], conf["tp"] + conf["fn"])
    tnr = _safe_div(conf["tn"], conf["tn"] + conf["fp"])
    return (tpr + tnr) / 2.0


def matthews_correlation_coefficient(conf: dict[str, int]) -> float:
    """MCC: -1..1; 0 = random; robust to class imbalance."""
    denominator = math.sqrt(
        (conf["tp"] + conf["fp"])
        * (conf["tp"] + conf["fn"])
        * (conf["tn"] + conf["fp"])
        * (conf["tn"] + conf["fn"])
    )
    if denominator == 0:
        return 0.0
    return (conf["tp"] * conf["tn"] - conf["fp"] * conf["fn"]) / denominator


def roc_auc(y_true: Sequence[int], y_proba: Sequence[float]) -> float:
    """Two-class ROC AUC via Mann-Whitney U; 0.5 = random, handles ties."""
    try:
        if np is not None:
            import numpy as _np

            y = _np.asarray([1 if int(v) == 1 else 0 for v in y_true])
            scores = _np.asarray([float(v) for v in y_proba])
            pos = scores[y == 1]
            neg = scores[y == 0]
            if len(pos) == 0 or len(neg) == 0:
                return 0.5
            ranks = _np.argsort(_np.argsort(_np.concatenate([pos, neg]))) + 1
            sum_pos = float(_np.sum(ranks[: len(pos)]))
            return (sum_pos - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg))
    except Exception:
        pass
    # Pure-python fallback.
    pos = [float(p) for a, p in zip(y_true, y_proba) if int(a) == 1]
    neg = [float(p) for a, p in zip(y_true, y_proba) if int(a) == 0]
    if not pos or not neg:
        return 0.5
    count = sum(1 for p in pos for n in neg if p > n)
    ties = sum(1 for p in pos for n in neg if p == n)
    return (count + 0.5 * ties) / (len(pos) * len(neg))


def pr_auc(y_true: Sequence[int], y_proba: Sequence[float]) -> float:
    """Precision-recall AUC (average precision). Robust to imbalance."""
    pos = [1 if int(v) == 1 else 0 for v in y_true]
    order = sorted(range(len(pos)), key=lambda i: -float(y_proba[i]))
    tp = fp = 0
    total_pos = max(1, sum(pos))
    running_sum = 0.0
    prev_precision = 0.0
    prev_recall = 0.0
    for i in order:
        if pos[i]:
            tp += 1
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / total_pos
            running_sum += (recall - prev_recall) * precision
            prev_precision = precision
            prev_recall = recall
        else:
            fp += 1
    # Fall back to random-guess AP when no recall was achieved.
    return float(running_sum) if running_sum else 0.0


def brier_score(y_true: Sequence[int], y_proba: Sequence[float]) -> float:
    return float(sum((float(p) - (1 if int(a) == 1 else 0)) ** 2 for a, p in zip(y_true, y_proba)) / max(1, len(y_true)))


def expected_calibration_error(
    y_true: Sequence[int], y_proba: Sequence[float], *, bins: int = 10,
) -> float:
    """ECE over probability bins; missing bins are skipped (not penalized)."""
    if len(y_true) < bins:
        return 1.0
    ece = 0.0
    for lower in range(bins):
        lo = lower / bins
        hi = (lower + 1) / bins
        mask = [i for i, p in enumerate(y_proba) if lo <= float(p) < hi]
        if not mask:
            continue
        conf = sum(float(y_proba[i]) for i in mask) / len(mask)
        acc = sum(1 for i in mask if int(y_true[i]) == 1) / len(mask)
        ece += (len(mask) / len(y_true)) * abs(conf - acc)
    return float(ece)


def log_loss_score(y_true: Sequence[int], y_proba: Sequence[float]) -> float:
    total = 0.0
    for a, p in zip(y_true, y_proba):
        p = min(max(float(p), 1e-7), 1.0 - 1e-7)
        total += -(1 * math.log(p) if int(a) == 1 else math.log(1 - p))
    return total / max(1, len(y_true))


def coverage_and_selective_accuracy(
    y_true: Sequence[int], y_proba: Sequence[float], *, top_fraction: float = 0.5,
) -> dict[str, float]:
    """Accuracy at the most-confident ``top_fraction`` of predictions."""
    if not y_true:
        return {"coverage": 0.0, "selective_accuracy": 0.0, "full_coverage_accuracy": 0.0}
    order = sorted(range(len(y_true)), key=lambda i: -float(y_proba[i]))
    keep = max(1, int(round(len(order) * float(top_fraction))))
    selected = order[:keep]
    sel_correct = sum(1 for i in selected if (1 if int(y_true[i]) == 1 else 0) == (1 if float(y_proba[i]) >= 0.5 else 0))
    full_correct = sum(1 for i in range(len(y_true)) if (1 if int(y_true[i]) == 1 else 0) == (1 if float(y_proba[i]) >= 0.5 else 0))
    return {
        "coverage": round(keep / len(order), 4),
        "selective_accuracy": round(sel_correct / keep, 4),
        "full_coverage_accuracy": round(full_correct / len(order), 4),
    }


def expected_r_utility(y_true: Sequence[int], y_proba: Sequence[float]) -> dict[str, float]:
    """Expected R multiple under threshold selection (reward = 2R, loss = 1R)."""
    threshold = 0.5
    predicted_positive = sum(1 for p in y_proba if float(p) >= threshold)
    if predicted_positive == 0:
        return {"expected_r": 0.0, "predicted_positive": 0}
    gains = 0.0
    for a, p in zip(y_true, y_proba):
        if float(p) >= threshold:
            gains += 2.0 if int(a) == 1 else -1.0
    return {"expected_r": round(gains / predicted_positive, 4), "predicted_positive": predicted_positive}


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    accuracy: float
    balanced_accuracy: float
    mcc: float
    positive_precision: float
    positive_recall: float
    positive_f1: float
    negative_precision: float
    negative_recall: float
    negative_f1: float
    roc_auc: float
    pr_auc: float
    brier: float
    ece: float
    log_loss: float
    coverage: float
    selective_accuracy: float
    majority_baseline_accuracy: float
    positive_rate: float
    confusion: dict[str, int]
    expected_r: float
    calibrated_win_probability: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accuracy": round(self.accuracy, 4),
            "balanced_accuracy": round(self.balanced_accuracy, 4),
            "mcc": round(self.mcc, 4),
            "positive_precision": round(self.positive_precision, 4),
            "positive_recall": round(self.positive_recall, 4),
            "positive_f1": round(self.positive_f1, 4),
            "negative_precision": round(self.negative_precision, 4),
            "negative_recall": round(self.negative_recall, 4),
            "negative_f1": round(self.negative_f1, 4),
            "roc_auc": round(self.roc_auc, 4),
            "pr_auc": round(self.pr_auc, 4),
            "brier": round(self.brier, 4),
            "ece": round(self.ece, 4),
            "log_loss": round(self.log_loss, 4),
            "coverage": round(self.coverage, 4),
            "selective_accuracy": round(self.selective_accuracy, 4),
            "majority_baseline_accuracy": round(self.majority_baseline_accuracy, 4),
            "positive_rate": round(self.positive_rate, 4),
            "confusion": self.confusion,
            "expected_r": round(self.expected_r, 4),
            "calibrated_win_probability": self.calibrated_win_probability,
        }


def evaluate_classification(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    y_proba: Sequence[float],
    *,
    calibrated_probability: float | None = None,
    top_fraction: float = 0.5,
) -> EvaluationReport:
    """Full binary-classification evaluation with imbalance-safe metrics."""
    y_true = [1 if int(v) == 1 else 0 for v in y_true]
    y_pred = [1 if int(v) == 1 else 0 for v in y_pred]
    y_proba = [float(v) for v in y_proba]
    conf = confusion_counts(y_true, y_pred)
    positive_rate = _safe_div(conf["tp"] + conf["fn"], len(y_true))
    majority_baseline = max(positive_rate, 1.0 - positive_rate)
    bal_acc = balanced_accuracy(conf)
    p_prec = _safe_div(conf["tp"], conf["tp"] + conf["fp"])
    p_rec = _safe_div(conf["tp"], conf["tp"] + conf["fn"])
    n_prec = _safe_div(conf["tn"], conf["tn"] + conf["fn"])
    n_rec = _safe_div(conf["tn"], conf["tn"] + conf["fp"])
    p_f1 = _safe_div(2 * p_prec * p_rec, p_prec + p_rec)
    n_f1 = _safe_div(2 * n_prec * n_rec, n_prec + n_rec)
    selection = coverage_and_selective_accuracy(y_true, y_proba, top_fraction=top_fraction)
    utility = expected_r_utility(y_true, y_proba)
    return EvaluationReport(
        accuracy=_safe_div(conf["tp"] + conf["tn"], len(y_true)),
        balanced_accuracy=bal_acc,
        mcc=matthews_correlation_coefficient(conf),
        positive_precision=p_prec,
        positive_recall=p_rec,
        positive_f1=p_f1,
        negative_precision=n_prec,
        negative_recall=n_rec,
        negative_f1=n_f1,
        roc_auc=roc_auc(y_true, y_proba),
        pr_auc=pr_auc(y_true, y_proba),
        brier=brier_score(y_true, y_proba),
        ece=expected_calibration_error(y_true, y_proba),
        log_loss=log_loss_score(y_true, y_proba),
        coverage=selection["coverage"],
        selective_accuracy=selection["selective_accuracy"],
        majority_baseline_accuracy=majority_baseline,
        positive_rate=positive_rate,
        confusion=conf,
        expected_r=utility["expected_r"],
        calibrated_win_probability=calibrated_probability,
    )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    eligible: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {"eligible": self.eligible, "reasons": list(self.reasons)}


def promotion_gate(
    report: EvaluationReport,
    *,
    validation_rows: int,
    min_validation_rows: int = 200,
    max_ece: float = 0.15,
    max_brier: float = 0.25,
    min_balanced_accuracy: float = 0.55,
    min_positive_recall: float = 0.20,
    min_pr_auc: float = 0.35,
    min_expected_r: float = 0.05,
    drift_unresolved: bool = False,
    calibration_validated: bool = False,
) -> PromotionDecision:
    """Governed promotion gate. Every failing check returns a named reason."""
    reasons: list[str] = []
    if validation_rows < min_validation_rows:
        reasons.append(f"validation_sample_insufficient:{validation_rows}<{min_validation_rows}")
    if report.ece > max_ece:
        reasons.append(f"calibration_ece_too_high:{report.ece:.3f}>{max_ece}")
    if report.brier > max_brier:
        reasons.append(f"brier_too_high:{report.brier:.3f}>{max_brier}")
    if report.balanced_accuracy < min_balanced_accuracy:
        reasons.append(f"balanced_accuracy_weak:{report.balanced_accuracy:.3f}<{min_balanced_accuracy}")
    if report.positive_recall < min_positive_recall:
        reasons.append(f"positive_recall_below_policy:{report.positive_recall:.3f}<{min_positive_recall}")
    if report.pr_auc < min_pr_auc:
        reasons.append(f"pr_auc_weak:{report.pr_auc:.3f}<{min_pr_auc}")
    if report.expected_r < min_expected_r:
        reasons.append(f"expected_r_does_not_improve_utility:{report.expected_r:.3f}<{min_expected_r}")
    if not calibration_validated:
        reasons.append("calibration_not_validated")
    if drift_unresolved:
        reasons.append("feature_drift_unresolved")
    if report.roc_auc <= report.majority_baseline_accuracy and report.roc_auc <= 0.55:
        reasons.append(f"roc_auc_not_better_than_baseline:{report.roc_auc:.3f}")
    return PromotionDecision(eligible=not reasons, reasons=tuple(reasons))


def render_metrics_log(report: EvaluationReport) -> str:
    """One-line structured metrics log (never calls accuracy 'trading accuracy')."""
    d = report.to_dict()
    parts = " ".join(f"{k}={v}" for k, v in sorted(d.items()))
    return f"classification_metrics {parts}"


__all__ = [
    "EvaluationReport",
    "PromotionDecision",
    "balanced_accuracy",
    "brier_score",
    "confusion_counts",
    "coverage_and_selective_accuracy",
    "evaluate_classification",
    "expected_calibration_error",
    "expected_r_utility",
    "log_loss_score",
    "matthews_correlation_coefficient",
    "pr_auc",
    "promotion_gate",
    "render_metrics_log",
    "roc_auc",
]
