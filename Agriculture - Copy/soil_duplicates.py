"""
Quick check: soil should be one static reading per property/depth for a
single farm. If data_soil_ariyalur.csv has duplicate rows for the same
property+depth (e.g. from running soil_collector.py more than once and
saving over/alongside an earlier partial run), that's worth knowing about
even though it didn't break anything downstream.
"""

import pandas as pd

df = pd.read_csv("data_soil_ariyalur.csv")
print(f"Total rows: {len(df)}")

dupes = df[df.duplicated(subset=["property", "depth"], keep=False)]
if len(dupes) > 0:
    print(f"\nFound {len(dupes)} rows involved in property+depth duplicates:")
    print(dupes.sort_values(["property", "depth"]).to_string())
else:
    print("\nNo duplicates found -- exactly one row per property+depth combination, as expected.")