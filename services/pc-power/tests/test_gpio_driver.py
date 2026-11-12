from app.relay import GpioDriver


class FakeLgpio:
    SET_BIAS_DISABLE = 32

    def __init__(self):
        self.calls = []

    def gpiochip_open(self, chip):
        self.calls.append(("open", chip))
        return 7

    def gpiochip_close(self, h):
        self.calls.append(("chip_close", h))

    def gpio_free(self, h, pin):
        self.calls.append(("free", pin))

    def gpio_claim_input(self, h, pin, flags=0):
        self.calls.append(("input", pin, flags))

    def gpio_claim_output(self, h, pin, flags=0, level=0):
        self.calls.append(("output", pin, level))


def calls(fake, since=0):
    return [c for c in fake.calls[since:] if c[0] in ("input", "output")]


def test_active_low_rest_is_input_not_driven_high():
    fake = FakeLgpio()
    drv = GpioDriver(23, active_high=False, lgpio_module=fake)
    assert calls(fake) == [("input", 23, 32)]  # alta impedancia, sin sesgo interno
    n = len(fake.calls)
    drv.on()
    assert calls(fake, n) == [("output", 23, 0)]  # cerrar = salida en bajo
    n = len(fake.calls)
    drv.off()
    assert calls(fake, n) == [("input", 23, 32)]  # abrir = soltar el pin
    assert not any(c[0] == "output" and c[2] == 1 for c in fake.calls)  # nunca se maneja en alto


def test_active_low_never_closes_at_startup():
    fake = FakeLgpio()
    GpioDriver(23, active_high=False, lgpio_module=fake)
    assert not any(c[0] == "output" for c in fake.calls)


def test_active_high_module_uses_push_pull():
    fake = FakeLgpio()
    drv = GpioDriver(23, active_high=True, lgpio_module=fake)
    assert calls(fake) == [("output", 23, 0)]
    n = len(fake.calls)
    drv.on()
    assert calls(fake, n) == [("output", 23, 1)]
    n = len(fake.calls)
    drv.off()
    assert calls(fake, n) == [("output", 23, 0)]


def test_close_leaves_relay_open_and_releases():
    fake = FakeLgpio()
    drv = GpioDriver(23, active_high=False, lgpio_module=fake)
    drv.on()
    n = len(fake.calls)
    drv.close()
    tail = fake.calls[n:]
    assert ("input", 23, 32) in tail  # abierto
    assert tail[-1] == ("chip_close", 7)


def test_free_errors_are_ignored():
    fake = FakeLgpio()

    def boom(h, pin):
        raise RuntimeError("not claimed")

    fake.gpio_free = boom
    drv = GpioDriver(23, active_high=False, lgpio_module=fake)
    drv.on()
    drv.off()
