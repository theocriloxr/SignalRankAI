from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("floors", [(900,30,50),(50,700,100),(50,30,900),(50,30,100)])
def test_every_configured_temporal_floor_is_preserved_when_capacity_allows(floors):
    from ml.train_model import _temporal_three_way_indices
    windows = _temporal_three_way_indices(1000, minimum_train_rows=floors[0],
        minimum_calibration_rows=floors[1], minimum_validation_rows=floors[2])
    assert all(len(window) >= floor for window, floor in zip(windows, floors))
    assert [int(index) for window in windows for index in window] == list(range(1000))


def test_temporal_split_reserves_production_validation_floor_when_capacity_allows() -> None:
    from ml.train_model import _temporal_three_way_indices

    train, calibration, validation = _temporal_three_way_indices(
        290,
        ordered_indices=list(range(290)),
        train_ratio=0.70,
        calibration_ratio=0.15,
        minimum_train_rows=50,
        minimum_calibration_rows=30,
        minimum_validation_rows=100,
    )
    assert len(validation) == 100
    assert len(calibration) >= 30
    assert len(train) >= 50
    assert len(train) + len(calibration) + len(validation) == 290
    assert set(train).isdisjoint(calibration)
    assert set(train).isdisjoint(validation)
    assert set(calibration).isdisjoint(validation)
    assert max(train) < min(calibration) < min(validation)


def test_training_passes_calibration_evidence_floors_into_temporal_split() -> None:
    source = (ROOT / "ml" / "train_model.py").read_text(encoding="utf-8")
    assert 'ML_MIN_CALIBRATION_VALIDATION_ROWS' in source
    assert 'ML_MIN_CALIBRATION_FIT_ROWS' in source
    assert 'ML_MIN_MODEL_FIT_ROWS' in source
    assert 'minimum_validation_rows=calibration_min_rows' in source
    assert 'minimum_calibration_rows=minimum_calibration_fit_rows' in source
    assert 'minimum_train_rows=minimum_model_fit_rows' in source
    assert '[ml_temporal_split]' in source
