"""Exercise the shipped motion engine with Node; no service/network calls."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_motion_engine():
    assert shutil.which("node"), "Node.js required for deck motion tests"
    result = subprocess.run(["node", "tests/deck_motion.test.cjs"], cwd=ROOT,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
