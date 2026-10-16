# Notification Lab

**Live demo:** https://chloe4ai.github.io/notification-lab/

A simulation of push-notification fatigue for a community app. It follows one person through their first month, push by push, and recommends how many notifications to send each day, and which ones, for three kinds of users.

> Concept demo. All data is simulated and parameters are illustrative, not fitted to any company's logs. The app in the demo ("Spark") is invented. Not affiliated with Reddit.

## Why

A push that gets ignored is not free. It spends a little of the user's patience. Once that runs out, they mute the app or turn push off, and that permission rarely comes back. Volume-first policies look fine at day 30 and lose the channel by day 180.

This is the same problem as ad frequency capping: the marginal impression has a cost that the click-through model does not see.

## What the model does

| Step | What happens |
|---|---|
| Supply | Each day a person gets candidates: replies to their posts and comments (in proportion to how much they contribute), upvote milestones, trending posts in joined communities, a digest, recommended posts and community suggestions. |
| Select | **Volume-first** sends the top *cap* by relevance. **Fatigue-aware** subtracts an irritation cost that grows with fatigue, lowers the ceiling as fatigue rises, and skips anything below a relevance bar. |
| Respond | Open probability = relevance × (1 − fatigue) × willingness. Opens lower fatigue; ignores raise it. Past a personal threshold the rest of the day is Do Not Disturb. Fatigue also lowers unprompted visits; recent opens raise them. |
| Burn | Each day there is a small chance, growing with fatigue², that the person turns push off for good. |
| Measure | Lift = extra active days versus the **same person** receiving no pushes (common random numbers). |

The optimiser grid-searches 30 policies (6 ceilings × volume-first and 4 relevance bars) on 3,000 simulated people per persona over 180 days. Among policies whose lift is statistically tied with the best, it picks the one that keeps the most people reachable. Each content type is then switched off in turn to measure what it contributes. Final numbers come from a fresh cohort of 4,500 people the optimiser never saw.

## What the site shows

| Post | Content |
|---|---|
| 01 Metrics dashboard | Nine headline metrics per persona (pushes/day, lift, open rate, opens per person, push on at day 30 and 180, reach days, DND days, pushes per extra active day), cumulative lift curve, the cap × relevance-bar grid the optimiser searched, a "mechanism or just less volume" comparison against the best volume-first policy, and all three personas side by side. |
| 02 One person, first 30 days | Two phones, same person, push by push, with a 30-day strip and population summary. |
| 03 How many pushes a day | Lift by daily cap with 95% intervals; validation table on a fresh cohort. |
| 04 Which pushes to send | Share of sends, open rate and ablation result per notification type. |
| 05 What the first month hides | Permission and lift curves over 180 days; day-30 vs day-180 table. |
| 06 How the numbers are made | Model steps and the data files. |

Every chart has hover tooltips; the sidebar has a glossary of the metrics.

## Results (validation cohort, 180 days)

| Persona | Policy | Pushes / day | Extra active days | Push still on |
|---|---|---|---|---|
| Notification minimalist | Today's default (top 5) | 2.09 | +7.2 | 19% |
| | Recommended (fatigue-aware) | 0.88 | +10.2 | 75% |
| Casual browser | Today's default | 3.45 | +18.0 | 57% |
| | Recommended | 1.62 | +19.7 | 88% |
| Active contributor | Today's default | 4.38 | +29.3 | 82% |
| | Recommended | 2.82 | +29.6 | 94% |

The answer depends on the user. For minimalists, sending less wins outright. For active contributors, today's default is about as good on six-month lift, and the gain is that 12 more people in 100 are still reachable.

## Run it

```bash
pip install -r requirements.txt
python scripts/generate.py          # writes docs/data/, about 3 minutes
python -m pytest -q
python -m http.server -d docs 8000  # open http://localhost:8000
```

## Layout

```
nlab/params.py      personas, notification types, dynamics
nlab/sim.py         vectorised day-by-day simulation
nlab/optimize.py    grid search, tie-break, content ablation
nlab/content.py     invented notification copy for the lived view
scripts/generate.py full pipeline -> docs/data/*.json, events_sample.csv
docs/               static site (GitHub Pages)
tests/              pytest
```

## Limits

- Parameters are hand-set to sit in plausible ranges, not fitted. With real logs, the first step is calibrating open, mute and opt-out curves against a holdout that receives no pushes.
- One push slot per candidate per day; no send-time optimisation yet.
- Personas are fixed segments. A production system would estimate tolerance per user and update it online.

Chloe Tan · October 2026
