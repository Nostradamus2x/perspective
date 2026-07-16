# Methodology — Perspective (`main`)

Perspective is two systems that share a folder and nothing else:

- an **offline pipeline** that scraped news archives and trained a stance
  classifier, last run July 2025, invoked by hand;
- a **live web app** (`app.py`) that fetches RSS feeds and shows how outlets of
  different leanings covered the same story.

The live app does not read anything the offline pipeline produced. No labels, no
CSVs, no trained model. Understanding that is the single most important thing
about this codebase.

Every number below was measured against the code and data as they stand, not
estimated.

---

## 1. Live app — `app.py`

```
5 RSS feeds  →  bucket by bias  →  embed headlines  →  best quartet  →  Jinja2
```

| Source | Bias tag | URL |
| --- | --- | --- |
| The Hindu | center | `thehindu.com/news/national/feeder/default.rss` |
| NDTV | center | `feeds.feedburner.com/ndtvnews-latest` |
| Scroll.in | left | `feeds.feedburner.com/ScrollinArticles.rss` |
| OpIndia | right | `opindia.com/feed/` |
| Altnews | factcheck | `altnews.in/feed/` |

**Bias is asserted, never computed.** Scroll.in is `"left"` because that string
is hardcoded in `NEWS_SOURCES`. Every Scroll.in article is left. The app performs
no classification at runtime. What it actually computes is *similarity*.

Note that The Hindu and NDTV are both tagged `center`, so they compete for one
slot in the quartet and only one ever appears.

**Method.** Headlines (not article text) are embedded with
`sentence-transformers/all-mpnet-base-v2`. The app then brute-forces every
(left × center × right × factcheck) combination, computes 6 pairwise cosine
similarities per combination, and keeps the quartet with the highest **mean**.
A quartet is shown if its mean clears **0.30**.

**Caching.** Flask-Caching, filesystem backend, 10-minute TTL. Nothing is
persisted — each expiry discards the fetched articles entirely.

---

## 2. Offline pipeline

Run by hand, in order. Not wired to the app.

| Stage | Script | Method |
| --- | --- | --- |
| Scrape headlines | `dbcreate_ndtv.py` | `requests` + BeautifulSoup over `archives.ndtv.com/articles/{year}-{month}.html`, monthly pages, 2024–2025 |
| Scrape headlines | `dbcreate_opindia.py` | 5 pages of `opindia.com/latest-news/`, 2s delay |
| Fetch body text | `headline_to_articles.py` | `newspaper3k` per URL, `sleep(10)` |
| Clean | `preprocess.py` | lowercase, strip URLs/HTML/punctuation, `langdetect`, NLTK stopwords + WordNet lemmatiser |
| Classify | `process.py` | TF-IDF (5,000 features) → LogisticRegression (`class_weight='balanced'`), 80/20 split |
| Visualise | `visual.py`, `visual_st.py` | matplotlib bar charts, wordclouds; Streamlit variant |

Hindi support exists in `preprocess.py` but is **commented out** — the
`indic_tokenize` import is disabled, so the `language == 'hi'` branch would raise
`NameError` if reached.

---

## 3. Data as it actually is

`combined_articles_with_labels.csv` — 5,072 rows, the pipeline's terminal output:

```
label_type:  predicted 4,882    manual 190
label:       Neutral         4,803   (94.7%)
             Pro-Government    199
             Anti-Government     70
outlet:      NDTV            4,948
             OpIndia           124
```

**The classifier is degenerate.** A function returning `"Neutral"`
unconditionally scores 94.7% on this. There are only **190 manual labels** across
three classes, against 5,000 TF-IDF features. The other 4,882 labels are the
model's own output.

**The two outlets do not overlap in time:**

```
NDTV    : 2025-01 .. 2025-01   (January 2025; dates are month-granular)
OpIndia : 09/07/25 .. 23/07/25 (July 2025)
```

Six months apart. This is not a comparison of two outlets on shared events — it
is January NDTV stapled to July OpIndia. Any stance contrast drawn between them
is uncontrolled.

**Disk.** 171 MB of CSV to hold a 5,072-row table. Each pipeline stage rewrote
the entire table with one column added:

```
ndtv_articles_cleaned (25.4MB) → _labeled (25.4MB) → _with_labels (25.5MB)
combined_articles_labeled (26.6MB) → _with_labels (26.7MB)
```

~127 MB is duplication. `cleaned_text` is a further 10.5 MB derived from
`article_text` in the same file — the output of a function stored beside its
input. All of it is tracked in git, so `.git` is 209 MB.

---

## 4. Known defects

**`numpy` is imported but not declared.** Commit `de8f738` ("Removed numpy")
dropped it from `requirements.txt`, but `app.py:7` still imports it and lines
159–164 call `np.dot` and `np.linalg.norm`. A clean install raises `ImportError`.

**Timestamps are wrong by the local UTC offset.** `parse_time()` (`app.py:83`)
does `datetime.fromtimestamp(time.mktime(published_parsed))`. feedparser always
returns `published_parsed` in UTC; `time.mktime` interprets a struct as *local*
time. Measured on the dev machine:

```
feed value : Thu, 16 Jul 2026 04:47:02 +0530
app.py     : 16 Jul 2026, 12:17 AM
correct    : 15 Jul 2026, 07:17 PM      ← 5 hours off
```

The fix is `calendar.timegm(published_parsed)`.

**The clean step destroys 92% of the scrape.** This is why the dataset is 5,000
rows rather than 57,000:

```
ndtv_headlines.csv        69,053 rows   67,971 unique URLs   ← raw scrape, fine
ndtv_headlines_clean.csv  66,036 rows    5,000 unique URLs   ← 61,036 rows have url = NULL
```

The scrape worked. The clean step nulled 62,971 URLs while keeping the rows, so
`headline_to_articles.py` could only fetch text for what was left. Of the raw
67,971 URLs, 57,537 match NDTV's real article pattern; the remaining ~10,434 are
navigation and social links, because `dbcreate_ndtv.py` grabs every `<li>` on the
page.

**The 0.30 threshold is above noise but far below meaning.** Over 4,000 random
quintets, mean pairwise similarity is 0.152 and p99 is 0.279 — so 0.30 is
genuinely better than random. But real same-story matches sit at 0.61+, and by
0.59 the matcher is pairing genre rather than event. Combined with a **mean**
across 6 pairs, two decent matches can carry four unrelated headlines. Live
output at the time of writing, mean 0.412, passing the threshold and shipped as
"Highlight of the Day":

```
The Hindu   Fulfil the promise: On restoring Statehood to Jammu and Kashmir
NDTV        "Even Ambulance Can't Pass": Inside Noida Lane Where 2 Died In Fire
Scroll.in   Anand Teltumbde: India's citizenship riddle demands documents…
OpIndia     Tahir Hussain and five others convicted in Ankit Sharma murder…
Altnews     Hardoi victim's statement falsely linked to Rajasthan 'gangrape'
```

Five unrelated stories, presented as one.

**Similarity alone cannot identify a story.** Searching 613,552 cross-outlet
pairs in the archive found NDTV/OpIndia headlines about Pappu Yadav six months
apart scoring 0.686 — identical to a genuine same-day IRCTC match. Publication
time is the missing discriminator, and the app has never used it. See the
`single` branch for a matcher that does.

**Combinatorics.** The quartet search is a 4-deep nested loop — 40 articles per
source is 2.56M combinations × 6 cosine ops, recomputed with `np.linalg.norm` on
every iteration rather than normalising once.

**`requirements.txt` is ~50 packages of dead weight** — the agate family,
Jupyter/IPython, matplotlib, seaborn, sympy — none imported by `app.py`.
`Flask-SQLAlchemy` is declared and never used.

---

## 5. Environment

`venv/` is the working environment. `.venv/` also exists and is an empty stub —
it does not even have feedparser. `runtime.txt` pins python-3.11.9 for Render;
both local venvs are 3.13.

```bash
venv/bin/python app.py     # :8080
```
