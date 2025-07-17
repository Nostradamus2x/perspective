#articles.py



import pandas as pd

df = pd.read_csv('news.csv')
urls = df['url'].tolist()


from newspaper import Article
import time

def fetch_article_content(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        print(f"Failed for {url}: {e}")
        return ""

df['article_text'] = df['url'].apply(fetch_article_content)
time.sleep(1) # Optionally, add a sleep between requests to be polite!

df.to_csv('ndtv_articles_with_text.csv', index=False, encoding = "utf-8")