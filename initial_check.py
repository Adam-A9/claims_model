import sqlite3
import pandas as pd

df = pd.read_csv(
    r"C:\Users\adama\OneDrive\Desktop\Project\claims_model\small_commercial_underwriting_raw.csv"
)

print(df.info())
print(df.isnull().sum())
print(df.dtypes)
print(df.head())
print(df.describe())

