"""Vectorised day-by-day simulation of push notifications for a signup cohort.

Every policy is run on the same people with the same random draws
(common random numbers), so differences between policies are not noise
from different populations. Lift is measured against the same person
receiving no pushes at all, which is also what a logged-out visitor
looks like: organic visits only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import params as P

T = len(P.TYPES)
BASE = np.array([t["base"] for t in P.TYPES])
ANNOY = np.array([t["annoy"] for t in P.TYPES])
VALUE = np.array([t["value"] for t in P.TYPES])
IS_POOL = np.array([t["supply"] == "pool" for t in P.TYPES])
DIGEST = P.TYPE_KEYS.index("digest")
MAX_PER_TYPE = 4
MAX_CAP = max(P.CAPS)
SLOT_TYPE = np.repeat(np.arange(T), MAX_PER_TYPE)  # candidate slot -> type index
M = SLOT_TYPE.size


@dataclass
class Policy:
    kind: str                 # "none" | "volume_first" | "fatigue_aware" | "uplift_aware"
    cap: int = 0
    threshold: float | None = None
    lam: float = P.LAMBDA
    allowed: tuple[str, ...] | None = None  # None = all types
    state_budget: bool = False   # halve the cap for core users, lower the bar for dormant ones
    batch: bool = False          # fold unsent pool candidates into one digest push
    email: bool = False          # email digest for people who turned push off

    @property
    def name(self) -> str:
        if self.kind == "none":
            return "No pushes"
        k = {"volume_first": "Volume-first", "fatigue_aware": "Fatigue-aware", "uplift_aware": "Uplift-aware"}[self.kind]
        s = f"{k} · cap {self.cap}"
        extras = [x for x, on in (("state budget", self.state_budget), ("batching", self.batch), ("email", self.email)) if on]
        return s + (" + " + " + ".join(extras) if extras else "")

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "cap": self.cap, "threshold": self.threshold,
             "state_budget": self.state_budget, "batch": self.batch, "email": self.email}
        if self.kind in ("fatigue_aware", "uplift_aware"):
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
    active: np.ndarray               # (n, days) bool: logged-in activity that day
    base_active: np.ndarray          # (n, days) bool: organic visits only (no pushes)
    email_sends: np.ndarray
    email_opens: np.ndarray
    email_on_end: np.ndarray
    type_sends: np.ndarray           # (T,)
    type_opens: np.ndarray
    type_ignores: np.ndarray
    type_value: np.ndarray
    trace: dict = field(default_factory=dict)  # user index -> list of day dicts

    # --- retention metrics on the active matrix ---
    @staticmethod
    def dau_mau(active: np.ndarray, window: int = 30) -> np.ndarray:
        """DAU over MAU per day: share active today / share active in the `window` days ending today."""
        n, days = active.shape
        cs = np.cumsum(active, axis=1, dtype=np.int64)
        in_window = cs - np.pad(cs, ((0, 0), (window, 0)))[:, :days]   # active days in the trailing window
        mau = (in_window > 0).mean(0)
        dau = active.mean(0)
        return np.divide(dau, mau, out=np.zeros(days), where=mau > 0)

    @staticmethod
    def retained(active: np.ndarray, day: int, window: int = 7) -> float:
        """Share active at least once in the 7 days ending on `day` (1-based)."""
        lo = max(0, day - window)
        return float(active[:, lo:day].any(1).mean())

    def summary(self) -> dict:
        n, days = self.n, self.daily_push_on.size
        inc = self.incremental
        sends = self.sends.sum()
        dm = self.dau_mau(self.active)
        out = {
            "incremental_active_days": round(float(inc.mean()), 3),
            "ci95": round(float(1.96 * inc.std(ddof=1) / np.sqrt(n)), 3),
            "push_on_end": round(float(self.push_on_end.mean()), 3),
            "push_on_day30": round(float(self.push_on_day30.mean()), 3),
            "sends_per_user_day": round(float(sends / (n * days)), 3),
            "open_rate": round(float(self.opens.sum() / max(1, sends)), 3),
            "dnd_days_per_user": round(float(self.dnd_days.mean()), 3),
            "active_rate": round(float(self.active.mean()), 4),
            "dau_mau_30": round(float(dm[min(29, days - 1)]), 4),
            "dau_mau_90": round(float(dm[min(89, days - 1)]), 4),
            "dau_mau_end": round(float(dm[-1]), 4),
            "retained_d7": round(self.retained(self.active, min(7, days)), 4),
            "retained_d30": round(self.retained(self.active, min(30, days)), 4),
            "retained_d90": round(self.retained(self.active, min(90, days)), 4),
            "retained_end": round(self.retained(self.active, days), 4),
        }
        if self.policy.email:
            es = self.email_sends.sum()
            out["email_sends_per_user_day"] = round(float(es / (n * days)), 3)
            out["email_open_rate"] = round(float(self.email_opens.sum() / max(1, es)), 3)
            out["email_on_end"] = round(float(self.email_on_end.mean()), 3)
            out["reachable_end"] = round(float((self.push_on_end | self.email_on_end).mean()), 3)
        else:
            out["reachable_end"] = out["push_on_end"]
        return out


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
    email_phase = rc.integers(0, P.EMAIL["every"], n)

    allowed = np.ones(T, bool)
    if policy.allowed is not None:
        allowed = np.array([k in policy.allowed for k in P.TYPE_KEYS])

    reply_rate = np.array([P.REPLY_RATE.get(k, 0.0) for k in P.TYPE_KEYS])
    pool_rate = np.array([P.POOL_RATE.get(k, 0.0) for k in P.TYPE_KEYS])
    is_digest = np.array([k == "digest" for k in P.TYPE_KEYS])

    fatigue = np.zeros(n)
    push_on = np.ones(n, bool)
    email_on = np.ones(n, bool)
    opens7 = np.zeros((n, 7), int)
    act14 = np.zeros((n, 14), bool)

    inc = np.zeros(n)
    sends = np.zeros(n, int)
    opens = np.zeros(n, int)
    dnd_days = np.zeros(n, int)
    e_sends = np.zeros(n, int)
    e_opens = np.zeros(n, int)
    push30 = np.ones(n, bool)
    d_push = np.zeros(days)
    d_inc = np.zeros(days)
    act = np.zeros((n, days), bool)
    base_act = np.zeros((n, days), bool)
    ts = np.zeros(T)
    to = np.zeros(T)
    ti = np.zeros(T)
    tv = np.zeros(T)
    trace = {u: [] for u in trace_users}
    rows = np.arange(n)
    scored = policy.kind in ("fatigue_aware", "uplift_aware")

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
        u_open = rr.random((n, MAX_CAP + 1))
        u_rev = rr.random(n)
        u_email = rr.random((n, 2))

        valid &= allowed[SLOT_TYPE][None, :]
        valid &= push_on[:, None]
        if policy.kind == "none":
            valid[:] = False

        f0 = fatigue.copy()
        dnd = np.zeros(n, bool)
        opened = np.zeros(n, bool)
        rel_m = np.where(valid, rel, -np.inf)
        cap_eff = np.full(n, policy.cap)
        thr = np.full(n, policy.threshold if policy.threshold is not None else -np.inf)
        if scored:
            cap_eff = np.maximum(1, np.rint(policy.cap * (1 - f0)).astype(int))
            if policy.state_budget:
                # Pinterest-style: core users come anyway, dormant ones are where a push adds most
                recent = act14.sum(1)
                core = recent >= P.STATE["core_days"]
                dormant = recent == 0
                cap_eff = np.where(core, np.maximum(1, policy.cap // 2), cap_eff)
                thr = np.where(dormant, thr - P.STATE["dormant_bar_relief"], thr)
        # batching (LinkedIn ATC style): two or more pool candidates become one digest instead of
        # several individual pushes. The digest inherits the best two's relevance plus a small bonus.
        if policy.batch and scored:
            pool_slot = IS_POOL[SLOT_TYPE] & ~is_digest[SLOT_TYPE]
            pool_v = valid & pool_slot[None, :]
            n_pool = pool_v.sum(1)
            top2 = np.partition(np.where(pool_v, rel, -np.inf), -2, axis=1)[:, -2:]
            r_b = np.clip(top2.mean(1) + P.BATCH["bonus"], 0.02, 0.98)
            # only fold when the digest itself is allowed; otherwise pool items go out individually
            fold = (n_pool >= 2) & allowed[DIGEST]
            dslot = DIGEST * MAX_PER_TYPE
            rel[fold, dslot] = np.maximum(np.where(valid[fold, dslot], rel[fold, dslot], 0), r_b[fold])
            valid[fold, dslot] = True
            valid[fold[:, None] & pool_slot[None, :]] = False
            rel_m = np.where(valid, rel, -np.inf)
        # uplift-aware discounts by the chance the person would have visited anyway
        anyway = organic if policy.kind == "uplift_aware" else np.zeros(n)
        day_log = {u: [] for u in trace_users}

        def respond(ok, t_idx, r, slot, channel):
            nonlocal fatigue, dnd, opened
            muted = ok & dnd
            live = ok & ~dnd
            mult = P.EMAIL["open_mul"] if channel == "email" else 1.0
            annoy_mult = P.EMAIL["annoy"] if channel == "email" else 1.0
            p_open = r * (1 - fatigue) * open_m * mult
            op = live & (u_open[:, slot] < p_open)
            ig = live & ~op
            fatigue = np.where(op, fatigue * P.OPEN_RELIEF, fatigue)
            fatigue = np.where(ig, fatigue + tol * ANNOY[t_idx] * annoy_mult * (1 - fatigue), fatigue)
            if channel == "push":
                dnd |= live & (fatigue > dnd_thr)
            opened |= op
            for u in trace_users:
                if ok[u]:
                    day_log[u].append({
                        "type": P.TYPE_KEYS[t_idx[u]], "channel": channel,
                        "outcome": "opened" if op[u] else ("muted" if muted[u] else "ignored"),
                        "relevance": round(float(r[u]), 3),
                        "fatigue_after": round(float(fatigue[u]), 3),
                    })
            return op, ig

        for s in range(policy.cap):
            if policy.kind == "volume_first":
                score = rel_m
                pick = score.argmax(1)
                ok = np.isfinite(score[rows, pick])
            else:
                base_score = rel_m * (1 - fatigue)[:, None] * open_m[:, None] * (1 - anyway)[:, None] if policy.kind == "uplift_aware" else rel_m
                score = base_score - policy.lam * fatigue[:, None] * ANNOY[SLOT_TYPE][None, :]
                pick = score.argmax(1)
                best = score[rows, pick]
                ok = np.isfinite(best) & (best >= thr) & (s < cap_eff)
            if not ok.any():
                break
            t_idx = SLOT_TYPE[pick]
            r = rel[rows, pick]
            op, ig = respond(ok, t_idx, r, s, "push")
            sends += ok
            opens += op
            ts += np.bincount(t_idx[ok], minlength=T)
            to += np.bincount(t_idx[op], minlength=T)
            ti += np.bincount(t_idx[ig], minlength=T)
            tv += np.bincount(t_idx[op], weights=VALUE[t_idx[op]], minlength=T)
            rel_m[rows[ok], pick[ok]] = -np.inf

        # --- email digest for people who turned push off ---
        if policy.email and policy.kind != "none":
            due = (~push_on) & email_on & ((day + email_phase) % P.EMAIL["every"] == 0)
            if due.any():
                pool_rel = np.where((slot_rank < counts[:, SLOT_TYPE]) & IS_POOL[SLOT_TYPE][None, :], rel, -np.inf).max(1)
                r_e = np.where(np.isfinite(pool_rel), pool_rel, BASE[DIGEST])
                t_idx = np.full(n, DIGEST)
                p_open = r_e * (1 - fatigue) * open_m * P.EMAIL["open_mul"]
                op = due & (u_email[:, 0] < p_open)
                ig = due & ~op
                fatigue = np.where(op, fatigue * P.OPEN_RELIEF, fatigue)
                fatigue = np.where(ig, fatigue + tol * ANNOY[DIGEST] * P.EMAIL["annoy"] * (1 - fatigue), fatigue)
                opened |= op
                e_sends += due
                e_opens += op
                for u in trace_users:
                    if due[u]:
                        day_log[u].append({"type": "digest", "channel": "email",
                                           "outcome": "opened" if op[u] else "ignored",
                                           "relevance": round(float(r_e[u]), 3),
                                           "fatigue_after": round(float(fatigue[u]), 3)})
                unsub = ig & (u_email[:, 1] < P.EMAIL["unsub_per_ignore"])
                email_on &= ~unsub

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
        act[:, day] = active
        base_act[:, day] = base_visit

        opens7 = np.roll(opens7, 1, axis=1)
        opens7[:, 0] = opened
        act14 = np.roll(act14, 1, axis=1)
        act14[:, 0] = active

        # --- burn: chance of turning push off grows with fatigue squared, never comes back ---
        revoked = push_on & (u_rev < pp["revoke_k"] * (fatigue / 0.5) ** 2)
        for u in trace_users:
            trace[u].append({
                "day": day + 1, "dnd": bool(dnd[u]), "push_on": bool(push_on[u]),
                "email_on": bool(email_on[u]),
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
                  d_push, d_inc, act, base_act, e_sends, e_opens, email_on.copy(),
                  ts, to, ti, tv, trace)
