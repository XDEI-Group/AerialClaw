from adapters import adapter_manager
from adapters.mock_adapter import MockAdapter


def test_mock_adapter_is_registered():
    registered = {item["name"] for item in adapter_manager.list_adapters()}
    assert "mock" in registered


def test_init_unknown_adapter_fails_without_overwriting_existing_adapter():
    adapter_manager._adapter = None
    assert adapter_manager.init_adapter("mock") is True
    assert isinstance(adapter_manager.get_adapter(), MockAdapter)
    before = adapter_manager.get_adapter()

    assert adapter_manager.init_adapter("definitely_not_real") is False
    assert adapter_manager.get_adapter() is before


def test_switch_adapter_to_mock_connects():
    assert adapter_manager.switch_adapter("mock") is True
    adapter = adapter_manager.get_adapter()
    assert isinstance(adapter, MockAdapter)
    assert adapter.is_connected()
