"""Pull English TV news segments from YouTube into SQLite.

Run it repeatedly; it is idempotent. New videos land, known ones are skipped,
and transcripts already fetched are never refetched.

    venv/bin/python tv_ingest.py            # last 7 days
    venv/bin/python tv_ingest.py --days 14

Two things here are not obvious and were both found the hard way:

1. Live streams have no captions. They are stored but flagged, and the matcher
   ignores them. Sampling a channel's most recent uploads without this filter
   measures "recently live", not "captions disabled" -- India Today runs 32 of
   50 recent uploads live, which is enough to make a working channel look dead.

2. The API's contentDetails.caption field only reports *manually uploaded*
   caption tracks. It reads false for channels whose auto-generated captions
   fetch perfectly well, so it cannot be used to decide what to try.
"""

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi

import store

load_dotenv(dotenv_path=pathlib.Path(__file__).parent / ".env")

API = "https://www.googleapis.com/youtube/v3/"

# Resolved via the Data API, not by scraping @handles -- handle scraping gave
# wrong IDs (it returned Times Now's channel for @MirrorNow) and a Republic
# channel that had not posted in 84 days.
#
# Times Now is deliberately absent: 0 of 8 non-live uploads had captions. It
# disables them at the channel level, which no API key or setting works around.
CHANNELS = {
    "CNN-News18":  "UCef1-8eOpJgud7szVPlZQAQ",
    "WION":        "UC_gUM8rL-Lrg6O3adPW9K1g",
    "Republic":    "UCwqusr8YDwM-3mEYTDeJHzw",
    "NewsX":       "UCytSP0M0Jdnw6qIy3Y-nTig",
    "India Today": "UCYPvAwZP8pZhSMW8qs7cVCw",
}


def api(endpoint, **params):
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        sys.exit("YOUTUBE_API_KEY missing. Copy .env.example to .env and fill it in.")
    params["key"] = key
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = json.load(e)
        reason = body.get("error", {}).get("errors", [{}])[0].get("reason", "?")
        if reason in ("quotaExceeded", "dailyLimitExceeded"):
            sys.exit("YouTube API quota exhausted for today. Resets at midnight Pacific.")
        sys.exit(f"YouTube API error {e.code} ({reason}): "
                 f"{body.get('error', {}).get('message', '')}")


def uploads_playlist(channel_id):
    items = api("channels", part="contentDetails", id=channel_id).get("items")
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def recent_video_ids(playlist_id, days):
    """Page back through uploads until we pass the cutoff.

    A channel posting ~50/day needs several pages for a week. playlistItems
    costs 1 quota unit per page, so this stays cheap even at 14 days.
    """
    cutoff = time.time() - days * 86400
    ids, page = [], None
    while True:
        r = api("playlistItems", part="contentDetails", playlistId=playlist_id,
                maxResults=50, **({"pageToken": page} if page else {}))
        stop = False
        for item in r.get("items", []):
            published = item["contentDetails"].get("videoPublishedAt")
            if not published:
                continue
            when = time.mktime(time.strptime(published, "%Y-%m-%dT%H:%M:%SZ"))
            if when < cutoff:
                stop = True
                continue
            ids.append(item["contentDetails"]["videoId"])
        page = r.get("nextPageToken")
        if stop or not page:
            return ids


def store_videos(channel, video_ids):
    """videos.list carries liveStreamingDetails, which is how we spot streams."""
    added = 0
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        for v in api("videos", part="snippet,liveStreamingDetails",
                     id=",".join(chunk)).get("items", []):
            store.upsert_video(
                v["id"], channel, v["snippet"]["title"],
                v["snippet"]["publishedAt"],
                f"https://www.youtube.com/watch?v={v['id']}",
                is_live="liveStreamingDetails" in v,
            )
            added += 1
    return added


def fetch_transcripts(limit=500, workers=10):
    """Fetch captions for untried non-live videos.

    Not an API call and costs no quota -- it scrapes the caption track, so it
    is the slow part. Failures are recorded as '' rather than left NULL, so a
    video with captions genuinely disabled is never retried.
    """
    pending = store.needing_transcript(limit)
    if not pending:
        return 0, 0
    tapi = YouTubeTranscriptApi()

    def grab(row):
        try:
            fetched = tapi.fetch(row["video_id"])
            return row["video_id"], " ".join(s.text for s in fetched)
        except Exception:
            return row["video_id"], ""

    got = 0
    with ThreadPoolExecutor(workers) as pool:
        for video_id, text in pool.map(grab, pending):
            store.set_transcript(video_id, text)
            if text:
                got += 1
    return got, len(pending)


def run_once(days=7):
    store.init()
    for channel, channel_id in CHANNELS.items():
        playlist = uploads_playlist(channel_id)
        if not playlist:
            print(f"  {channel:12} could not resolve uploads playlist")
            continue
        ids = recent_video_ids(playlist, days)
        store_videos(channel, ids)
        print(f"  {channel:12} {len(ids):4} uploads in last {days}d")
    got, tried = fetch_transcripts()
    print(f"\n  transcripts: {got}/{tried} fetched")
    return store.stats()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()
    print(f"Ingesting {len(CHANNELS)} channels, last {args.days} days\n")
    s = run_once(args.days)
    print(f"\n  db now: {s['videos']} videos from {s['channels']} channels")
    print(f"          {s['usable']} usable, {s['live']} live (skipped), "
          f"{s['unavailable']} no captions, {s['pending']} pending")
