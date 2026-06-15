import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_uses_single_opencv_distribution():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    dependencies = pyproject["project"]["dependencies"]

    assert any(dep.startswith("opencv-python") for dep in dependencies)
    assert not any(dep.startswith("opencv-python-headless") for dep in dependencies)
