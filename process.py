#text_classification

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import numpy as np

# Load your dataframe as needed:
df = pd.read_csv('ndtv_articles_labeled.csv')


print(df['label'].value_counts(dropna=False))  # Sanity check: Should show classes and NaNs



#split labeled/unlabaled

# Get only labeled data for supervised training
labeled_df = df[df['label'].notnull()].copy()
unlabeled_df = df[df['label'].isnull()].copy()


#Vectorization
vectorizer = TfidfVectorizer(max_features=5000)
vectorizer.fit(df['cleaned_text'])  # Fit on **all** data to ensure feature consistency

X_labeled = vectorizer.transform(labeled_df['cleaned_text'])
y_labeled = labeled_df['label']

X_unlabeled = vectorizer.transform(unlabeled_df['cleaned_text'])


#Train/Split for Labeled Data

X_train, X_val, y_train, y_val = train_test_split(
    X_labeled, y_labeled, test_size=0.2, random_state=42, stratify=y_labeled
)
print("Train samples:", X_train.shape[0], "Validation samples:", X_val.shape[0])


#Model Training using logistic regresion
clf = LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42)
clf.fit(X_train, y_train)


#Validation/Evaluation
y_pred = clf.predict(X_val)
print("\n=== Validation Results ===")
print(classification_report(y_val, y_pred))
print(confusion_matrix(y_val, y_pred))
print("Accuracy:", accuracy_score(y_val, y_pred))



#Predit on unlabeled data
unlabeled_pred = clf.predict(X_unlabeled)
unlabeled_df = unlabeled_df.copy()  # For assignment safety
unlabeled_df['label_predicted'] = unlabeled_pred

# For full dataset: update labels where they are missing
df.loc[df['label'].isnull(), 'label'] = unlabeled_pred
df['label_type'] = np.where(df['label'].notnull() & df.index.isin(labeled_df.index), "manual", "predicted")

# Optional: Save with prediction origin
df.to_csv('ndtv_articles_with_labels.csv', index=False)


# Sanity check
print(df['label_type'].value_counts())
print(df[['headline', 'label', 'label_type']].sample(5))

# Now, df['label'] contains the stance for every article, with "manual" or "predicted" indicated.


#Best practices - interpret coefficients
feature_names = vectorizer.get_feature_names_out()
for idx, class_label in enumerate(clf.classes_):
    top_idxs = clf.coef_[idx].argsort()[-10:][::-1]
    print(f"Top features for '{class_label}': {[feature_names[i] for i in top_idxs]}")
