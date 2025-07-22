import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re

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

def is_english(text):
    # Returns True if the text contains only English letters, numbers, spaces, or basic punctuation
    # You can expand this to include more punctuation/special cases if needed.
    return bool(re.match(r'^[A-Za-z0-9\s,._"\'\:;\(\)\[\]\?!@#&*%$-]+$', text))

print("Reached for loop")
for month in range(1, month_end + 1):
    url = f"https://archives.ndtv.com/articles/{year}-{month:02d}.html"
    print("Year is ",year,". Month is ",month)
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Failed to fetch {url}: {resp.status_code}")
        continue
    soup = BeautifulSoup(resp.content, "html.parser")
    for item in soup.find_all("li"):
        headline = item.get_text(strip=True)
        if is_english(headline):
            link = item.find("a")["href"] if item.find("a") else None

            data.append({
                "outlet": "NDTV",
                "date": f"{year}-{month:02d}",
                "headline": headline,
                "url": link
            })

df = pd.DataFrame(data)
df.to_csv("ndtv_headlines.csv", index=False, encoding = "utf-8")
