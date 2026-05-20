import subprocess
import sys


def test_repository_consistency_script_passes():
    result = subprocess.run(
        [sys.executable, "scripts/check_repository.py"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "repository consistency checks passed" in result.stdout
