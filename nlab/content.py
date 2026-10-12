"""Fake but plausible notification copy for the lived-experience view."""
import numpy as np

from .params import COMMUNITIES

ADJ = ["sleepy", "quiet", "brave", "lucky", "salty", "mellow", "rusty", "witty", "cosmic", "humble"]
NOUN = ["maple", "otter", "kettle", "falcon", "pebble", "noodle", "lantern", "cactus", "badger", "comet"]

POSTS = {
    "sourdough_lab": ["My starter finally doubled in 6 hours", "Crumb shot: 78% hydration, cold retard overnight", "Why is my loaf flat after the bulk ferment?"],
    "bayarea_trails": ["Mission Peak at sunrise, worth the 5am alarm", "Quiet weekday hikes near San Jose?", "Rancho San Antonio parking tips"],
    "ev_owners": ["Home charger install cost breakdown (Bay Area, 2026)", "Winter range loss: real numbers from a year of logs", "Is a 240V outlet enough?"],
    "indoor_jungle": ["Monstera finally put out a fenestrated leaf", "Brown tips on my calathea, what am I doing wrong?", "Cheap grow lights that actually work"],
    "budget_travel": ["Two weeks in Portugal for under $1,500", "Points vs cash for domestic flights this fall", "Best carry-on that fits budget airlines"],
    "learn_python": ["Finally understood decorators, here is how", "Pandas vs Polars for a 2GB CSV?", "My first script that saved me an hour a week"],
    "frugal_kitchen": ["$30 a week meal prep that does not get boring", "What to do with a whole bag of lentils", "Freezer soups ranked"],
    "mech_keebs": ["First build: lubed linears, gasket mount", "Is a 65% layout hard to get used to?", "Budget keycaps that do not feel cheap"],
}
REPLIES = ["Counterpoint: it depends on your setup", "This is exactly what I needed today, thanks", "Did you try lowering the temperature?",
           "Saving this for the weekend", "I had the same problem, here is what fixed it", "Can you share the link to that?",
           "Respectfully, I think you have it backwards", "Updated: tried it and it worked"]


def user(rng):
    return f"u/{rng.choice(ADJ)}_{rng.choice(NOUN)}{rng.integers(10, 99)}"


def make(type_key: str, rng: np.random.Generator) -> dict:
    com = str(rng.choice(list(COMMUNITIES)))
    post = str(rng.choice(POSTS[com]))
    if type_key == "reply_post":
        return {"title": f"{user(rng)} replied to your post", "body": f"“{rng.choice(REPLIES)}”", "community": com}
    if type_key == "reply_comment":
        return {"title": f"{user(rng)} replied to your comment", "body": f"“{rng.choice(REPLIES)}”", "community": com}
    if type_key == "milestone":
        n = int(rng.choice([10, 25, 50, 100]))
        return {"title": f"Your comment reached {n} upvotes", "body": f"On “{post}”", "community": com}
    if type_key == "trending_joined":
        return {"title": f"Trending in r/{com}", "body": post, "community": com}
    if type_key == "digest":
        return {"title": "Your daily digest", "body": f"{post} and {int(rng.integers(4, 12))} more from your communities", "community": com}
    if type_key == "recommended":
        return {"title": "Recommended for you", "body": post, "community": com}
    return {"title": f"Join r/{com}?", "body": f"{COMMUNITIES[com]} members. People like you are reading “{post}”", "community": com}


def times(k: int, rng: np.random.Generator) -> list[str]:
    mins = np.sort(rng.integers(8 * 60, 22 * 60, k))
    return [f"{m // 60}:{m % 60:02d}" for m in mins]
