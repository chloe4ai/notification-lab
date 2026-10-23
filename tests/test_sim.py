import json
from pathlib import Path

import numpy as np

from nlab import params as P
from nlab.optimize import ablation_policies, ladder_policies, pick
from nlab.sim import Policy, Result, simulate

N, DAYS = 300, 40
ROOT = Path(__file__).resolve().parents[1]


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
    assert chosen.summary()["reachable_end"] == max(r.summary()["reachable_end"] for r in tied_rs)


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


def test_baseline_uses_common_random_numbers():
    # the no-push counterfactual must be the same organic visits whatever policy is run
    none = simulate("casual", Policy("none"), N, DAYS, 13)
    vf = simulate("casual", Policy("volume_first", 5), N, DAYS, 13)
    assert np.array_equal(none.base_active, vf.base_active)


def _readme_row(cells):
    pushes, extra, _dau, _ret, push_on, reach = cells[2:8]
    pct = lambda x: float(x.rstrip("%")) / 100
    return {"sends_per_user_day": float(pushes), "incremental_active_days": float(extra.lstrip("+")),
            "push_on_end": pct(push_on), "reachable_end": pct(reach)}


def test_readme_results_match_published_data():
    # the README results table is hand-written; keep it in step with docs/data/recommendations.json
    recs = json.loads((ROOT / "docs" / "data" / "recommendations.json").read_text())
    lines = (ROOT / "README.md").read_text().splitlines()
    # README rounds pushes/day to 2 decimals, extra days to 1, shares to whole percents
    tol = {"sends_per_user_day": 0.005, "incremental_active_days": 0.05, "push_on_end": 0.005, "reachable_end": 0.005}
    for persona, p in P.PERSONAS.items():
        v = recs[persona]["validation"]
        i = next(k for k, ln in enumerate(lines) if ln.startswith(f"| {p['label']} |"))
        rows = {key: _readme_row([c.strip() for c in lines[i + j].strip().strip("|").split("|")])
                for j, key in enumerate(("status_quo", "recommended"))}
        for key in ("status_quo", "recommended"):
            for metric, t in tol.items():
                assert abs(rows[key][metric] - v[key][metric]) <= t + 1e-9, (persona, key, metric, rows[key][metric], v[key][metric])


def _dau_mau_reference(active, window=30):
    n, days = active.shape
    out = np.zeros(days)
    for t in range(days):
        mau = active[:, max(0, t - window + 1):t + 1].any(1).mean()
        out[t] = active[:, t].mean() / mau if mau > 0 else 0.0
    return out


def test_dau_mau_matches_the_day_by_day_definition():
    rng = np.random.default_rng(0)
    active = rng.random((200, 75)) < 0.3
    active[:50] = False                       # people who never show up
    assert np.array_equal(Result.dau_mau(active), _dau_mau_reference(active))
    assert np.array_equal(Result.dau_mau(np.zeros((10, 5), bool)), np.zeros(5))


def test_type_tallies_add_up():
    r = simulate("contributor", Policy("fatigue_aware", 4, 0.3, batch=True, email=True), N, DAYS, 14)
    assert r.type_sends.sum() == r.sends.sum()
    assert r.type_opens.sum() == r.opens.sum()
    assert np.array_equal(r.type_opens + r.type_ignores, r.type_sends)


def test_policy_lists_are_in_a_fixed_order():
    base = Policy("fatigue_aware", 3, 0.3)
    lad = ladder_policies(base)
    assert lad[0] == base and len(lad) == 6 and all(p.cap == 3 for p in lad)
    abl = ablation_policies(base)
    assert [k for k in P.TYPE_KEYS] == [next(k for k in P.TYPE_KEYS if k not in p.allowed) for p in abl]
