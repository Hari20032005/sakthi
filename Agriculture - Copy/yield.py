"""
Filter the Kaggle crop production dataset down to Ariyalur / rice & cotton.

Confirmed columns: State, District, Crop, Crop_Year, Season, Area, Production, Yield
"""

import pandas as pd

# Change this to whatever the downloaded file is actually named
INPUT_FILE = "APY.csv"

df = pd.read_csv(INPUT_FILE)

# --- Clean up known quirks in this dataset ---
# Column headers have trailing spaces (e.g. "District ", "Area ")
df.columns = df.columns.str.strip()

# Text values also have trailing spaces (e.g. Season = "Kharif     ")
for col in df.select_dtypes(include="object").columns:
    df[col] = df[col].astype(str).str.strip()

print("Total rows in full dataset:", len(df))
print("Columns (cleaned):", df.columns.tolist())

# --- Filter for Ariyalur district ---
ariyalur_df = df[df['District'].str.contains('ARIYALUR', case=False, na=False)]
print("\nRows for Ariyalur (all crops):", len(ariyalur_df))

if len(ariyalur_df) == 0:
    print("\n!! No rows matched 'ARIYALUR'. Ariyalur district was carved out of")
    print("   Perambalur district in 2007 -- older records (pre-2007) may")
    print("   still be filed under 'PERAMBALUR' instead. Try checking:")
    print(df['District'].unique()[:40])  # eyeball the real district names
else:
    # --- Further filter for rice and cotton ---
    crops_df = ariyalur_df[
        ariyalur_df['Crop'].str.contains('Rice|Cotton', case=False, na=False)
    ]
    print("\nRows for Ariyalur -- Rice & Cotton only:", len(crops_df))
    print("\nCrop varieties found:", crops_df['Crop'].unique())
    print("\nYears covered:", sorted(crops_df['Crop_Year'].unique()))
    print("\nSample rows:")
    print(crops_df.head(10).to_string())

    # Save the filtered result
    crops_df = crops_df.copy()  # avoid SettingWithCopyWarning on the lines below
    crops_df.to_csv("data_yield_ariyalur_rice_cotton.csv", index=False)
    print("\nSaved -> data_yield_ariyalur_rice_cotton.csv")

    # --- Data quality check: missing/blank values ---
    crops_df["Production"] = pd.to_numeric(crops_df["Production"], errors="coerce")
    crops_df["Yield"] = pd.to_numeric(crops_df["Yield"], errors="coerce")
    missing = crops_df[crops_df["Production"].isna()]
    if len(missing) > 0:
        print(f"\n!! {len(missing)} rows have missing Production (Yield shows 0, which is")
        print("   how this dataset marks 'not recorded', not a true zero harvest).")
        print(missing.head())

        # Drop them -- 2 rows out of 38 is a small, safe loss, and keeping a
        # fabricated 0 would quietly teach the model that a real harvest failed.
        clean_df = crops_df.dropna(subset=["Production"]).reset_index(drop=True)
        clean_df.to_csv("data_yield_ariyalur_rice_cotton_clean.csv", index=False)
        print(f"\nSaved cleaned version ({len(clean_df)} rows) -> data_yield_ariyalur_rice_cotton_clean.csv")
        print("Use the _clean.csv file for model training, not the raw one.")