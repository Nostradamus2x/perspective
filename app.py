from flask import Flask, render_template, request
import feedparser

app = Flask(__name__)

NEWS_SOURCES = [
    {
        "name": "The Hindu",
        "url": "https://www.thehindu.com/news/national/feeder/default.rss"
    },
    {
        "name": "Scroll.in",
        "url": "https://feeds.feedburner.com/ScrollinArticles.rss"
    },
    {
        "name": "OpIndia",
        "url": "https://www.opindia.com/feed/"
    }
]

def fetch_articles():
    articles = []
    for source in NEWS_SOURCES:
        feed = feedparser.parse(source["url"])
        for entry in feed.entries[:10]:
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "summary": getattr(entry, "summary", ""),
                "source": source["name"]
            })
    return articles

@app.route("/", methods=["GET"])
def index():
    articles = fetch_articles()
    return render_template("index.html", articles=articles)

if __name__ == "__main__":
    app.run(debug=True)
