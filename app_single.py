"""Web UI: one story, several outlets, a comment box per outlet.

Kept separate from app.py so the existing site keeps running unchanged.
Run on a different port:  python app_single.py
"""

from flask import Flask, redirect, render_template, request, url_for
from flask_caching import Cache

import common_story
import store

app = Flask(__name__)
app.config["CACHE_TYPE"] = "filesystem"
app.config["CACHE_DIR"] = "flask_cache_single"
app.config["CACHE_DEFAULT_TIMEOUT"] = 10 * 60
cache = Cache(app)

store.init()


@cache.cached(key_prefix="single_clusters")
def load_clusters():
    return common_story.top_stories(limit=5)


@app.route("/")
def index():
    clusters = load_clusters()
    urls = [a.url for c in clusters for a in c.articles]
    return render_template(
        "single.html",
        clusters=clusters,
        comments=store.comments_for(urls),
        total_sources=len(common_story.SOURCES),
        min_similarity=common_story.MIN_SIMILARITY,
        max_span=common_story.MAX_SPAN_HOURS,
        saved=store.count(),
    )


@app.route("/comment", methods=["POST"])
def comment():
    store.save_comment(
        request.form["url"],
        request.form["source"],
        request.form["headline"],
        request.form.get("comment", ""),
    )
    return redirect(url_for("index") + f"#{request.form['anchor']}")


@app.route("/refresh", methods=["POST"])
def refresh():
    cache.delete("single_clusters")
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Load the model before serving so the first request isn't a 10s stall.
    common_story.get_model()
    # debug=True must stay off: the reloader re-imports this module and torch
    # then raises "Cannot copy out of meta tensor" on the next encode.
    app.run(host="0.0.0.0", port=8081, debug=False)
