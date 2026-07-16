"""Group TV news segments that covered the same story.

Reads what tv_ingest.py cached; does not fetch. Emits two tiers:

  EVENT tier  -- the same specific incident, reported by several channels
  TOPIC tier  -- one ongoing story, covered from different angles

Both tiers matter because they answer different questions. In a live sample,
five channels ran Iran-war segments -- a missile-arsenal explainer, a drone
shootdown, blasts on Hengam Island, the Strait of Hormuz, an interview. At the
event threshold that whole cluster is rejected as "not the same story", and the
digest surfaces a two-channel NASA press release instead. The war is the story
worth writing about; the event tier alone cannot see it.

Matching is on TITLES, not transcripts. Measured over 1,067 cross-channel pairs:

    TITLES       median 0.149 | p90 0.306 | p99 0.621 | max 0.939
    TRANSCRIPTS  median 0.183 | p90 0.416 | p99 0.683 | max 0.858

Titles separate signal from noise by 6.3x, transcripts only 4.7x. Transcripts
share news-register filler -- anchor intros, "joining us now", ad reads -- which
lifts the floor, and the model reads only the first ~1,536 chars of one anyway.
Transcripts are still stored: they are what you read and write about.
"""

import calendar
import re
import time
from dataclasses import dataclass
from itertools import combinations

import numpy as np
from sentence_transformers import SentenceTransformer

import store

MODEL_NAME = "all-mpnet-base-v2"

# Calibrated by reading every cross-channel pair above 0.55:
#   0.939  ISS astronaut Anil Menon        CNN-News18 + Republic   same event
#   0.904  Tamil Nadu custodial death      NewsX + India Today     same event
#   0.684  'Republic of Balochistan' video Republic + NewsX        same event
#   0.667  missile arsenal / Amirahmadi    WION + India Today      SAME WAR, different segments
# The true/false boundary sits in a 0.017 gap -- tighter than the 0.60 that
# works for newspaper headlines, because TV titles share formulaic prefixes
# ("US-Iran War:", "Iran News |") that inflate similarity between unrelated
# segments. clean_title() strips those before encoding to widen it.
EVENT_SIMILARITY = 0.68
TOPIC_SIMILARITY = 0.60

# A single incident is reported within a couple of days. A running story is not,
# so the topic tier gets the whole window.
EVENT_SPAN_HOURS = 48
TOPIC_SPAN_HOURS = 24 * 7

_model = None

# Channel branding and hype markers, stripped because they are constant across
# every segment a channel posts -- similarity that carries no signal.
_NOISE = re.compile(
    r"\b(LIVE|WATCH|BREAKING|EXCLUSIVE|LATEST|FULL VIDEO|Latest News|"
    r"News LIVE|English News|Top Headlines?|NewsX|WION|Republic|India Today|"
    r"CNN[- ]?News18)\b", re.I)

# A leading "Topic: " label, e.g. "US-Iran War: Inside Tehran's ..."
_LABEL = re.compile(r"^[A-Za-z0-9'\-\s&]{3,28}:\s+")


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def clean_title(title):
    """Strip channel branding and topic labels from a video title.

    Takes the longest pipe-delimited segment rather than the first. Titles put
    the substance in either position -- "US-Iran War: Inside Tehran's Missile
    Arsenal | WION" leads with it, "US-IRAN WAR | Trump Declares EMERGENCY"
    trails with it -- and taking the first turns the second into "US-IRAN WAR",
    which is the noise with the story removed.
    """
    parts = [p.strip() for p in title.split("|") if p.strip()]
    text = max(parts, key=len) if parts else title
    text = _NOISE.sub("", text)
    text = _LABEL.sub("", text, count=1)
    text = re.sub(r"\s+", " ", text).strip(" :;-,")
    # If stripping ate the whole title, the original beats nothing.
    return text if len(text) >= 12 else re.sub(r"\s+", " ", title).strip()


@dataclass
class Segment:
    video_id: str
    channel: str
    title: str
    url: str
    published: float
    transcript: str

    @property
    def when(self):
        return time.strftime("%d %b, %H:%M UTC", time.gmtime(self.published))

    @property
    def match_text(self):
        return clean_title(self.title)


@dataclass
class Cluster:
    segments: list
    min_similarity: float
    tier: str

    @property
    def coverage(self):
        return len({s.channel for s in self.segments})

    @property
    def span_hours(self):
        stamps = [s.published for s in self.segments]
        return (max(stamps) - min(stamps)) / 3600


def load_segments(days=7):
    out = []
    for row in store.segments_since(days):
        stamp = calendar.timegm(time.strptime(row["published"], "%Y-%m-%dT%H:%M:%SZ"))
        out.append(Segment(row["video_id"], row["channel"], row["title"],
                           row["url"], stamp, row["transcript"]))
    return out


def embed(segments):
    vectors = get_model().encode([s.match_text for s in segments],
                                 normalize_embeddings=True,
                                 show_progress_bar=False)
    return np.asarray(vectors)


def _grow(seed, sim, segments, floor, max_span):
    group = [seed]
    channels = {segments[seed].channel}
    while True:
        best_score, best_idx = None, None
        for j in range(len(segments)):
            if segments[j].channel in channels:
                continue
            if any(sim[j, g] < floor for g in group):
                continue
            stamps = [segments[g].published for g in group] + [segments[j].published]
            if (max(stamps) - min(stamps)) / 3600 > max_span:
                continue
            score = min(sim[j, g] for g in group)
            if best_score is None or score > best_score:
                best_score, best_idx = score, j
        if best_idx is None:
            return group
        group.append(best_idx)
        channels.add(segments[best_idx].channel)


def find_clusters(segments, vectors, floor, max_span, tier, limit=5, exclude=()):
    """Stories ranked by channel coverage, then by tightness.

    Scored on the MINIMUM pairwise similarity, never the mean. A mean lets two
    real matches launder three unrelated segments into a passing group. If the
    claim is "these channels all covered one story", every pair must hold.
    """
    if not segments:
        return []
    sim = vectors @ vectors.T
    blocked = set(exclude)

    candidates = []
    for seed in range(len(segments)):
        if segments[seed].video_id in blocked:
            continue
        group = [i for i in _grow(seed, sim, segments, floor, max_span)
                 if segments[i].video_id not in blocked]
        if len({segments[i].channel for i in group}) < 2:
            continue
        low = min(sim[a, b] for a, b in combinations(group, 2))
        candidates.append((len({segments[i].channel for i in group}), float(low), group))

    candidates.sort(key=lambda c: (-c[0], -c[1]))

    clusters, claimed = [], set()
    for _, low, group in candidates:
        if any(i in claimed for i in group):
            continue
        claimed.update(group)
        clusters.append(Cluster([segments[i] for i in group], low, tier))
        if len(clusters) >= limit:
            break
    return clusters


def weekly_digest(days=7, limit=5):
    """Event-tier clusters first, then topic-tier over what is left."""
    segments = load_segments(days)
    if not segments:
        return [], [], 0
    vectors = embed(segments)
    events = find_clusters(segments, vectors, EVENT_SIMILARITY,
                           EVENT_SPAN_HOURS, "event", limit)
    used = {s.video_id for c in events for s in c.segments}
    topics = find_clusters(segments, vectors, TOPIC_SIMILARITY,
                           TOPIC_SPAN_HOURS, "topic", limit, exclude=used)
    return events, topics, len(segments)


if __name__ == "__main__":
    events, topics, total = weekly_digest()
    print(f"{total} segments in window\n")
    for label, clusters in (("EVENT", events), ("TOPIC", topics)):
        print(f"=== {label} tier: {len(clusters)} stories ===")
        for n, c in enumerate(clusters, 1):
            print(f"\n[{n}] {c.coverage} channels | min {c.min_similarity:.3f} "
                  f"| span {c.span_hours:.1f}h")
            for s in c.segments:
                print(f"    {s.channel:12} {s.title[:66]}")
        print()
