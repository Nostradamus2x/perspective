from flask import Flask, render_template, request
import feedparser

app = Flask(__name__)

NEWS_SOURCES = [
    {
        "name": "The Hindu",
        "url": "https://www.thehindu.com/news/national/feeder/default.rss",
        "bias": "center"
    },
    {
        "name": "Scroll.in",
        "url": "https://feeds.feedburner.com/ScrollinArticles.rss",
        "bias": "left"
    },
    {
        "name": "OpIndia",
        "url": "https://www.opindia.com/feed/",
        "bias": "right"
    }
]

def fetch_articles():
    articles_by_bias = {"left": [], "center": [], "right": []}
    for source in NEWS_SOURCES:
        feed = feedparser.parse(source["url"])
        for entry in feed.entries[:10]:  # Limit to 10 per source
            articles_by_bias[source["bias"]].append({
                "title": entry.title,
                "link": entry.link,
                "source": source["name"]
            })
    return articles_by_bias

@app.route("/", methods=["GET"])
def index():
    articles = fetch_articles()
    return render_template("index.html", articles=articles)

if __name__ == "__main__":
    app.run(debug=True)
