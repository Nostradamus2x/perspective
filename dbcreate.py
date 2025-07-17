import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

data = []

# Set current year/month to today
current_year = 2025
current_month = 7  # July
for year in range(2024, current_year + 1):
    # In the current year, only scrape up to the current month
    if year == current_year:
        month_end = current_month
    else:
        month_end = 12

# url = 'https://archives.ndtv.com/articles/2025-01.html'

# response = requests.get(url)
# response.encoding = 'utf-8'  # Force UTF-8!
# html = response.text
# soup = BeautifulSoup(html, 'lxml')


# articles = soup.find_all('li')


# with open('ndtv_output.txt', 'w', encoding='utf-8') as f:
#     for article in articles:
#         if article.find('a'):  # likely filters story items
#             f.write(article.text.strip() + '\n')


    for month in range(1, month_end + 1):
        url = f"https://archives.ndtv.com/articles/{year}-{month:02d}.html"
        resp = requests.get(url)
        resp.encoding = 'utf-8'  # Force UTF-8!
        if resp.status_code != 200:
            print(f"Failed to fetch {url}: {resp.status_code}")
            continue
        soup = BeautifulSoup(resp.content, "html.parser")
        for item in soup.find_all("li"):
            headline = item.get_text(strip=True)
            link = item.find("a")["href"] if item.find("a") else None
            data.append({
                "outlet": "NDTV",
                "date": f"{year}-{month:02d}",
                "headline": headline,
                "url": link
            })

df = pd.DataFrame(data)
df.to_csv("ndtv_news.csv", index=False, encoding = "utf-8")
