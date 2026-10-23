"""Grid search over daily cap x relevance bar, content ablation, and held-out validation."""
from __future__ import annotations

import numpy as np

from . import params as P
from .sim import Policy, Result, simulate


def grid_policies() -> list[Policy]:
    out = [Policy("volume_first", c) for c in P.CAPS]
    out += [Policy("fatigue_aware", c, th) for c in P.CAPS for th in P.THRESHOLDS]
    out += [Policy("uplift_aware", c, th) for c in P.CAPS for th in P.UPLIFT_THRESHOLDS]
    return out


def tied_with(results: list[Result], best: dict) -> list[Result]:
    return [r for r in results
            if r.summary()["incremental_active_days"] + r.summary()["ci95"] >= best["incremental_active_days"] - best["ci95"]]


def run_serial(persona: str, policies: list[Policy], n: int, days: int, seed: int) -> list[Result]:
    """Simulate each policy in turn. generate.py passes a process-pool version with the same signature."""
    return [simulate(persona, p, n, days, seed) for p in policies]


def ladder_policies(base: Policy) -> list[Policy]:
    """The operational layers added one at a time on top of the chosen cap and bar."""
    return [base,
            Policy(base.kind, base.cap, base.threshold, base.lam, base.allowed, state_budget=True),
            Policy(base.kind, base.cap, base.threshold, base.lam, base.allowed, state_budget=True, batch=True),
            Policy(base.kind, base.cap, base.threshold, base.lam, base.allowed, state_budget=True, batch=True, email=True),
            Policy(base.kind, base.cap, base.threshold, base.lam, base.allowed, batch=True, email=True),
            Policy(base.kind, base.cap, base.threshold, base.lam, base.allowed, email=True)]


def ladder(persona: str, base: Policy, n: int, days: int, seed: int, run=run_serial) -> list[Result]:
    """Add the operational layers one at a time on top of the chosen cap and bar."""
    return run(persona, ladder_policies(base), n, days, seed)


def pick(results: list[Result]) -> tuple[Result, list[int]]:
    """Best mean lift; among policies statistically tied with it, keep the most push permission.

    Tied = the two 95% intervals overlap. Lift over 180 days does not price
    the campaigns a revoked user can never receive again, so we break ties
    toward the policy that keeps the channel open.
    """
    sums = [(r, r.summary()) for r in results]
    best_r, best = max(sums, key=lambda x: x[1]["incremental_active_days"])
    tied = [(r, s) for r, s in sums
            if s["incremental_active_days"] + s["ci95"] >= best["incremental_active_days"] - best["ci95"]]
    chosen = max(tied, key=lambda x: (x[1]["reachable_end"], x[1]["push_on_end"], -x[1]["sends_per_user_day"]))[0]
    tied_caps = sorted({r.policy.cap for r, _ in tied if r.policy.kind == chosen.policy.kind})
    return chosen, tied_caps


def content_mix(res: Result, ablation: dict | None = None) -> list[dict]:
    total = max(1.0, res.type_sends.sum())
    rows = []
    for i, t in enumerate(P.TYPES):
        s = res.type_sends[i]
        row = {
            "type": t["key"], "label": t["label"],
            "sends_per_user_day": round(float(s / (res.n * res.daily_push_on.size)), 3),
            "share_of_sends": round(float(s / total), 3),
            "open_rate": round(float(res.type_opens[i] / max(1, s)), 3),
            "ignore_rate": round(float(res.type_ignores[i] / max(1, s)), 3),
            "value_per_send": round(float(res.type_value[i] / max(1, s)), 3),
        }
        d, ci = (ablation or {}).get(t["key"], (0.0, 0.0))
        row["delta_if_removed"] = round(float(d), 3)
        row["ci95"] = round(float(ci), 3)
        if row["share_of_sends"] < 0.02:
            row["rule"] = "rare"
        elif d < -ci:
            row["rule"] = "send"
        elif d > ci:
            row["rule"] = "drop"
        else:
            row["rule"] = "optional"
        rows.append(row)
    return rows


def ablation_policies(pol: Policy) -> list[Policy]:
    """One policy per notification type, with that type switched off (order follows P.TYPE_KEYS)."""
    return [Policy(pol.kind, pol.cap, pol.threshold, pol.lam,
                   tuple(x for x in P.TYPE_KEYS if x != k and (pol.allowed is None or x in pol.allowed)))
            for k in P.TYPE_KEYS]


def ablate(persona: str, pol: Policy, base: Result, n: int, days: int, seed: int, run=run_serial) -> dict:
    """Switch each type off in turn on the same people; paired difference in lift."""
    out = {}
    for k, r in zip(P.TYPE_KEYS, run(persona, ablation_policies(pol), n, days, seed)):
        diff = r.incremental - base.incremental
        out[k] = (diff.mean(), 1.96 * diff.std(ddof=1) / np.sqrt(n))
    return out
