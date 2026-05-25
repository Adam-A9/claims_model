import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

df = pd.read_csv(BASE_DIR / "small_commercial_underwriting_raw.csv")

print(df.info())
print(df.isnull().sum())
print(df.dtypes)
print(df.head())
print(df.describe())

