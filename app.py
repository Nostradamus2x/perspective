from flask import Flask, render_template, request
import feedparser
import re
from collections import Counter

app = Flask(__name__)

NEWS_SOURCES = [
    {
        "name": "The Hindu",
        "url": "https://www.thehindu.com/news/national/feeder/default.rss"
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

def fetch_articles():

    articles_by_bias = {"left": [], "center": [], "right": [], "factcheck": []}
    all_articles = []
    for source in NEWS_SOURCES:
        feed = feedparser.parse(source["url"])
        for entry in feed.entries[:100]:  # Limit to 10 per source
            article = {
                "title": entry.title,
                "link": entry.link,
                "source": source["name"],
                "bias": source["bias"],
                "clean_title": clean_title(entry.title)
            }
            articles_by_bias[source["bias"]].append(article)
            all_articles.append(article)
    return articles_by_bias, all_articles


from sentence_transformers import SentenceTransformer
import numpy as np

def find_highlight_topic(all_articles):
    # Group articles by bias
    grouped = {'left': [], 'center': [], 'right': [], 'factcheck': []}
    for article in all_articles:
        grouped[article['bias']].append(article)
    # If any group is empty, can't find a trio
    if not all(grouped.values()):
        return None, None

    # Prepare all headlines and encode them
    model = SentenceTransformer('all-mpnet-base-v2')  # Fast, high-quality model
    # Create lists of headlines for each bias
    left_titles = [a['title'] for a in grouped['left']]
    center_titles = [a['title'] for a in grouped['center']]
    right_titles = [a['title'] for a in grouped['right']]
    factcheck_titles = [a['title'] for a in grouped['factcheck']]
    
    # Encode all headlines
    left_embeddings = model.encode(left_titles)
    center_embeddings = model.encode(center_titles)
    right_embeddings = model.encode(right_titles)
    factcheck_embeddings = model.encode(factcheck_titles)
    

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
    if best_score < 0.3:  # You can adjust this threshold
        return None, None

    # Use the center headline as the topic label
    highlight_word = best_quartet['center']['title']
    return highlight_word, best_quartet


    # Try to find a word that appears in all three sources
    for word, count in word_counter.most_common():
        # Get articles from each bias containing this word
        highlight_articles = {
            bias: next((a for a in all_articles if (a["bias"] == bias and word in a["clean_title"].split())), None)
            for bias in ["left", "center", "right","factcheck"]
        }
        if all(highlight_articles.values()):
            return word, highlight_articles
    return None, None

@app.route("/", methods=["GET"])
def index():
    articles, all_articles = fetch_articles()
    highlight_word, highlight_articles = find_highlight_topic(all_articles)
    return render_template(
        "index.html",
        articles=articles,
        highlight_word=highlight_word,
        highlight_articles=highlight_articles
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

