"""Grid search over daily cap x relevance bar, content ablation, and held-out validation."""
from __future__ import annotations

import numpy as np

from . import params as P
from .sim import Policy, Result, simulate


def grid_policies() -> list[Policy]:
    out = [Policy("volume_first", c) for c in P.CAPS]
    out += [Policy("fatigue_aware", c, th) for c in P.CAPS for th in P.THRESHOLDS]
    return out


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
    chosen = max(tied, key=lambda x: (x[1]["push_on_end"], -x[1]["sends_per_user_day"]))[0]
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


def ablate(persona: str, pol: Policy, base: Result, n: int, days: int, seed: int) -> dict:
    """Switch each type off in turn on the same people; paired difference in lift."""
    out = {}
    for k in P.TYPE_KEYS:
        allowed = tuple(x for x in P.TYPE_KEYS if x != k and (pol.allowed is None or x in pol.allowed))
        r = simulate(persona, Policy(pol.kind, pol.cap, pol.threshold, pol.lam, allowed), n, days, seed)
        diff = r.incremental - base.incremental
        out[k] = (diff.mean(), 1.96 * diff.std(ddof=1) / np.sqrt(n))
    return out
