from flask import Flask, render_template, request
from flask_caching import Cache
import feedparser
import re
from collections import Counter
import time
import numpy as np
from sentence_transformers import SentenceTransformer

app = Flask(__name__)

#Cache Configuration
app.config['CACHE_TYPE'] = 'filesystem'
app.config['CACHE_DIR'] = 'flask_cache'  # Directory for storing cache files
app.config['CACHE_DEFAULT_TIMEOUT'] = 10 * 60  # 10 minutes
cache = Cache(app)


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
    },
    {
        "name": "Altnews",
        "url": "https://www.altnews.in/feed/",
        "bias": "factcheck"
    }
]

def clean_title(title):
    # Lowercase and remove punctuation for better matching
    return re.sub(r'[^\w\s]', '', title.lower())

########
# Caching setup
# CACHE = {
#     "articles": None,
#     "all_articles": None,
#     "highlight_word": None,
#     "highlight_articles": None,
#     "timestamp": 0,
#     "fetching": False
# }

# CACHE_TIMEOUT = 100 * 60  # 100 minutes

model = SentenceTransformer('all-mpnet-base-v2')  # Fast, high-quality model

EMBED_CACHE = {}

def embed_titles (titles):
    not_embedded = [t for t in titles if t not in EMBED_CACHE]
    if not_embedded:
        vectors = model.encode(not_embedded)
        for t, v in zip(not_embedded, vectors):
            EMBED_CACHE[t] = v
    return [EMBED_CACHE[t] for t in titles]


@cache.cached(key_prefix="news_data")    
def fetch_and_process_articles():
    # now = time.time()
    # if (CACHE["articles"] is not None) and (now - CACHE["timestamp"] < CACHE_TIMEOUT):
    #     # Use cache if fresh
    #     print("Using cached articles")
    #     return CACHE["articles"], CACHE["all_articles"]

    print("Fetching fresh articles from the web")

    articles_by_bias = {"left": [], "center": [], "right": [], "factcheck": []}
    all_articles = []
    for source in NEWS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:50]:  # Limit to 10 per source
                article = {
                    "title": entry.title,
                    "link": entry.link,
                    "source": source["name"],
                    "bias": source["bias"],
                    "clean_title": clean_title(entry.title)
                }
                articles_by_bias[source["bias"]].append(article)
                all_articles.append(article)
        except Exception as e:
            print (f"Failed to fetch {source['name']}:{e}")
            continue
    
    # #Update CACHE
    # CACHE["articles"] = articles_by_bias
    # CACHE["all_articles"] = all_articles
    # CACHE["timestamp"] = now
    # return articles_by_bias, all_articles


    # Highlight logic (can cache/memoize separately if needed)
    # Group articles by bias
    grouped = {'left': [], 'center': [], 'right': [], 'factcheck': []}
    for article in all_articles:
        grouped[article['bias']].append(article)
    # If any group is empty, can't find a trio
    if not all(grouped.values()):
        return None, None

    # Prepare all headlines and encode them
    # Create lists of headlines for each bias
    left_titles = [a['title'] for a in grouped['left']]
    center_titles = [a['title'] for a in grouped['center']]
    right_titles = [a['title'] for a in grouped['right']]
    factcheck_titles = [a['title'] for a in grouped['factcheck']]
    
    # Encode all headlines
    left_embeddings = embed_titles(left_titles)
    center_embeddings = embed_titles(center_titles)
    right_embeddings = embed_titles(right_titles)
    factcheck_embeddings = embed_titles(factcheck_titles)
    

    # Find the quartet (one from each bias) with the highest average pairwise similarity
    best_score = -1
    best_quartet = None
    for i, l_emb in enumerate(left_embeddings):
        for j, c_emb in enumerate(center_embeddings):
            for k, r_emb in enumerate(right_embeddings):
                for m, f_emb in enumerate(factcheck_embeddings):
           
                    # Compute pairwise cosine similarities
                    sim_lc = np.dot(l_emb, c_emb) / (np.linalg.norm(l_emb) * np.linalg.norm(c_emb))
                    sim_lr = np.dot(l_emb, r_emb) / (np.linalg.norm(l_emb) * np.linalg.norm(r_emb))
                    sim_lf = np.dot(l_emb, f_emb) / (np.linalg.norm(l_emb) * np.linalg.norm(f_emb))
                    sim_cr = np.dot(c_emb, r_emb) / (np.linalg.norm(c_emb) * np.linalg.norm(r_emb))
                    sim_cf = np.dot(c_emb, f_emb) / (np.linalg.norm(c_emb) * np.linalg.norm(f_emb))
                    sim_rf = np.dot(r_emb, f_emb) / (np.linalg.norm(r_emb) * np.linalg.norm(f_emb))
                    avg_sim = (sim_lc + sim_lr + sim_lf + sim_cr + sim_cf + sim_rf) / 6
                    if avg_sim > best_score:
                        best_score = avg_sim
                        best_quartet = {
                            'left': grouped['left'][i],
                            'center': grouped['center'][j],
                            'right': grouped['right'][k],
                            'factcheck': grouped['factcheck'][m]
                        }
                        
    # Set a minimum similarity threshold to avoid unrelated headlines
    if best_score >= 0.3 and best_quartet:  # You can adjust this threshold
        highlight_word = best_quartet['center']['title'] # Use the center headline as the topic label
        highlight_articles = best_quartet
    return articles_by_bias,all_articles, highlight_word, highlight_articles

@app.route("/", methods=["GET"])
def index():
    articles, all_articles, highlight_word, highlight_articles = fetch_and_process_articles()
    return render_template(
        "index.html",
        articles=articles,
        highlight_word=highlight_word,
        highlight_articles=highlight_articles
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)

