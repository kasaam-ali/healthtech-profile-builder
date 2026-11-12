"""Synthetic wellness-engagement dataset generator (fictional, non-sensitive).

No real people or patient data. Values come from a seeded numpy RNG.
"""
import csv
from pathlib import Path

import numpy as np

SEED = 42
N_ROWS = 2000
CHANNELS = ["email", "sms", "app"]
NUMERIC = ["age", "sessions_last_30d", "avg_session_minutes", "days_since_signup"]
BOOLEAN = ["reminders_opt_in"]
CATEGORICAL = ["preferred_channel"]
FEATURES = NUMERIC + BOOLEAN + CATEGORICAL
LABEL = "engaged_next_30d"
DATA_PATH = Path(__file__).parent / "data" / "wellness_engagement.csv"


def generate(n: int = N_ROWS, seed: int = SEED) -> list[dict]:
    rng = np.random.default_rng(seed)
    age = rng.integers(18, 86, n)
    sessions = rng.poisson(6, n).clip(0, 30)
    minutes = rng.gamma(2.0, 8.0, n).clip(1, 120).round(1)
    days = rng.integers(1, 1000, n)
    opt_in = rng.random(n) < 0.55
    channel = rng.choice(CHANNELS, n, p=[0.35, 0.25, 0.40])
    # Hidden fictional rule plus noise, so the task is learnable but not trivial.
    logit = (-2.2 + 0.28 * sessions + 0.03 * minutes + 0.9 * opt_in
             - 0.0012 * days + 0.4 * (channel == "app") + rng.normal(0, 1.0, n))
    label = (1 / (1 + np.exp(-logit)) > 0.5).astype(int)
    return [
        {"age": int(age[i]), "sessions_last_30d": int(sessions[i]),
         "avg_session_minutes": float(minutes[i]), "days_since_signup": int(days[i]),
         "reminders_opt_in": int(opt_in[i]), "preferred_channel": str(channel[i]),
         LABEL: int(label[i])}
        for i in range(n)
    ]


def write_csv(rows: list[dict], path: Path = DATA_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FEATURES + [LABEL])
        w.writeheader()
        w.writerows(rows)
    return path
