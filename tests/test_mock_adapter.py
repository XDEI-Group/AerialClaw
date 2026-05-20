from adapters.mock_adapter import MockAdapter


def test_mock_adapter_basic_flight_cycle():
    adapter = MockAdapter()
    assert adapter.connect()
    assert adapter.is_connected()

    takeoff = adapter.takeoff(altitude=12)
    assert takeoff.success
    assert adapter.is_armed()
    assert adapter.is_in_air()
    assert adapter.get_position().down == -12

    fly = adapter.fly_to_ned(10, 5, -12, speed=10)
    assert fly.success
    pos = adapter.get_position()
    assert (pos.north, pos.east, pos.down) == (10, 5, -12)

    land = adapter.land()
    assert land.success
    assert not adapter.is_armed()
    assert not adapter.is_in_air()
    assert adapter.get_position().down == 0
