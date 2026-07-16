# Methodology — `single`

A weekly digest of stories that several English Indian TV channels covered, with
per-channel transcripts and a notes field. Built to feed a weekly Substack column
about how broadcasters frame the same story differently.

TV only. No newspapers.

Every number here was measured against live data, not estimated. Where a design
choice was made, the measurement that forced it is given. Several of these
measurements overturned an earlier conclusion in this document's own history;
those reversals are recorded rather than quietly edited out, because the way they
failed is the useful part.

---

## 1. Pipeline

```
YouTube Data API  ->  SQLite  ->  transcripts  ->  cluster (2 tiers)  ->  Flask
   tv_ingest.py       store.py    tv_ingest.py     common_story.py      app_single.py
```

| File | Role |
| --- | --- |
| `tv_ingest.py` | YouTube API + transcript fetch into SQLite. Idempotent; rerun freely. |
| `store.py` | SQLite: `videos`, `comments`. |
| `common_story.py` | Two-tier clustering. Reads the DB, never fetches. |
| `app_single.py` | Flask UI, port 8081. |

```bash
venv/bin/python tv_ingest.py --days 7    # populate (minutes; rerun for pending)
venv/bin/python app_single.py            # serve :8081
```

Ingestion is a separate step because a week of transcripts takes minutes to
fetch. It must never happen inside a request.

---

## 2. Channels

| Channel | Status |
| --- | --- |
| CNN-News18 | ✅ 6/8 non-live had transcripts |
| WION | ✅ 7/8 |
| Republic | ✅ 4/8 |
| NewsX | ✅ 8/8 |
| India Today | ✅ 5/8 |
| **Times Now** | ❌ **0/8 — captions disabled at channel level** |

Times Now is excluded permanently. Captions are the uploader's setting; no API
key, account, or permission enables them on someone else's channel.

Channel IDs are resolved via the Data API's `search` endpoint, **not** by
scraping `@handles`. Handle scraping produced two wrong answers: `@MirrorNow`
returned Times Now's channel ID, and `@RepublicWorld` returned a Republic channel
that had not posted in 84 days. Both were silently wrong and would have poisoned
everything downstream.

Volume is large — 2,958 videos across 5 channels in **3 days**, India Today alone
posting ~295/day.

---

## 3. Live streams must be filtered, and this is not a detail

News channels stream constantly. **Live streams have no captions.**

```
India Today:  32 of 50 recent uploads were live
Republic:     18 of 50
CNN-News18:   27 of 50
```

`tv_ingest.py` stores live videos flagged and the matcher ignores them.

**This is the single biggest trap in the whole tool.** An earlier version of this
document concluded that four of six channels disabled captions, and that TV-only
was therefore dead. That conclusion was false. It came from sampling each
channel's *five most recent uploads*, which for a news channel are
overwhelmingly live streams. The measurement was of "recently live," recorded as
"captions disabled."

Re-testing against non-live uploads only, five of six channels work.

### The API's `caption` field cannot be used for this

`videos.list` returns `contentDetails.caption`. It is useless here:

```
India Today: API reports caption=true on 0 of 50 uploads
             ...while transcripts fetch successfully from that channel
```

The field only counts **manually uploaded** caption tracks. It is blind to the
auto-generated ASR captions this tool actually uses. Trusting it nearly
confirmed the live-stream error a second time, from an independent direction.

The only reliable test is to try the fetch.

---

## 4. Titles, not transcripts

Matching runs on segment **titles**. Transcripts are stored, displayed, and are
what you read — but they are not what the matcher compares.

Measured over 1,067 cross-channel pairs:

| Corpus | median | p90 | p99 | max | signal/noise |
| --- | --- | --- | --- | --- | --- |
| **Titles** | 0.149 | 0.306 | 0.621 | 0.939 | **6.3×** |
| Transcripts | 0.183 | 0.416 | 0.683 | 0.858 | 4.7× |

Titles win on both ends: lower noise floor, higher ceiling. Transcripts share
news-register filler — anchor intros, "joining us now", ad reads — which lifts
the floor without adding signal. And `all-mpnet-base-v2` caps at 384 tokens
(~1,536 chars), so on a median 2,171-char transcript the model reads about 66%
regardless.

This reverses an earlier judgement. Titles were first dismissed as SEO noise that
bundles stories — `"Iran's Electronic Warfare | India-UK FTA | Anil Menon's ISS
Mission"` is one video covering three unrelated stories. That is true **of live
bulletins**. Non-live per-story segments carry clean, entity-rich titles. Once
live streams are filtered, the objection disappears with them.

### Title cleaning

`clean_title()` takes the **longest** pipe-delimited segment, not the first, then
strips channel branding and a leading `Topic:` label.

Longest, because titles put the substance in either position:

```
"US-Iran War: Inside Tehran's Missile Arsenal | WION"   -> substance first
"US-IRAN WAR | Trump Declares EMERGENCY From Whitehouse" -> substance second
```

An earlier cleaner took text before the first pipe and turned the second into
`"US-IRAN WAR"` — the noise, with the story deleted.

---

## 5. Two tiers

Both are emitted, ranked separately, because they answer different questions.

| Tier | Floor | Window | Question |
| --- | --- | --- | --- |
| **Event** | 0.68 | 48h | Did several channels report *this specific incident*? |
| **Topic** | 0.60 | 7 days | Did several channels cover *this running story*? |

### Why the topic tier exists

In a live sample, five channels ran Iran-war segments: a missile-arsenal
explainer, a drone shootdown, blasts on Hengam Island, the Strait of Hormuz, an
interview. Every pair scored 0.55–0.77 — genuinely related, genuinely not the
same event.

At the event threshold that entire cluster is rejected, and the digest's top
story becomes a two-channel NASA press release. **The war is the story worth
writing about.** The event tier cannot see it, by construction.

The topic tier is not a looser event tier. It is the one that finds ongoing
stories, which is most of what a weekly column covers.

### Calibrating 0.68

Every cross-channel pair above 0.55 was read by hand:

| Score | Pair | Verdict |
| --- | --- | --- |
| 0.939 | ISS astronaut Anil Menon — CNN-News18 / Republic | same event ✅ |
| 0.904 | Tamil Nadu custodial death — NewsX / India Today | same event ✅ |
| 0.684 | 'Republic of Balochistan' video — Republic / NewsX | same event ✅ |
| 0.667 | missile arsenal / Amirahmadi interview — WION / India Today | same war, **different segments** ❌ |

The boundary is a **0.017 gap**. That is tight, and it is a judgement from four
pairs, not a tuned parameter. It sits higher than the 0.60 that works for
newspaper headlines because TV titles share formulaic prefixes that inflate
similarity between unrelated segments; `clean_title()` strips those to widen it.

---

## 6. Minimum pairwise, never mean

Groups are scored on the **lowest** pairwise similarity among members.

A mean lets two real matches launder three unrelated segments into a passing
group. If the claim is "these channels all covered one story," every pair must
hold — which is a minimum, not an average.

(`app.py` on `main` uses a mean over 6 pairs at a 0.30 floor. Its live output
pairs a Kashmir editorial with a Noida building fire, a citizenship essay, a
murder conviction, and a Hardoi fact-check, scores 0.412, and ships it as
"Highlight of the Day.")

---

## 7. Time

Similarity alone cannot identify a story. Two pairs from testing, identical
scores, opposite meanings:

```
0.686  NDTV / OpIndia : IRCTC ticket booking   — same day       ✅ same story
0.686  NDTV / OpIndia : Pappu Yadav            — 6 months apart ❌ different events
```

No threshold separates these, because the false match scores exactly as high as
the true one. Publication time is the only discriminator.

Consequently: segments without a parseable timestamp are dropped, and timestamps
use `calendar.timegm()`. `time.mktime()` reads a UTC struct as local time — the
bug in `app.py:83` that makes every clock on `main` 5 hours wrong.

---

## 8. Clustering

Greedy, seeded from every segment:

1. Seed with segment *i*.
2. Repeatedly add the segment — from a channel not yet in the group — maximising
   minimum similarity to the group, subject to every pair ≥ floor and total span
   ≤ window.
3. Rank by channel count, then tightness.
4. Emit non-overlapping groups. Event tier runs first; topic tier excludes what
   it consumed.

Greedy is not optimal, but it is not the bottleneck: **0.06s for 343 segments**,
scaling as O(n²), so ~4.6s at 3,000. The cost is embedding and transcript
fetching, not the search.

---

## 9. Known limits

**Five channels, all English.** Hindi is out — `all-mpnet-base-v2` cannot read
it. A headline and its exact Hindi translation score **0.265**, while two
*unrelated* English headlines score 0.301. One test pair scored **-0.029**. Aaj
Tak and ABP need a multilingual model, which would invalidate every threshold in
section 5.

**Not on-air coverage, strictly.** These are the segments a channel chose to
upload with captions enabled. A full 9pm debate that never gets clipped is
invisible. Whisper over downloaded audio would reach it; that means downloading
YouTube media, against their ToS, and real compute.

**The 0.017 event boundary is narrow.** Four hand-read pairs set it. It will
misfire. The topic tier is more forgiving and probably more useful week to week.

**Transcript fetching is capped at 500/run** and takes minutes. A full week needs
several passes. It costs no API quota (it scrapes captions) but it is the slow
step. Failures are recorded as `''` rather than left NULL so genuinely
caption-less videos are never retried.

**Quota.** Free tier is 10,000 units/day. `playlistItems` and `videos` cost 1 per
50; `search` costs 100. A daily ingest across 5 channels for 7 days is a few
hundred units.

---

## 10. Environment

```bash
venv/bin/python ...     # NOT .venv/ -- that exists and is an empty stub
```

Requires `.env` with `YOUTUBE_API_KEY` (see `.env.example`). `.env` is gitignored;
this repo is public.

`debug=True` breaks `app_single.py`: Flask's reloader re-imports the module and
torch raises `NotImplementedError: Cannot copy out of meta tensor` on the next
encode. It is pinned off, with the model warmed at startup instead.
