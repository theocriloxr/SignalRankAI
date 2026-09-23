from pathlib import Path


def test_railway_uses_cpu_only_xgboost_distribution() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    lines = {
        line.strip()
        for line in requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "xgboost-cpu==3.2.0" in lines
    assert not any(line == "xgboost" or line.startswith("xgboost>") or line.startswith("xgboost=") for line in lines)


def test_application_imports_remain_package_compatible() -> None:
    root = Path(__file__).resolve().parents[1]
    trainer = (root / "ml" / "train_model.py").read_text(encoding="utf-8")
    assert "import xgboost" in trainer or "from xgboost" in trainer
