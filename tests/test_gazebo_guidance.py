import subprocess
from pathlib import Path


def test_gazebo_guidance_scripts_are_present_and_syntax_valid():
    scripts = [
        Path("scripts/doctor_gazebo.sh"),
        Path("scripts/setup_px4.sh"),
        Path("scripts/start_sim.sh"),
    ]
    for script in scripts:
        assert script.exists(), f"missing {script}"
        assert script.stat().st_mode & 0o111, f"{script} should be executable"
        result = subprocess.run(
            ["bash", "-n", str(script)],
            check=False,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr


def test_gazebo_doctor_mentions_actionable_review_path():
    text = Path("scripts/doctor_gazebo.sh").read_text(encoding="utf-8")
    for expected in [
        "./scripts/setup_px4.sh",
        "./scripts/start_sim.sh",
        "SIM_ADAPTER=px4",
        "/api/sensor/status",
        "--live",
    ]:
        assert expected in text
