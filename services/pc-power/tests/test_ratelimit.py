from app.ratelimit import AttemptLimiter, client_ip


class Clk:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def lim():
    c = Clk()
    return AttemptLimiter(clock=c), c


def test_ip_blocked_after_5_failures_not_before():
    l, c = lim()
    for i in range(4):
        assert l.record_failure("1.1.1.1") is False
        assert not l.blocked("1.1.1.1")
    assert l.record_failure("1.1.1.1") is True  # el 5.º cruza el umbral
    assert l.blocked("1.1.1.1")
    assert not l.blocked("2.2.2.2")  # otras IPs no se ven afectadas


def test_threshold_crossing_reported_once():
    l, c = lim()
    results = [l.record_failure("1.1.1.1") for _ in range(7)]
    assert results.count(True) == 1


def test_unblocks_after_15_minutes_since_last_failure():
    l, c = lim()
    for i in range(5):
        c.t = i
        l.record_failure("1.1.1.1")
    c.t = 899  # los 5 fallos siguen dentro de los últimos 15 min
    assert l.blocked("1.1.1.1")
    c.t = 900.1  # caduca el primero: quedan 4
    assert not l.blocked("1.1.1.1")
    c.t = 4 + 900.1  # y con 15 min desde el último, no queda ninguno
    assert not l.blocked("1.1.1.1")
    assert l.record_failure("1.1.1.1") is False


def test_sliding_window_partial_expiry():
    l, c = lim()
    for i in range(5):
        c.t = i
        l.record_failure("1.1.1.1")
    c.t = 900.5  # solo ha caducado el primero: quedan 4
    assert not l.blocked("1.1.1.1")


def test_global_block_after_30_failures_from_many_ips():
    l, c = lim()
    for i in range(29):
        l.record_failure(f"10.0.0.{i}")
    assert not l.global_blocked()
    assert not l.blocked("10.9.9.9")
    l.record_failure("10.0.1.1")
    assert l.global_blocked()
    assert l.blocked("10.9.9.9")  # cualquier origen, aunque sea nuevo


def test_global_unblocks_after_one_hour():
    l, c = lim()
    for i in range(30):
        l.record_failure(f"10.0.0.{i}")
    c.t = 3599
    assert l.global_blocked()
    c.t = 3601
    assert not l.global_blocked()


def test_each_ip_counted_separately():
    l, c = lim()
    for _ in range(4):
        l.record_failure("1.1.1.1")
        l.record_failure("2.2.2.2")
    assert not l.blocked("1.1.1.1") and not l.blocked("2.2.2.2")


def test_empty_entries_are_cleaned():
    l, c = lim()
    l.record_failure("1.1.1.1")
    c.t = 10_000
    assert not l.ip_blocked("1.1.1.1")
    assert "1.1.1.1" not in l._by_ip


# ---- IP real tras el proxy ---------------------------------------------------
def test_xff_trusted_only_from_local_peer():
    assert client_ip("127.0.0.1", "203.0.113.7") == "203.0.113.7"
    assert client_ip("::1", "203.0.113.7, 10.0.0.1") == "203.0.113.7"


def test_xff_ignored_from_non_local_peer():
    assert client_ip("198.51.100.2", "203.0.113.7") == "198.51.100.2"
    assert client_ip("192.168.10.5", "1.2.3.4") == "192.168.10.5"


def test_xff_garbage_falls_back_to_peer():
    assert client_ip("127.0.0.1", "no-es-ip") == "127.0.0.1"
    assert client_ip("127.0.0.1", None) == "127.0.0.1"
    assert client_ip(None, None) == "unknown"
