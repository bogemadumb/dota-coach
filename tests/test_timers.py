from types import SimpleNamespace

import pytest

from dota_coach.timers import Timers, fmt_clock

TIMINGS = """
patch: test
schedule:
  - {id: rune, first: 120, interval: 120, lead: 10, say: "Руна в {at}, через {lead}", detail: "d {at}", priority: 2}
  - {id: stack, times: [50, 110], lead: 5, say: "Стак", category: stack}
  - {id: bounty, first: 0, interval: 180, until: 360, say: "Баунти"}
  - {id: night_only, first: 300, interval: 600, lead: 0, say: "Ночь", when: night}
  - {id: day_only, first: 300, interval: 600, lead: 0, say: "День", when: day}
relative:
  roshan_killed:
    - {id: rosh_early, after: 480, lead: 0, say: "Рошан мог появиться"}
    - {id: rosh_late, after: 660, lead: 30, say: "Рошан точно жив через {lead}", priority: 3}
"""


@pytest.fixture
def timers(tmp_path):
    path = tmp_path / "timings.yaml"
    path.write_text(TIMINGS, encoding="utf-8")
    return Timers(path)


def run(timers, start, stop, state=None):
    out = []
    for clock in range(start, stop + 1):
        out += [(clock, h) for h in timers.check(clock, state)]
    return out


def of(fired, rule_id):
    return [(c, h) for c, h in fired if h.id.startswith(rule_id)]


def test_missing_file_is_tolerated(tmp_path):
    t = Timers(tmp_path / "nope.yaml")
    assert t.schedule == [] and t.relative == {}
    assert t.check(100) == []
    assert t.mark("roshan_killed", 100) == 0


def test_periodic_fires_once_at_lead(timers):
    fired = of(run(timers, -90, 400), "rune")
    assert [c for c, _ in fired] == [110, 230, 350]
    assert len({h.id for _, h in fired}) == 3
    assert fired[0][1].say == "Руна в 2:00, через 10"
    assert fired[0][1].detail == "d 2:00"
    assert fired[0][1].source == "timers"


def test_same_clock_checked_twice_fires_once(timers):
    assert len(of([(110, h) for h in timers.check(110)], "rune")) == 1
    assert timers.check(110) == []


def test_times_rule(timers):
    fired = of(run(timers, 0, 200), "stack")
    assert [c for c, _ in fired] == [45, 105]
    assert fired[0][1].category == "stack"


def test_until_stops_periodic(timers):
    fired = of(run(timers, 0, 1000), "bounty")
    assert [c for c, _ in fired] == [0, 180, 360]


def test_clock_jump_does_not_replay_past(timers):
    assert timers.check(1000) == []
    hints = timers.check(1070)
    assert [h.id for h in hints] == ["rune@1080"]
    fresh = Timers.__new__(Timers)
    fresh.__dict__.update(timers.__dict__)
    fresh.reset()
    assert fresh.check(5000) == []


def test_clock_going_backwards_resets(timers):
    assert len(of(run(timers, 100, 120), "rune")) == 1
    assert timers.check(120) == []
    timers.check(40)
    assert len(of(run(timers, 100, 120), "rune")) == 1


def test_reset_forgets_marks_and_fired(timers):
    timers.mark("roshan_killed", 100)
    run(timers, 100, 120)
    timers.reset()
    assert timers.pending == [] and timers.fired == set() and timers.last_clock is None
    assert len(of(run(timers, 100, 120), "rune")) == 1


def test_relative_roshan_after_mark(timers):
    assert timers.mark("roshan_killed", 1000) == 2
    fired = run(timers, 1000, 1700)
    early = of(fired, "rosh_early")
    late = of(fired, "rosh_late")
    assert [c for c, _ in early] == [1480]
    assert [c for c, _ in late] == [1630]
    assert late[0][1].priority == 3
    assert late[0][1].say == "Рошан точно жив через 30"
    assert early[0][1].id != late[0][1].id


def test_no_relative_hints_without_mark(timers):
    fired = run(timers, 0, 2000)
    assert of(fired, "rosh") == []


def test_remark_replaces_previous_pending(timers):
    timers.mark("roshan_killed", 1000)
    timers.mark("roshan_killed", 1003)
    fired = run(timers, 1003, 1700)
    assert [c for c, _ in of(fired, "rosh_early")] == [1483]


def test_unknown_trigger_mark_is_noop(timers):
    assert timers.mark("tormentor", 100) == 0
    assert timers.pending == []


@pytest.mark.parametrize("daytime,expect_night,expect_day", [(False, 1, 0), (True, 0, 1), (None, 0, 0)])
def test_when_day_night(timers, daytime, expect_night, expect_day):
    state = SimpleNamespace(daytime=daytime)
    fired = run(timers, 295, 305, state)
    assert len(of(fired, "night_only")) == expect_night
    assert len(of(fired, "day_only")) == expect_day


def test_without_state_when_rules_pass(timers):
    fired = run(timers, 295, 305)
    assert len(of(fired, "night_only")) == 1 and len(of(fired, "day_only")) == 1


def test_fmt_clock():
    assert fmt_clock(-5) == "-0:05" and fmt_clock(605) == "10:05"
