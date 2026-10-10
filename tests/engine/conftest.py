import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from gameplan.engine import db, identity  # noqa: E402

SECRET = "test-secret-not-for-production"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "engine.db")
    db.migrate(c)
    yield c
    c.close()


@pytest.fixture
def org(conn):
    """Two teams, three hitters, one admin and one coach scoped to the first team."""
    t1 = identity.add_team(conn, "Visalia Rawhide", "A", 516, 14, "tracking_drawn")
    t2 = identity.add_team(conn, "Reno Aces", "AAA", 2310, 11, "tracking_drawn")
    p1 = identity.add_player(conn, "Jordan Smith", "L", t1, "ORG-1")
    p2 = identity.add_player(conn, "Alex Jones", "R", t1, "ORG-2")
    p3 = identity.add_player(conn, "Sam Lee", "S", t2, "ORG-3")
    admin_id, admin_tok = identity.create_staff(conn, SECRET, "Admin", "admin")
    coach_id, coach_tok = identity.create_staff(conn, SECRET, "Coach V", "coach", [t1])
    return dict(t1=t1, t2=t2, p1=p1, p2=p2, p3=p3, admin=(admin_id, admin_tok), coach=(coach_id, coach_tok))
