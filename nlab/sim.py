"""Vectorised day-by-day simulation of push notifications for a cohort.

Every policy is run on the same people with the same random draws
(common random numbers), so differences between policies are not noise
from different populations. Lift is measured against the same person
receiving no pushes at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import params as P

T = len(P.TYPES)
BASE = np.array([t["base"] for t in P.TYPES])
ANNOY = np.array([t["annoy"] for t in P.TYPES])
VALUE = np.array([t["value"] for t in P.TYPES])
MAX_PER_TYPE = 4
MAX_CAP = max(P.CAPS)
SLOT_TYPE = np.repeat(np.arange(T), MAX_PER_TYPE)  # candidate slot -> type index
M = SLOT_TYPE.size


@dataclass
class Policy:
    kind: str                 # "none" | "volume_first" | "fatigue_aware"
    cap: int = 0
    threshold: float | None = None
    lam: float = P.LAMBDA
    allowed: tuple[str, ...] | None = None  # None = all types

    @property
    def name(self) -> str:
        if self.kind == "none":
            return "No pushes"
        k = "Volume-first" if self.kind == "volume_first" else "Fatigue-aware"
        return f"{k} · cap {self.cap}"

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "cap": self.cap, "threshold": self.threshold}
        if self.kind == "fatigue_aware":
            d["lam"] = self.lam
        return d


@dataclass
class Result:
    persona: str
    policy: Policy
    n: int
    incremental: np.ndarray          # per user, extra active days vs no pushes
    sends: np.ndarray
    opens: np.ndarray
    dnd_days: np.ndarray
    push_on_end: np.ndarray
    push_on_day30: np.ndarray
    daily_push_on: np.ndarray        # share of users with push on, per day
    daily_incremental: np.ndarray    # share of users with an extra active day, per day
    type_sends: np.ndarray           # (T,)
    type_opens: np.ndarray
    type_ignores: np.ndarray
    type_value: np.ndarray
    trace: dict = field(default_factory=dict)  # user index -> list of day dicts

    def summary(self) -> dict:
        n, days = self.n, self.daily_push_on.size
        inc = self.incremental
        sends = self.sends.sum()
        return {
            "incremental_active_days": round(float(inc.mean()), 3),
            "ci95": round(float(1.96 * inc.std(ddof=1) / np.sqrt(n)), 3),
            "push_on_end": round(float(self.push_on_end.mean()), 3),
            "push_on_day30": round(float(self.push_on_day30.mean()), 3),
            "sends_per_user_day": round(float(sends / (n * days)), 3),
            "open_rate": round(float(self.opens.sum() / max(1, sends)), 3),
            "dnd_days_per_user": round(float(self.dnd_days.mean()), 3),
        }


def simulate(persona: str, policy: Policy, n: int, days: int, seed: int,
             trace_users: tuple[int, ...] = ()) -> Result:
    pp = P.PERSONAS[persona]
    rc = np.random.default_rng(seed)          # people, candidates, organic visits
    rr = np.random.default_rng(seed + 7919)   # responses and revokes

    # --- people (same for every policy at a given seed) ---
    lg = lambda: np.exp(rc.normal(-P.HETEROGENEITY ** 2 / 2, P.HETEROGENEITY, n))
    contrib = pp["contribution"] * lg()
    open_m = np.clip(pp["open_mul"] * lg(), 0, 1)
    tol = pp["tolerance"] * lg()
    organic = np.clip(pp["organic"] * lg(), 0.01, 0.95)
    dnd_thr = np.clip(pp["dnd"] + rc.normal(0, 0.05, n), 0.3, 0.98)
    affinity = rc.normal(0, 0.08, (n, T))

    allowed = np.ones(T, bool)
    if policy.allowed is not None:
        allowed = np.array([k in policy.allowed for k in P.TYPE_KEYS])

    reply_rate = np.array([P.REPLY_RATE.get(k, 0.0) for k in P.TYPE_KEYS])
    pool_rate = np.array([P.POOL_RATE.get(k, 0.0) for k in P.TYPE_KEYS])
    is_digest = np.array([k == "digest" for k in P.TYPE_KEYS])

    fatigue = np.zeros(n)
    push_on = np.ones(n, bool)
    opens7 = np.zeros((n, 7), int)

    inc = np.zeros(n)
    sends = np.zeros(n, int)
    opens = np.zeros(n, int)
    dnd_days = np.zeros(n, int)
    push30 = np.ones(n, bool)
    d_push = np.zeros(days)
    d_inc = np.zeros(days)
    ts = np.zeros(T)
    to = np.zeros(T)
    ti = np.zeros(T)
    tv = np.zeros(T)
    trace = {u: [] for u in trace_users}
    rows = np.arange(n)

    for day in range(days):
        # --- candidates (fixed-shape draws so every policy sees the same ones) ---
        lam = reply_rate[None, :] * contrib[:, None] + pool_rate[None, :]
        counts = np.minimum(rc.poisson(lam), MAX_PER_TYPE)
        counts[:, is_digest] = np.minimum(counts[:, is_digest], 1)
        noise = rc.normal(0, 0.12, (n, M))
        rel = np.clip(BASE[SLOT_TYPE][None, :] + affinity[:, SLOT_TYPE] + noise, 0.02, 0.98)
        slot_rank = np.tile(np.arange(MAX_PER_TYPE), T)[None, :]
        valid = slot_rank < counts[:, SLOT_TYPE]
        u_org = rc.random(n)
        u_open = rr.random((n, MAX_CAP))
        u_rev = rr.random(n)

        valid &= allowed[SLOT_TYPE][None, :]
        valid &= push_on[:, None]
        if policy.kind == "none":
            valid[:] = False

        f0 = fatigue.copy()
        dnd = np.zeros(n, bool)
        opened = np.zeros(n, bool)
        rel_m = np.where(valid, rel, -np.inf)
        cap_eff = np.full(n, policy.cap)
        if policy.kind == "fatigue_aware":
            cap_eff = np.maximum(1, np.rint(policy.cap * (1 - f0)).astype(int))
        day_log = {u: [] for u in trace_users}

        for s in range(policy.cap):
            if policy.kind == "volume_first":
                score = rel_m
                pick = score.argmax(1)
                ok = np.isfinite(score[rows, pick])
            else:
                score = rel_m - policy.lam * fatigue[:, None] * ANNOY[SLOT_TYPE][None, :]
                pick = score.argmax(1)
                best = score[rows, pick]
                ok = np.isfinite(best) & (best >= policy.threshold) & (s < cap_eff)
            if not ok.any():
                break
            t_idx = SLOT_TYPE[pick]
            r = rel[rows, pick]
            muted = ok & dnd
            live = ok & ~dnd
            p_open = r * (1 - fatigue) * open_m
            op = live & (u_open[:, s] < p_open)
            ig = live & ~op
            fatigue = np.where(op, fatigue * P.OPEN_RELIEF, fatigue)
            fatigue = np.where(ig, fatigue + tol * ANNOY[t_idx] * (1 - fatigue), fatigue)
            newly_dnd = live & (fatigue > dnd_thr)
            dnd |= newly_dnd
            opened |= op
            sends += ok
            opens += op
            np.add.at(ts, t_idx[ok], 1)
            np.add.at(to, t_idx[op], 1)
            np.add.at(ti, t_idx[ig], 1)
            np.add.at(tv, t_idx[op], VALUE[t_idx[op]])
            for u in trace_users:
                if ok[u]:
                    day_log[u].append({
                        "type": P.TYPE_KEYS[t_idx[u]],
                        "outcome": "opened" if op[u] else ("muted" if muted[u] else "ignored"),
                        "relevance": round(float(r[u]), 3),
                        "fatigue_after": round(float(fatigue[u]), 3),
                    })
            rel_m[rows[ok], pick[ok]] = -np.inf

        # --- organic visits and lift vs the same person with no pushes ---
        habit = 1 + P.HABIT_BOOST * np.minimum(opens7.sum(1), 3)
        org_p = np.clip(organic * (1 - P.ORGANIC_FATIGUE_DRAG * f0) * habit, 0, 0.98)
        visit = u_org < org_p
        base_visit = u_org < organic
        active = visit | opened
        delta = active.astype(int) - base_visit.astype(int)
        inc += delta
        d_inc[day] = delta.mean()
        dnd_days += dnd

        opens7 = np.roll(opens7, 1, axis=1)
        opens7[:, 0] = opened

        # --- burn: chance of turning push off grows with fatigue squared, never comes back ---
        revoked = push_on & (u_rev < pp["revoke_k"] * (fatigue / 0.5) ** 2)
        for u in trace_users:
            trace[u].append({
                "day": day + 1, "dnd": bool(dnd[u]), "push_on": bool(push_on[u]),
                "revoked_today": bool(revoked[u]), "organic_visit": bool(visit[u]),
                "active": bool(active[u]), "fatigue_end": round(float(fatigue[u]), 3),
                "notifications": day_log[u],
            })
        push_on &= ~revoked
        if day == 29:
            push30 = push_on.copy()
        d_push[day] = push_on.mean()
        fatigue *= P.OVERNIGHT_RECOVERY

    if days < 30:
        push30 = push_on.copy()
    return Result(persona, policy, n, inc, sends, opens, dnd_days, push_on.copy(), push30,
                  d_push, d_inc, ts, to, ti, tv, trace)
