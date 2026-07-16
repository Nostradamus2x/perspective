"""Find one story covered by several outlets at once.

Two articles count as the same story only if they are both semantically close
AND published close together in time. Similarity alone is not enough: in
testing, "Pappu Yadav humiliated at opposition rally" (OpIndia) and "Pappu
Yadav's Supporters Block Roads" (NDTV) scored 0.686 despite being different
events six months apart -- the same score as a genuine same-day match. Time is
what separates the two cases.
"""

import calendar
import time
from dataclasses import dataclass
from itertools import combinations
from urllib.parse import urlsplit, urlunsplit

import feedparser
import numpy as np
from sentence_transformers import SentenceTransformer

SOURCES = [
    ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss", "center"),
    ("NDTV", "https://feeds.feedburner.com/ndtvnews-latest", "center"),
    ("Scroll.in", "https://feeds.feedburner.com/ScrollinArticles.rss", "left"),
    ("OpIndia", "https://www.opindia.com/feed/", "right"),
    ("Altnews", "https://www.altnews.in/feed/", "factcheck"),
]

MODEL_NAME = "all-mpnet-base-v2"
PER_SOURCE = 40

# Calibrated against pairs verified by hand:
#   0.686  IRCTC booking site       NDTV/OpIndia    same story
#   0.614  Wangchuk hunger strike   Hindu/Scroll    same story
#   0.588  two unrelated murders    Hindu/NDTV      same genre, different event
# Real matches sit at 0.61+; by 0.59 the matcher is pairing genre, not event.
MIN_SIMILARITY = 0.60

# The Hindu publishes ~10 articles/hour and its feed holds only ~6 hours, while
# Altnews holds ~307. Widening this does not find more stories, it just admits
# same-entity false positives.
MAX_SPAN_HOURS = 48

_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def normalise_url(url):
    """Strip query and fragment so the same article dedupes across polls.

    Scroll serves ?utm_source=rss and NDTV appends #pfrom= fragments, so the
    raw URL is not stable between fetches.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path.rstrip("/"), "", ""))


def published_utc(entry):
    """Epoch seconds, or None.

    feedparser always hands back published_parsed in UTC. time.mktime() reads a
    struct as local time, so app.py's parse_time() is wrong by the local UTC
    offset (5 hours on this machine). calendar.timegm() is the UTC counterpart.
    """
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    return calendar.timegm(parsed) if parsed else None


@dataclass
class Article:
    source: str
    bias: str
    title: str
    url: str
    published: float

    @property
    def when(self):
        return time.strftime("%d %b %Y, %H:%M UTC", time.gmtime(self.published))


@dataclass
class Cluster:
    articles: list
    min_similarity: float

    @property
    def coverage(self):
        return len(self.articles)

    @property
    def span_hours(self):
        stamps = [a.published for a in self.articles]
        return (max(stamps) - min(stamps)) / 3600


def fetch_articles(per_source=PER_SOURCE):
    """Pull the current window from every feed. Articles without a usable
    timestamp are dropped -- they cannot be time-checked, and admitting them
    would reintroduce the false positives the time filter exists to stop."""
    articles = []
    for name, url, bias in SOURCES:
        feed = feedparser.parse(url)
        for entry in feed.entries[:per_source]:
            stamp = published_utc(entry)
            link = normalise_url(entry.get("link"))
            if stamp is None or not link or not entry.get("title"):
                continue
            articles.append(Article(name, bias, entry.title.strip(), link, stamp))
    return articles


def embed(articles):
    vectors = get_model().encode([a.title for a in articles],
                                 normalize_embeddings=True,
                                 show_progress_bar=False)
    return np.asarray(vectors)


def _grow(seed, sim, articles, min_similarity, max_span):
    """Greedily extend a seed article with one article per other source,
    keeping every pairwise similarity above the floor and the whole group
    inside the time window."""
    group = [seed]
    sources = {articles[seed].source}
    while True:
        best_score, best_idx = None, None
        for j in range(len(articles)):
            if articles[j].source in sources:
                continue
            if any(sim[j, g] < min_similarity for g in group):
                continue
            stamps = [articles[g].published for g in group] + [articles[j].published]
            if (max(stamps) - min(stamps)) / 3600 > max_span:
                continue
            score = min(sim[j, g] for g in group)
            if best_score is None or score > best_score:
                best_score, best_idx = score, j
        if best_idx is None:
            return group
        group.append(best_idx)
        sources.add(articles[best_idx].source)


def find_clusters(articles, vectors, min_similarity=MIN_SIMILARITY,
                  max_span=MAX_SPAN_HOURS, limit=5):
    """Stories ranked by how many outlets covered them, then by how tightly.

    Scored on the *minimum* pairwise similarity, not the mean. A mean lets two
    real matches launder three unrelated headlines into a passing group -- which
    is how app.py currently pairs a Kashmir editorial with a Noida building fire
    and calls it the story of the day.
    """
    if not articles:
        return []
    sim = vectors @ vectors.T

    candidates = []
    for seed in range(len(articles)):
        group = _grow(seed, sim, articles, min_similarity, max_span)
        if len(group) < 2:
            continue
        floor = min(sim[a, b] for a, b in combinations(group, 2))
        candidates.append((len(group), float(floor), sorted(group)))

    candidates.sort(key=lambda c: (-c[0], -c[1]))

    clusters, claimed = [], set()
    for _, floor, group in candidates:
        if any(i in claimed for i in group):
            continue
        claimed.update(group)
        clusters.append(Cluster([articles[i] for i in group], floor))
        if len(clusters) >= limit:
            break
    return clusters


def top_stories(limit=5):
    articles = fetch_articles()
    if not articles:
        return []
    return find_clusters(articles, embed(articles), limit=limit)


if __name__ == "__main__":
    found = top_stories()
    if not found:
        print("No story cleared the bar.")
    for n, cluster in enumerate(found, 1):
        print(f"\n[{n}] {cluster.coverage} of {len(SOURCES)} sources "
              f"| min similarity {cluster.min_similarity:.3f} "
              f"| span {cluster.span_hours:.1f}h")
        for article in cluster.articles:
            print(f"    {article.source:11} {article.title[:70]}")
            print(f"    {'':11} {article.when}")
