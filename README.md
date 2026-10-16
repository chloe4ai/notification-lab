# Notification Lab

**Live demo:** https://chloe4ai.github.io/notification-lab/

Notifications as a retention channel. A cohort of new signups to a community app is simulated for 180 days under today's default push policy and a fatigue-aware one, and the site reports what a retention team cares about: logged-in DAU/MAU, day-N retention, and how many people can still be reached by push or email. It follows one person through their first month, push by push, and recommends how many notifications to send each day, which ones, and through which channel, for three kinds of users.

> Concept demo. All data is simulated and parameters are illustrative, not fitted to any company's logs. The app in the demo ("Kin") is invented. Not affiliated with Reddit.

## Why

A push that gets ignored is not free. It spends a little of the user's patience. Once that runs out, they mute the app or turn push off, and that permission rarely comes back. Volume-first policies look fine at day 30 and lose the channel by day 180.

This is the same problem as ad frequency capping: the marginal impression has a cost that the click-through model does not see.

## What the model does

| Step | What happens |
|---|---|
| Supply | Each day a person gets candidates: replies to their posts and comments (in proportion to how much they contribute), upvote milestones, trending posts in joined communities, a digest, recommended posts and community suggestions. |
| Select | **Volume-first** sends the top *cap* by relevance. **Fatigue-aware** subtracts an irritation cost that grows with fatigue, lowers the ceiling as fatigue rises, and skips anything below a relevance bar. **Uplift-aware** scores by relevance × open chance × (1 − chance of visiting anyway), the Instagram idea. Optional layers on top: a per-state budget (half the cap for core users, lower bar for dormant ones, after Pinterest), batching (two or more feed items become one digest, after LinkedIn), and an email digest for people who turned push off. |
| Respond | Open probability = relevance × (1 − fatigue) × willingness. Opens lower fatigue; ignores raise it. Past a personal threshold the rest of the day is Do Not Disturb. Fatigue also lowers unprompted visits; recent opens raise them. |
| Burn | Each day there is a small chance, growing with fatigue², that the person turns push off for good. Ignored emails carry their own unsubscribe chance. |
| Measure | Lift = extra active days versus the **same person** receiving no pushes (common random numbers). |

The optimiser grid-searches 54 policies (6 ceilings × volume-first, 4 relevance bars, 4 uplift bars) on 3,000 simulated people per persona over 180 days, then switches the operational layers on one at a time and keeps those that do not lose lift. Among policies whose lift is statistically tied with the best, it picks the one that keeps the most people reachable. Each content type is then switched off in turn to measure what it contributes. Final numbers come from a fresh cohort of 4,500 people the optimiser never saw.

## What the site shows

| Post | Content |
|---|---|
| 01 The growth funnel this lives in | SEO → Identity → Notifications. DAU/MAU of the signup cohort against a logged-out look-alike; retention at D7/D30/D90/D180. |
| 02 Metrics dashboard | Twelve metrics per persona (DAU/MAU at day 30 and 180, D90 retention, pushes/day, lift, open rate, opens per person, push on at day 30, reachable at 180, reach days, DND days, pushes per extra active day), cumulative lift, the cap × relevance-bar grid, a lift-vs-reach frontier with an α slider, a "mechanism or just less volume" comparison, and all three personas side by side. |
| 03 One person, first 30 days | Two phones, same person, push by push (and email digests once push is off), with a 30-day strip and population summary. |
| 04 How many pushes a day | Lift by daily cap with 95% intervals; validation table on a fresh cohort. |
| 05 Which pushes to send | Share of sends, open rate and ablation result per notification type. |
| 06 What a 30-day test hides | Permission and lift curves over 180 days; D30 vs D90 retention and day-30 vs day-180 permission. |
| 07 What each layer adds | The recommended stack built up one layer at a time (fatigue-aware core → per-state budget → batching → email), with the uplift-aware policy as the measured next step. |
| 08 What the big apps do | Pinterest, LinkedIn, Instagram, X, Facebook, Duolingo: what they published and what is reproduced here. |
| 09 How the numbers are made | Model steps and the data files. |

Every chart has hover tooltips; the sidebar has a glossary of the metrics.

## Results (validation cohort of new signups, 180 days)

| Persona | Policy | Pushes / day | Extra active days | DAU/MAU d180 | Retained d90 | Push on d180 | Reachable d180 |
|---|---|---|---|---|---|---|---|
| Notification minimalist | Today's default (top 5) | 2.13 | +7.3 | 24.0% | 84% | 19% | 19% |
|  | Fatigue-aware · cap 2 + batching + email | 0.88 | +11.1 | 27.5% | 88% | 78% | 93% |
| | Logged-out look-alike (no pushes) | 0 | 0 | 22.5% | 80% | — | — |
| Casual browser | Today's default (top 5) | 3.49 | +18.2 | 46.1% | 97% | 58% | 58% |
|  | Fatigue-aware · cap 4 + state budget + batching + email | 1.47 | +20.2 | 48.2% | 98% | 91% | 98% |
| | Logged-out look-alike (no pushes) | 0 | 0 | 37.7% | 93% | — | — |
| Active contributor | Today's default (top 5) | 4.42 | +29.6 | 76.3% | 100% | 83% | 83% |
|  | Fatigue-aware · cap 5 + batching + email | 2.79 | +29.8 | 77.6% | 100% | 94% | 99% |
| | Logged-out look-alike (no pushes) | 0 | 0 | 60.8% | 99% | — | — |

Reachable counts people who still have push on or still accept the email digest. The answer depends on the user. For minimalists, sending less wins outright on every metric. For active contributors, today's default is as good on six-month lift, and the gain is reach: 16 more people in 100 can still be pushed or emailed at day 180.

The retention angle: a 30-day test cannot see this. For the minimalist, D30 retention is 87% under today's default and 88% under the recommended policy. By D90 it is 84% against 88%, because the default has burned most of its push permission by then.

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
- One push slot per candidate per day; no send-time optimisation yet. Email is a single digest every third day, only for people who turned push off.
- The uplift-aware policy only knows a person's long-run organic rate. A real one is a model trained on a random holdout, as Instagram did; here it is measured as a next step, not shipped.
- Personas are fixed segments. A production system would estimate tolerance per user and update it online.

Chloe Tan · October 2026
