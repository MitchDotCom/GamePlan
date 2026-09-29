import math

from gameplan import baseout, decision, savant
from gameplan.constants import REGISTRY, by_status, value


def test_verified_values_are_pinned():
    assert value("WOBA_SCALE_2025") == 1.257 and value("WBB_2025") == 0.693 and value("WHBP_2025") == 0.725
    assert (value("SQUARED_UP_BAT_COEF"), value("SQUARED_UP_PITCH_COEF"), value("SQUARED_UP_THRESHOLD")) == (1.23, 0.2116, 0.80)
    assert value("VAA_RELEASE_Y_FT") == 50.0 and math.isclose(value("VAA_PLATE_FRONT_Y_FT"), 17 / 12)


def test_code_uses_the_registry_not_its_own_copy():
    assert baseout.WOBA_SCALE == value("WOBA_SCALE_2025")
    assert decision.WALK_VALUE == value("WBB_2025") and decision.HBP_VALUE == value("WHBP_2025")
    assert decision.GO_DELTA == value("GO_DELTA") and decision.NO_GO_DELTA == value("NO_GO_DELTA")


def test_squared_up_uses_the_published_formula():
    hdr = "description,plate_x,plate_z,pitch_type,stand,launch_speed,bat_speed,release_speed,estimated_woba_using_speedangle\n"
    sq = savant.parse_swings(hdr + "hit_into_play,0,2.5,FF,R,100,75,90,0.4\n")[0]      # 100 / (92.25 + 19.04) = .899
    no = savant.parse_swings(hdr + "hit_into_play,0,2.5,FF,R,80,75,90,0.1\n")[0]       # 80 / 111.29 = .719
    assert sq.squared_up is True and no.squared_up is False


def test_every_entry_has_a_status_and_source():
    for name, c in REGISTRY.items():
        assert c.status in {"VERIFIED", "DERIVED", "CHOICE", "BLUEPRINT"}, name
        assert c.source, name
    assert by_status("VERIFIED")


def test_data_handling_defaults_follow_published_definitions():
    hdr = "description,events,plate_x,plate_z,pitch_type,stand,estimated_woba_using_speedangle,woba_value\n"
    rows = hdr + "foul_tip,,0,2.5,FF,R,,\nfoul_bunt,,0,2.5,FF,R,,\nhit_into_play,sac_bunt,0,2.5,FF,R,,0\nhit_into_play,single,0,2.5,FF,R,,0.9\nhit_into_play,single,0,2.5,FF,R,0.4,0.9\n"
    out = savant.parse_swings(rows)
    assert len(out) == 2 and out[0].whiff is True and out[1].xwoba == 0.4      # tip = whiff; bunts and xwOBA-less BIP dropped
    old = savant.parse_swings(rows, foul_tip_as_whiff=False, exclude_bunts=False, strict_xwoba=False)
    assert len(old) == 5 and old[0].whiff is False
