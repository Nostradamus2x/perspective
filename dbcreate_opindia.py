import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

def is_english(text):
    # Returns True if text contains only English letters, numbers, spaces, or basic punctuation
    return bool(re.match(r'^[A-Za-z0-9\s,._"\'\:;\(\)\[\]\?!@#&*%$-]+$', text))

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

data = []
num_pages = 5  # Adjust this as needed for how many pages you want to scrape

for page in range(1, num_pages + 1):
    url = f"https://www.opindia.com/latest-news/page/{page}/?nocache"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"Failed to fetch {url}: {resp.status_code}")
        continue
    soup = BeautifulSoup(resp.content, "html.parser")
    
    # Each article container
    for container in soup.find_all("div", class_="td-module-container td-category-pos-image"):
        h3_tag = container.find("h3", class_="entry-title td-module-title")
        if h3_tag and h3_tag.a:
            headline = h3_tag.a.get_text(strip=True)
            link = h3_tag.a['href']
            if not is_english(headline):
                continue

            # Date
            time_tag = container.find("time", class_="entry-date updated td-module-date")
            date = time_tag['datetime'][:10] if time_tag and time_tag.has_attr('datetime') else ''

            # Excerpt
            excerpt_tag = container.find("div", class_="td-excerpt")
            excerpt = excerpt_tag.get_text(strip=True) if excerpt_tag else ''

            data.append({
                "outlet": "OpIndia",
                "date": date,
                "headline": headline,
                "url": link,
                "excerpt": excerpt
            })
    time.sleep(2)  # Be respectful; sleep 2 seconds between page fetches

df = pd.DataFrame(data)
print(df.head())
df.to_csv("opindia_headlines.csv", index=False, encoding="utf-8")
