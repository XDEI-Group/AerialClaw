import importlib


def test_server_imports_and_exposes_flask_app():
    server = importlib.import_module("server")
    assert server.app is not None
    assert server.socketio is not None


def test_status_endpoint_responds_with_system_state():
    server = importlib.import_module("server")
    client = server.app.test_client()
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert "initialized" in payload
    assert "mode" in payload
