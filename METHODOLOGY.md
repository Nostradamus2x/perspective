# Methodology — `single`

A tool for finding one news story that several Indian outlets covered at the same
time, and annotating how each outlet framed it.

Every number in this document was measured against the live feeds on 15 Jul 2026,
not estimated. Where a design choice was made, the measurement that forced it is
given.

---

## 1. What the tool does

1. Polls five RSS feeds (40 articles each).
2. Embeds every **headline** into a vector.
3. Groups articles that are both semantically close **and** published close together.
4. Ranks groups by how many outlets covered the story.
5. Renders one comment box per outlet, persisted to SQLite.

Entry points:

| File | Role |
| --- | --- |
| `common_story.py` | Fetching, matching, clustering. Runnable standalone. |
| `store.py` | SQLite comment persistence. |
| `app_single.py` | Flask UI, port 8081. |
| `templates/single.html` | The page. |

---

## 2. Sources

| Source | Bias tag | Publication rate | Feed depth |
| --- | --- | --- | --- |
| The Hindu | center | ~10.0 articles/hour | 60 entries ≈ **6.0 hours** |
| NDTV | center | ~7.5 articles/hour | 100 entries ≈ 13.4 hours |
| Scroll.in | left | ~1.0 articles/hour | 100 entries ≈ 98.5 hours |
| OpIndia | right | ~0.4 articles/hour | 10 entries ≈ 27.1 hours |
| Altnews | factcheck | ~0.03 articles/hour | 10 entries ≈ 307 hours |

The bias tags are **asserted, not measured** — they are editorial judgements
hardcoded in `SOURCES`. The tool does not classify stance. It only reports which
outlets covered a story; interpreting the framing is the human's job, which is
what the comment boxes are for.

**These rates are the central constraint on the whole tool.** A 40-article window
covers about 4 hours of The Hindu but 307 hours of Altnews. The windows barely
overlap in time, which is why cross-outlet matches are rarer than intuition
suggests.

---

## 3. Headlines, not article text

All matching is on headlines. This is forced, not preferred:

| Source | Body text in RSS | What the model would actually see |
| --- | --- | --- |
| OpIndia | 20,132 chars | 1,536 chars — **7.6%** |
| Altnews | 6,382 chars | 1,536 chars — 24.1% |
| Scroll.in | 1,733 chars | 1,536 chars — 88.6% |
| NDTV | 186 chars | 186 chars |
| The Hindu | **0 chars** | nothing |

Two independent blockers:

- **The Hindu ships no body text in its feed at all.** Comparing text would
  require an HTTP fetch per article, per poll.
- `all-mpnet-base-v2` has `max_seq_length = 384` tokens (~1,536 chars). It
  truncates. "Comparing articles" would really mean comparing the first two
  paragraphs.

A headline is also the better unit on the merits: it is the outlet's own claim
about what the story *is*, which is exactly the question being asked.

---

## 4. Similarity threshold: 0.60

Cosine similarity over L2-normalised `all-mpnet-base-v2` embeddings.

Calibrated against pairs verified by reading them:

| Score | Pair | Verdict |
| --- | --- | --- |
| 0.686 | NDTV *"IRCTC Unveils New Ticket Booking Website"* / OpIndia *"Faster Tatkal bookings…"* | same story ✅ |
| 0.631 | Hindu *"Sonam Wangchuk hangs on to hunger strike"* / Scroll *"…urge Wangchuk to end…"* | same story ✅ |
| 0.588 | Hindu *"life imprisonment in Guntur dowry death"* / NDTV *"Man Gets Life Term For Killing Wife"* | same genre, **different event** ❌ |

Real matches sit at 0.61+. By 0.59 the matcher is pairing genre, not event.
0.60 is the boundary, and it is narrow — this is a judgement from three verified
pairs, not a tuned parameter.

### The noise floor is not the bar

Over 4,000 random quintets (one headline per source):

```
mean 0.152   p90 0.219   p99 0.279   p99.9 0.321   max 0.349
```

`app.py` uses a 0.30 threshold, which random beats only 0.4% of the time — so it
is genuinely above noise. **That is not the same as being meaningful.** 0.30 sits
far below where "same story" begins (~0.61). It answers "is this better than
random?" when the question is "is this the same event?"

---

## 5. Minimum pairwise, not mean

Groups are scored on the **lowest** pairwise similarity among their members.

`app.py` uses the mean across all pairs. Averaging lets two real matches launder
three unrelated headlines into a passing group. Its actual live output:

```
mean pairwise 0.412 — above its 0.30 threshold, shipped as "Highlight of the Day"

  The Hindu   Fulfil the promise: On restoring Statehood to Jammu and Kashmir
  NDTV        "Even Ambulance Can't Pass": Inside Noida Lane Where 2 Died In Fire
  Scroll.in   Anand Teltumbde: India's citizenship riddle demands documents…
  OpIndia     Tahir Hussain and five others convicted in Ankit Sharma murder…
  Altnews     Hardoi victim's hospital-bed statement falsely linked to Rajasthan…
```

Five unrelated stories. If a claim is "all these outlets covered one story," then
*every* pair must hold — which is the definition of a minimum, not a mean.

---

## 6. Time proximity: 48 hours

**This is the part `app.py` has never had, and it is not optional.**

Similarity cannot distinguish "same story" from "same person, different event".
Two pairs, identical scores, opposite meanings:

```
0.686  NDTV / OpIndia : IRCTC ticket booking website   — same day        ✅ same story
0.686  NDTV / OpIndia : Pappu Yadav                    — 6 months apart  ❌ different events
```

The second came from searching 613,552 cross-outlet pairs in the project's
archive. No threshold separates these two cases, because the false match scores
*exactly as high* as the true one. Publication time is the only discriminator.

Consequences:

- Articles without a parseable timestamp are **dropped**, not admitted. They
  cannot be time-checked, and admitting them reintroduces exactly the false
  positives this filter exists to stop.
- Timestamps must be correct. `app.py`'s `parse_time()` uses
  `time.mktime(published_parsed)`, which reads a UTC struct as local time and is
  wrong by the local UTC offset (5 hours on the dev machine). This tool uses
  `calendar.timegm()`. A time-aware matcher built on the old function would be
  matching on garbage.
- 48h is deliberately loose. Widening it does not find more stories; it admits
  same-entity false positives.

---

## 7. Clustering

Greedy, seeded from every article in turn:

1. Seed with article *i*.
2. Repeatedly add the article — from a source not yet in the group — that
   maximises the minimum similarity to the current group, subject to every
   pairwise similarity ≥ 0.60 and total time span ≤ 48h.
3. Stop when nothing qualifies.
4. Rank all groups by source count, then by minimum similarity.
5. Emit non-overlapping groups; no article appears in two clusters.

Greedy is not guaranteed optimal. It is used because an exhaustive search
confirmed there is nothing for a better algorithm to find (see below), so the
optimality gap is not currently the binding constraint. If cluster sizes grow
once ingestion widens the window, this is worth revisiting.

---

## 8. Known limits

**Two sources is the realistic ceiling today.** Exhaustive search over all
distinct-source triples in a live snapshot:

```
best 3-source group: min pairwise 0.454

  Scroll.in : Bhojshala case, SC fines…
  OpIndia   : Tahir Hussain convicted in Ankit Sharma murder…
  Altnews   : Hindutva flagbearers threaten Muslim judge…
```

Three unrelated events sharing a *theme*. 0.454 is below even the 0.588
same-genre-different-event mark. **No genuine 3-way story existed in the
snapshot.** This is structural, not a tuning problem: you are comparing 4 hours
of The Hindu against 12 days of Altnews and hoping they collide.

**Altnews will rarely participate.** ~0.7 articles/day, and its beat is debunking
specific viral claims rather than covering the news cycle. Requiring all five is
unrealistic even in principle.

**A snapshot is the wrong input.** The fix is not in the matching logic — it is
persistence. A rolling multi-day window gives a story a real chance to pick up
later coverage from a slower outlet. The matcher does not change; only its input
does. See `INGESTION.md` (not yet written) for that design.

**`debug=True` breaks this app.** Flask's reloader re-imports the module and
torch then raises `NotImplementedError: Cannot copy out of meta tensor` on the
next encode. `app_single.py` pins `debug=False` and warms the model at startup.

---

## 9. Reproducing the measurements

```bash
venv/bin/python common_story.py     # matcher, standalone
venv/bin/python app_single.py       # UI on :8081
```

Note `venv/` — **not** `.venv/`, which exists but is an empty stub without even
feedparser installed.
