from gameplan.engine import replication

M = lambda sync, err: f'litestream_sync_count{{db="/data/engine.db"}} {sync}\nlitestream_sync_error_count{{db="/data/engine.db"}} {err}\n'


def run(monkeypatch, steps):
    monkeypatch.setenv("LITESTREAM_METRICS", "127.0.0.1:9191")
    state = {"sync": None, "errors": None, "at": None}
    clock = [1000.0]
    out = []
    for dt, text in steps:
        clock[0] += dt
        out.append(replication.check(fetch=(lambda a, t=text: t) if not isinstance(text, Exception) else (lambda a, t=text: (_ for _ in ()).throw(t)), now=lambda: clock[0], state=state))
    return out


def test_not_configured_is_silent(monkeypatch):
    monkeypatch.delenv("LITESTREAM_METRICS", raising=False)
    assert replication.check() == []


def test_healthy_replication_passes_while_the_counter_moves(monkeypatch):
    assert run(monkeypatch, [(0, M(5, 0)), (60, M(65, 0)), (60, M(125, 0))]) == [[], [], []]


def test_a_stalled_counter_is_flagged(monkeypatch):
    got = run(monkeypatch, [(0, M(5, 0)), (60, M(5, 0))])
    assert got[0] == [] and "stopped syncing" in got[1][0]


def test_new_errors_are_flagged(monkeypatch):
    got = run(monkeypatch, [(0, M(5, 0)), (60, M(65, 3))])
    assert any("errors" in p for p in got[1])


def test_an_unreachable_litestream_is_flagged(monkeypatch):
    got = run(monkeypatch, [(0, ConnectionRefusedError())])
    assert "not running" in got[0][0]
