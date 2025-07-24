#preprocess.py

import pandas as pd
import re
import string
from langdetect import detect
from tqdm import tqdm

# For English processing
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# For Hindi processing
# import os
# from indicnlp.tokenize import sentence_tokenize, indic_tokenize

# ---------------- SETUP -------------------

# # Set up Indic NLP resource path. Change this to the actual path where you cloned 'indic_nlp_resources'
# INDIC_RESOURCES_PATH = '/Users/ayushshukla/Downloads/perspective/indic_nlp_resources'  # <<<--- CHANGE THIS
# os.environ["INDIC_RESOURCES_PATH"] = INDIC_RESOURCES_PATH

nltk.download('stopwords')
nltk.download('wordnet')

# Get stopwords once for performance
en_stopwords = set(stopwords.words('english'))
# def load_hindi_stopwords(file_path):
#     with open(file_path, encoding='utf-8') as f:
#         return set(line.strip() for line in f if line.strip())
        
# hi_stopwords = load_hindi_stopwords('stopwords-hi.txt')

lemmatizer = WordNetLemmatizer()

def clean_text(text):
    if not isinstance(text, str):
        return ""

    # Lowercase
    text = text.lower()
    # Remove URLs
    text = re.sub(r'http\S+', ' ', text)
    # Remove HTML tags
    text = re.sub(r'<.*?>', ' ', text)
    # Remove punctuation (including English and Hindi punctuation)
    text = re.sub('[%s]' % re.escape(string.punctuation), ' ', text)
    # Remove extra whitespace
    text = ' '.join(text.split())
    return text

def preprocess_article(text):
    cleaned = clean_text(text)
    try:
        language = detect(cleaned)
    except:
        language = "en"  # fallback

    if language == 'hi':
        # Hindi text: use Indic NLP for word tokenization and stopword removal
        # You can split to sentences first, but for stopword/token cleaning, word tokenization is enough.
        tokens = indic_tokenize.trivial_tokenize(cleaned)
        tokens = [tok for tok in tokens if tok not in hi_stopwords and tok.strip()]
        # (Optional) Add further stemming/normalization if needed
    else:
        # English
        tokens = cleaned.split()
        tokens = [lemmatizer.lemmatize(tok) for tok in tokens if tok not in en_stopwords and tok.strip()]
    return ' '.join(tokens)

# --------- LOAD & CLEAN DATA ----------
df = pd.read_csv('opindia_articles.csv')

# Remove rows with blank article_text
df = df[df['article_text'].notnull() & (df['article_text'].str.strip() != "")]

# tqdm adds a progress bar for big datasets
tqdm.pandas()

df['cleaned_text'] = df['article_text'].progress_apply(preprocess_article)

df.to_csv('opindia_articles_cleaned.csv', index=False)
