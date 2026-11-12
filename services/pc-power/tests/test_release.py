from app.release import release
from tests.test_gpio_driver import FakeLgpio


def outputs(fake):
    return [c for c in fake.calls if c[0] == "output"]


def test_active_low_release_leaves_pin_as_input():
    fake = FakeLgpio()
    assert release({"RELAY_ACTIVE_HIGH": "false"}, fake) == 0
    assert [c[0] for c in fake.calls if c[0] in ("input", "output")] == ["input"]
    assert not any(c[0] == "chip_close" for c in fake.calls)  # el estado se conserva


def test_active_high_release_leaves_pin_low():
    fake = FakeLgpio()
    assert release({"RELAY_ACTIVE_HIGH": "true", "RELAY_GPIO": "17"}, fake) == 0
    assert outputs(fake) == [("output", 17, 0)]


def test_mock_driver_does_nothing():
    fake = FakeLgpio()
    assert release({"RELAY_DRIVER": "mock", "RELAY_ACTIVE_HIGH": "false"}, fake) == 0
    assert fake.calls == []


def test_undefined_polarity_touches_nothing():
    fake = FakeLgpio()
    assert release({}, fake) == 0
    assert fake.calls == []


def test_bad_gpio_number():
    fake = FakeLgpio()
    assert release({"RELAY_ACTIVE_HIGH": "false", "RELAY_GPIO": "x"}, fake) == 1
    assert fake.calls == []
