import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv('combined_articles_with_labels.csv')



# import os
# print(os.path.exists('NotoSansDevanagari-Regular.ttf'))  # Should print True

# import matplotlib.pyplot as plt
# from matplotlib import font_manager

# font_path = 'NotoSansDevanagari-Regular.ttf'
# assert os.path.exists(font_path), "Font file not found!"

# prop = font_manager.FontProperties(fname=font_path)
# plt.rcParams['font.family'] = prop.get_name()
# plt.rcParams['font.sans-serif'] = [prop.get_name()]

# # Now force a test plot
# plt.figure(figsize=(6,2))
# plt.text(0.1, 0.5, "यह हिंदी है", fontproperties=prop, fontsize=32)
# plt.axis('off')
# plt.show()


df['label'].value_counts().plot(kind='bar')
plt.title("Stance Distribution in NDTV and OpIndia Articles")
plt.xlabel("Stance")
plt.ylabel("Number of Articles")
plt.show()


from wordcloud import WordCloud
text_pro = ' '.join(df[df['label'] == 'Pro-Government']['cleaned_text'])
font_path = '/Users/ayushshukla/Downloads/perspective/NotoSansDevanagari-Regular.ttf'  # update path as needed


wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text_pro)
plt.imshow(wordcloud, interpolation='bilinear')
plt.axis('off')
plt.title("Word Cloud: Pro-Government Stance")
plt.show()




from sklearn.feature_extraction.text import CountVectorizer
vec = CountVectorizer(stop_words='english', max_features=20)
X = vec.fit_transform(df[df['label'] == 'Pro-Government']['cleaned_text'])
word_counts = X.sum(axis=0).A1
keywords = vec.get_feature_names_out()
plt.bar(keywords, word_counts)
plt.xticks(rotation=45)
plt.title("Top 20 Keywords: Pro-Government")
plt.tight_layout()
plt.show()



# # Simple font test
# import matplotlib.pyplot as plt
# plt.rcParams['font.family'] = 'Noto Sans Devanagari'
# plt.rcParams['font.sans-serif'] = ['NotoSansDevanagari-Regular.ttf']
# plt.text(0.1, 0.5, "यह हिंदी है", fontsize=32)
# plt.show()
