from app.events import EventBus


def test_emit_delivers_in_order_with_timestamp():
    bus = EventBus(clock=lambda: 42.0)
    got = []
    bus.subscribe(lambda e: got.append(("a", e["type"])))
    bus.subscribe(lambda e: got.append(("b", e["ts"])))
    ev = bus.emit("x", foo=1)
    assert got == [("a", "x"), ("b", 42.0)]
    assert ev == {"ts": 42.0, "type": "x", "foo": 1}


def test_failing_subscriber_does_not_break_emitter_or_others():
    bus = EventBus()
    got = []

    def boom(e):
        raise RuntimeError("falla")

    bus.subscribe(boom)
    bus.subscribe(got.append)
    bus.emit("x")  # no lanza
    assert [e["type"] for e in got] == ["x"]


def test_subscriber_may_emit_more_events():
    bus = EventBus()
    seen = []
    bus.subscribe(lambda e: bus.emit("segundo") if e["type"] == "primero" else None)
    bus.subscribe(lambda e: seen.append(e["type"]))
    bus.emit("primero")
    assert sorted(seen) == ["primero", "segundo"]
