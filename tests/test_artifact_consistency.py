import subprocess
import sys


def test_artifact_consistency_script_passes():
    result = subprocess.run(
        [sys.executable, "scripts/check_artifact.py"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "artifact consistency checks passed" in result.stdout
