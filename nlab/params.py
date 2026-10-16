"""Model parameters. Illustrative, not fitted to any company's logs.

Calibration targets (status-quo policy, 180 days), chosen to sit inside
publicly reported ranges for consumer-app push:
  - push open rates in the low single digits for broad sends, higher for replies
  - a meaningful minority of users disabling push over six months
"""

HORIZON_DAYS = 180
USERS_PER_CONFIG = 3000
VALIDATION_USERS = 4500
TRAIN_SEED = 101
VALIDATION_SEED = 202

STATUS_QUO = {"kind": "volume_first", "cap": 5}
CAPS = [1, 2, 3, 4, 5, 6]
THRESHOLDS = [0.22, 0.30, 0.38, 0.46]
UPLIFT_THRESHOLDS = [0.01, 0.02, 0.03, 0.05]  # uplift scores are relevance x open chance x (1 - would-visit-anyway)
LAMBDA = 0.6  # irritation cost weight in the fatigue-aware score

# Email digest for people who turned push off (LinkedIn ATC-style channel fallback).
# Opens are rarer than push, it irritates less, and it has its own unsubscribe.
EMAIL = {"every": 3, "open_mul": 0.45, "annoy": 0.5, "unsub_per_ignore": 0.012}

# Per-state budget (Pinterest-style): core users come anyway, so halve their cap;
# dormant users are where a push adds most, so lower their bar a little.
STATE = {"core_days": 10, "dormant_bar_relief": 0.06}   # over a 14-day window

# Batching: fold two or more unsent pool candidates into one digest push.
BATCH = {"bonus": 0.08}

# base: mean relevance; annoy: fatigue added when ignored (relative);
# value: how much an open is worth in engagement terms; supply: where candidates come from
TYPES = [
    {"key": "reply_post", "label": "Reply to your post", "base": 0.80, "annoy": 0.55, "value": 1.3, "supply": "reply"},
    {"key": "reply_comment", "label": "Reply to your comment", "base": 0.70, "annoy": 0.65, "value": 1.2, "supply": "reply"},
    {"key": "milestone", "label": "Upvote milestone", "base": 0.52, "annoy": 0.8, "value": 0.8, "supply": "reply"},
    {"key": "trending_joined", "label": "Trending in a joined community", "base": 0.40, "annoy": 1.0, "value": 0.9, "supply": "pool"},
    {"key": "digest", "label": "Daily digest", "base": 0.36, "annoy": 0.9, "value": 0.8, "supply": "pool"},
    {"key": "recommended", "label": "Recommended post", "base": 0.28, "annoy": 1.25, "value": 0.7, "supply": "pool"},
    {"key": "new_community", "label": "Community suggestion", "base": 0.20, "annoy": 1.4, "value": 0.5, "supply": "pool"},
]
TYPE_KEYS = [t["key"] for t in TYPES]

# Daily candidate supply (Poisson means). Reply-type supply scales with contribution.
REPLY_RATE = {"reply_post": 0.55, "reply_comment": 0.9, "milestone": 0.35}
POOL_RATE = {"trending_joined": 1.6, "digest": 1.0, "recommended": 2.2, "new_community": 0.8}

# organic: daily chance of opening the app unprompted
# contribution: multiplier on reply supply
# tolerance: fatigue added per ignored push (before type annoy)
# dnd: fatigue level past which the person silences the rest of the day
# revoke_k: scale of the daily chance of turning push off (x fatigue^2)
# open_mul: willingness to open a relevant push
PERSONAS = {
    "minimalist": {
        "label": "Notification minimalist",
        "blurb": "Turns off notifications for almost every app. Rarely posts, so few pushes are replies. Low tolerance for noise and quick to reach for Do Not Disturb.",
        "organic": 0.22, "contribution": 0.12, "tolerance": 0.085, "dnd": 0.70,
        "revoke_k": 0.006, "open_mul": 0.20,
    },
    "casual": {
        "label": "Casual browser",
        "blurb": "Opens the app a few times a week and comments now and then. Some pushes are replies; most are recommendations.",
        "organic": 0.38, "contribution": 0.45, "tolerance": 0.055, "dnd": 0.75,
        "revoke_k": 0.003, "open_mul": 0.24,
    },
    "contributor": {
        "label": "Active contributor",
        "blurb": "Posts and comments daily. Many pushes are replies they want, so they put up with a lot before muting.",
        "organic": 0.62, "contribution": 1.6, "tolerance": 0.035, "dnd": 0.86,
        "revoke_k": 0.0025, "open_mul": 0.27,
    },
}

# Dynamics shared by everyone
OVERNIGHT_RECOVERY = 0.80   # fatigue multiplies by this each night
OPEN_RELIEF = 0.75          # fatigue multiplies by this after an open
ORGANIC_FATIGUE_DRAG = 0.30 # organic visit chance falls by up to 30% at full fatigue
HABIT_BOOST = 0.06          # each open in the last 7 days (max 3) lifts organic chance by 6%
HETEROGENEITY = 0.35        # lognormal sigma for per-person multipliers

COMMUNITIES = {
    "sourdough_lab": "412k", "bayarea_trails": "268k", "ev_owners": "1.1M",
    "indoor_jungle": "903k", "budget_travel": "2.4M", "learn_python": "1.6M",
    "frugal_kitchen": "740k", "mech_keebs": "1.3M",
}
