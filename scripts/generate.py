"""Run the full pipeline and write the site's data files to docs/data/.

    python scripts/generate.py            # full run (~2-4 minutes)
    python scripts/generate.py --quick    # small cohorts, for a smoke test
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nlab import content, params as P  # noqa: E402
from nlab.optimize import ablate, content_mix, grid_policies, pick  # noqa: E402
from nlab.sim import Policy, simulate  # noqa: E402

OUT = ROOT / "docs" / "data"
LIVED_PEOPLE, LIVED_DAYS, EVENT_PEOPLE = 400, 30, 40


def row(res, extra=None):
    d = {**res.policy.as_dict(), **res.summary()}
    d.pop("lam", None)
    if extra:
        d.update(extra)
    return d


def lived_view(persona, sq, rec, rng):
    a = simulate(persona, sq, LIVED_PEOPLE, LIVED_DAYS, P.VALIDATION_SEED + 1)
    b = simulate(persona, rec, LIVED_PEOPLE, LIVED_DAYS, P.VALIDATION_SEED + 1)
    # representative person: closest to the population median under today's default,
    # among those who keep push on under both policies (the common case)
    feats = np.c_[a.sends, a.opens, a.dnd_days]
    z = (feats - np.median(feats, 0)) / (feats.std(0) + 1e-9)
    dist = np.abs(z).sum(1) + 10 * (~b.push_on_end)
    who = int(dist.argmin())
    out = {}
    for key, pol, pop in (("status_quo", sq, a), ("recommended", rec, b)):
        t = simulate(persona, pol, LIVED_PEOPLE, LIVED_DAYS, P.VALIDATION_SEED + 1, trace_users=(who,))
        days = t.trace[who]
        for d in days:
            ts = content.times(len(d["notifications"]), rng)
            for n, tm in zip(d["notifications"], ts):
                n["time"] = tm
                n.update(content.make(n["type"], rng))
        out[key] = {
            "policy": pol.name,
            "person": {"sends": int(t.sends[who]), "opens": int(t.opens[who]),
                       "dnd": int(t.dnd_days[who]), "revoked": int(not t.push_on_end[who])},
            "days": days,
            "population": {
                "people": LIVED_PEOPLE,
                "share_revoked": round(float(1 - pop.push_on_end.mean()), 3),
                "mean_dnd_days": round(float(pop.dnd_days.mean()), 3),
                "mean_sends": round(float(pop.sends.mean()), 3),
                "mean_opens": round(float(pop.opens.mean()), 3),
            },
        }
    return out


def events(persona, pols, w):
    tr = tuple(range(EVENT_PEOPLE))
    rng = np.random.default_rng(7)
    for key, pol in pols.items():
        r = simulate(persona, pol, EVENT_PEOPLE, LIVED_DAYS, P.VALIDATION_SEED + 2, trace_users=tr)
        for u in tr:
            for d in r.trace[u]:
                for n, tm in zip(d["notifications"], content.times(len(d["notifications"]), rng)):
                    w.writerow([persona, key, f"{persona[:3]}-{u:03d}", d["day"], tm, n["type"],
                                n["relevance"], n["outcome"], n["fatigue_after"], int(d["dnd"]),
                                int(d["push_on"] and not d["revoked_today"])])


def main(quick: bool):
    n_tr = 400 if quick else P.USERS_PER_CONFIG
    n_va = 600 if quick else P.VALIDATION_USERS
    days = P.HORIZON_DAYS
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(11)
    sq = Policy(P.STATUS_QUO["kind"], P.STATUS_QUO["cap"])
    recs, cohort, lived = {}, {}, {}
    fh = open(OUT / "events_sample.csv", "w", newline="")
    w = csv.writer(fh)
    w.writerow(["persona", "policy", "person_id", "day", "time", "type", "relevance", "outcome",
                "fatigue_after", "dnd_day", "push_on_end_of_day"])

    for persona in P.PERSONAS:
        print(f"[{persona}] grid search", flush=True)
        results = [simulate(persona, pol, n_tr, days, P.TRAIN_SEED) for pol in grid_policies()]
        vf = [r for r in results if r.policy.kind == "volume_first"]
        fa = [r for r in results if r.policy.kind == "fatigue_aware"]
        best_fa, tied = pick(fa)
        best_vf, _ = pick(vf)
        sq_tr = next(r for r in vf if r.policy.cap == sq.cap)

        print(f"[{persona}] content ablation", flush=True)
        abl = ablate(persona, best_fa.policy, best_fa, n_tr, days, P.TRAIN_SEED)
        abl_sq = ablate(persona, sq, sq_tr, n_tr, days, P.TRAIN_SEED)
        mix = content_mix(best_fa, abl)
        dropped = [m["type"] for m in mix if m["rule"] == "drop"]
        allowed = tuple(k for k in P.TYPE_KEYS if k not in dropped)
        rec = Policy("fatigue_aware", best_fa.policy.cap, best_fa.policy.threshold, P.LAMBDA,
                     None if not dropped else allowed)

        print(f"[{persona}] validation on a fresh cohort", flush=True)
        v = {}
        for key, pol in (("status_quo", sq), ("best_volume_first", best_vf.policy),
                         ("best_fatigue_aware", best_fa.policy), ("recommended", rec)):
            r = simulate(persona, pol, n_va, days, P.VALIDATION_SEED)
            v[key] = {"policy": pol.name + (" · content rules" if key == "recommended" and dropped else ""),
                      **r.summary()}
            if key == "status_quo":
                c_sq = r
            if key == "recommended":
                c_rec = r

        recs[persona] = {
            "grid": [row(r) for r in results],
            "best": row(best_fa), "best_volume_first": row(best_vf),
            "tied_caps": tied,
            "content_mix": mix,
            "content_mix_status_quo": content_mix(sq_tr, abl_sq),
            "recommended_policy": {"kind": "fatigue_aware", "cap": rec.cap, "lam": rec.lam,
                                   "threshold": rec.threshold, "allowed": list(allowed), "dropped": dropped},
            "validation": v,
        }
        cohort[persona] = {
            k: {"push_on": [round(float(x), 4) for x in r.daily_push_on],
                "incremental_dau": [round(float(x) * 100, 3) for x in r.daily_incremental]}
            for k, r in (("status_quo", c_sq), ("recommended", c_rec))
        }
        print(f"[{persona}] lived experience + events", flush=True)
        lived[persona] = lived_view(persona, sq, rec, rng)
        events(persona, {"status_quo": sq, "recommended": rec}, w)
        s, rv = v["status_quo"], v["recommended"]
        print(f"[{persona}] cap {rec.cap} bar {rec.threshold} | lift {s['incremental_active_days']} -> "
              f"{rv['incremental_active_days']} | push on {s['push_on_end']} -> {rv['push_on_end']}", flush=True)
    fh.close()

    meta = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "horizon_days": days, "users_per_config": n_tr, "validation_users": n_va,
        "train_seed": P.TRAIN_SEED, "validation_seed": P.VALIDATION_SEED,
        "status_quo": P.STATUS_QUO, "grid": {"caps": P.CAPS, "thresholds": P.THRESHOLDS},
        "types": P.TYPES,
        "personas": {k: {kk: vv for kk, vv in p.items()} for k, p in P.PERSONAS.items()},
        "communities": P.COMMUNITIES,
    }
    for name, obj in (("meta", meta), ("recommendations", recs), ("cohort", cohort), ("lived", lived)):
        (OUT / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    main(ap.parse_args().quick)
