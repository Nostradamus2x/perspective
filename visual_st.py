import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from wordcloud import WordCloud
from sklearn.feature_extraction.text import CountVectorizer
import matplotlib.font_manager as fm


# Streamlit app title
st.title("NDTV Article Stance Visualizations")


# Load CSV
df = pd.read_csv('ndtv_articles_with_labels.csv')


# Font selection (optional)
font_path = 'NotoSansDevanagari-Regular.ttf'  # Update path as needed


# Show value counts bar plot
st.subheader("Stance Distribution")
fig1, ax1 = plt.subplots()
df['label'].value_counts().plot(kind='bar', ax=ax1)
ax1.set_title("Stance Distribution in NDTV Articles")
ax1.set_xlabel("Stance")
ax1.set_ylabel("Number of Articles")
st.pyplot(fig1)


# Interactive stance selection
stance_options = df['label'].unique()
stance = st.selectbox("Choose Stance for Word Cloud & Keywords:", stance_options)


# Word Cloud for selected stance
st.subheader(f"Word Cloud: {stance.title()}")
text = ' '.join(df[df['label'] == stance]['cleaned_text'])
wordcloud = WordCloud(font_path=font_path, width=800, height=400, background_color='white').generate(text)

fig2, ax2 = plt.subplots(figsize=(10, 5))
ax2.imshow(wordcloud, interpolation='bilinear')
ax2.axis('off')
st.pyplot(fig2)


devanagari_font = fm.FontProperties(fname=font_path)

# Top Keywords bar chart
st.subheader(f"Top 20 Keywords: {stance.title()}")
vec = CountVectorizer(stop_words='english', max_features=20)
X = vec.fit_transform(df[df['label'] == stance]['cleaned_text'])
word_counts = X.sum(axis=0).A1
keywords = vec.get_feature_names_out()

fig3, ax3 = plt.subplots()
ax3.bar(keywords, word_counts)
for label in ax3.get_xticklabels():
    label.set_fontproperties(devanagari_font)
ax3.set_xticklabels(keywords, rotation=45, ha='right')
ax3.set_title("Top 20 Keywords")
fig3.tight_layout()
st.pyplot(fig3)

# Test Devanagari font rendering (optional)
st.subheader("Font Rendering Test")
fig4, ax4 = plt.subplots(figsize=(6,2))
ax4.text(0.1, 0.5, "यह हिंदी है", fontproperties={'fname': font_path}, fontsize=32)
ax4.axis('off')
st.pyplot(fig4)
