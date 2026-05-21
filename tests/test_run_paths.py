from pathlib import Path


def test_readme_documents_all_runnable_user_paths():
    readme = Path("README.md").read_text(encoding="utf-8")
    for expected in [
        "docker compose up --build",
        "docker build -t aerialclaw:demo .",
        "docker run --rm -p 5001:5001 aerialclaw:demo",
        "SIM_ADAPTER=mock python server.py",
        "./scripts/doctor_gazebo.sh urban_rescue x500_lidar_2d_cam",
        "./scripts/setup_px4.sh",
        "./scripts/start_sim.sh urban_rescue x500_lidar_2d_cam",
        "curl http://localhost:5001/api/status",
        "curl http://localhost:5001/api/sensor/status",
    ]:
        assert expected in readme


def test_compose_user_path_exists_and_uses_mock_adapter():
    compose = Path("compose.yml")
    assert compose.exists()
    text = compose.read_text(encoding="utf-8")
    for expected in [
        "SIM_ADAPTER: mock",
        "5001:5001",
        "aerialclaw:demo",
        "/api/status",
    ]:
        assert expected in text


def test_readme_project_tree_does_not_claim_runtime_profile_files_are_shipped():
    for path in ["README.md", "README_CN.md"]:
        text = Path(path).read_text(encoding="utf-8")
        assert "MEMORY.md / SKILLS.md" not in text
        assert "robot_profile/MEMORY.md" not in text
        assert "robot_profile/SKILLS.md" not in text
