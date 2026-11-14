import pandas as pd
d = pd.read_csv("data/interim/granule_manifest.csv")
print(d[["BLUE_url", "NIR_NARROW_url", "QA_url"]].head(2).to_string())
print("BLUE:", (d["BLUE_url"].fillna("").str.len() > 0).sum())
print("QA:", (d["QA_url"].fillna("").str.len() > 0).sum())