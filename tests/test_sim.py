import numpy as np

from nlab import params as P
from nlab.optimize import pick
from nlab.sim import Policy, simulate

N, DAYS = 300, 40


def test_deterministic_for_a_seed():
    a = simulate("casual", Policy("volume_first", 3), N, DAYS, 1)
    b = simulate("casual", Policy("volume_first", 3), N, DAYS, 1)
    assert np.array_equal(a.incremental, b.incremental)
    assert np.array_equal(a.sends, b.sends)


def test_no_pushes_means_no_lift_and_no_burn():
    r = simulate("minimalist", Policy("none"), N, DAYS, 2)
    assert r.sends.sum() == 0
    assert r.incremental.sum() == 0
    assert r.push_on_end.all()


def test_daily_cap_is_respected():
    for cap in (1, 2, 4):
        r = simulate("contributor", Policy("volume_first", cap), N, DAYS, 3)
        assert r.sends.max() <= cap * DAYS


def test_fatigue_aware_never_sends_more_than_volume_first_at_same_cap():
    vf = simulate("casual", Policy("volume_first", 3), N, DAYS, 4)
    fa = simulate("casual", Policy("fatigue_aware", 3, 0.3), N, DAYS, 4)
    assert fa.sends.sum() <= vf.sends.sum()


def test_disallowed_types_are_never_sent():
    allowed = tuple(k for k in P.TYPE_KEYS if k != "recommended")
    r = simulate("casual", Policy("volume_first", 5, allowed=allowed), N, DAYS, 5)
    assert r.type_sends[P.TYPE_KEYS.index("recommended")] == 0


def test_revoked_push_never_comes_back():
    r = simulate("minimalist", Policy("volume_first", 6), N, DAYS, 6)
    assert np.all(np.diff(r.daily_push_on) <= 1e-12)


def test_more_volume_burns_more_permission():
    lo = simulate("minimalist", Policy("volume_first", 1), 1000, 120, 7)
    hi = simulate("minimalist", Policy("volume_first", 6), 1000, 120, 7)
    assert hi.push_on_end.mean() < lo.push_on_end.mean()


def test_pick_breaks_ties_toward_more_permission():
    rs = [simulate("casual", Policy("fatigue_aware", c, 0.3), 400, 60, 8) for c in (2, 3, 4)]
    chosen, tied = pick(rs)
    tied_rs = [r for r in rs if r.policy.cap in tied]
    assert chosen.summary()["push_on_end"] == max(r.summary()["push_on_end"] for r in tied_rs)


def test_email_only_reaches_people_who_turned_push_off():
    r = simulate("minimalist", Policy("fatigue_aware", 5, 0.22, email=True), 800, 120, 9)
    assert r.email_sends.sum() > 0
    assert r.email_sends[r.push_on_end].sum() <= r.email_sends[~r.push_on_end].sum()
    assert (r.push_on_end | r.email_on_end).mean() >= r.push_on_end.mean()


def test_batching_does_not_raise_volume():
    a = simulate("casual", Policy("fatigue_aware", 3, 0.3), N, DAYS, 10)
    b = simulate("casual", Policy("fatigue_aware", 3, 0.3, batch=True), N, DAYS, 10)
    assert b.sends.sum() <= a.sends.sum()


def test_state_budget_sends_less_to_core_users():
    a = simulate("contributor", Policy("fatigue_aware", 4, 0.3), N, 60, 11)
    b = simulate("contributor", Policy("fatigue_aware", 4, 0.3, state_budget=True), N, 60, 11)
    assert b.sends.sum() < a.sends.sum()


def test_retention_metrics_are_shares():
    r = simulate("casual", Policy("volume_first", 3), N, DAYS, 12)
    s = r.summary()
    for k in ("dau_mau_30", "dau_mau_end", "retained_d7", "retained_d30", "active_rate"):
        assert 0 <= s[k] <= 1
    assert r.base_active.mean() <= r.active.mean()


def test_batching_respects_a_dropped_digest():
    # batching must not re-enable the digest slot when the policy excludes digests
    allowed = tuple(k for k in P.TYPE_KEYS if k != "digest")
    r = simulate("casual", Policy("fatigue_aware", 4, 0.3, allowed=allowed, batch=True), 500, 60, 3)
    assert r.type_sends[P.TYPE_KEYS.index("digest")] == 0
