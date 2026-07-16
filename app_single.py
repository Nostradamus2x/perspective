"""Weekly digest UI: TV stories covered by several channels, with notes.

    venv/bin/python tv_ingest.py --days 7   # populate first
    venv/bin/python app_single.py           # then serve on :8081

Reads only from SQLite. Ingestion is a separate step because fetching a week of
transcripts takes minutes and must not happen inside a request.
"""

from flask import Flask, redirect, render_template, request, url_for
from flask_caching import Cache

import common_story
import store
import tv_ingest

app = Flask(__name__)
app.config["CACHE_TYPE"] = "filesystem"
app.config["CACHE_DIR"] = "flask_cache_single"
app.config["CACHE_DEFAULT_TIMEOUT"] = 30 * 60
cache = Cache(app)

store.init()

WINDOW_DAYS = 7


@cache.cached(key_prefix="digest")
def load_digest():
    return common_story.weekly_digest(days=WINDOW_DAYS, limit=5)


@app.route("/")
def index():
    events, topics, total = load_digest()
    ids = [s.video_id for c in events + topics for s in c.segments]
    return render_template(
        "single.html",
        events=events,
        topics=topics,
        total=total,
        window=WINDOW_DAYS,
        comments=store.comments_for(ids),
        stats=store.stats(),
        event_floor=common_story.EVENT_SIMILARITY,
        topic_floor=common_story.TOPIC_SIMILARITY,
        channels=len(tv_ingest.CHANNELS),
    )


@app.route("/comment", methods=["POST"])
def comment():
    store.save_comment(
        request.form["video_id"],
        request.form["channel"],
        request.form["title"],
        request.form.get("comment", ""),
    )
    return redirect(url_for("index") + f"#{request.form['anchor']}")


@app.route("/recluster", methods=["POST"])
def recluster():
    cache.delete("digest")
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Load the model before serving so the first request is not a 10s stall.
    common_story.get_model()
    # debug=True must stay off: the reloader re-imports this module and torch
    # then raises "Cannot copy out of meta tensor" on the next encode.
    app.run(host="0.0.0.0", port=8081, debug=False)
