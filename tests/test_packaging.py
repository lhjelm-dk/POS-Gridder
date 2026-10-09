"""requirements.txt is canonical; pyproject.toml must list the same floors."""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _requirements() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {re.sub(r"\s+", "", line.split("#")[0]) for line in lines
            if line.strip() and not line.lstrip().startswith(("#", "-"))}


def test_pyproject_mirrors_requirements():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert {re.sub(r"\s+", "", d) for d in project["dependencies"]} == _requirements()
