"""
The Kaggle price dataset comes as one file per year (2001.csv ... 2026.csv),
not a single combined CSV. Recent years are large (5M+ rows), so this reads
each file in CHUNKS, filtering every chunk down to Tamil Nadu rice/cotton
immediately -- we never hold a full year's raw data in memory, only the
small filtered slice, which is what let earlier attempts run out of memory
on the bigger recent-year files.

Point DATA_FOLDER at wherever you saved all the yearly files.
"""

import gc
import glob
import os
import pandas as pd

DATA_FOLDER = r"C:\Users\Home\OneDrive\Desktop\Agriculture\price_data"

TARGET_STATE = "Tamil Nadu"
TARGET_DISTRICT = "Ariyalur"
# Confirmed real commodity naming in this dataset (found via find_rice_naming.py):
# paddy is the unmilled crop farmers actually sell at the mandi; "Rice" and
# "Beaten Rice" are milled/processed forms that also appear but are rarer.
TARGET_CROPS = ["Paddy", "Rice", "Cotton"]
CHUNK_SIZE = 200_000  # rows per chunk -- safe for most machines


def find_yearly_files(folder: str) -> list:
    candidates = []
    for ext in ("csv", "xlsx", "xls"):
        candidates.extend(glob.glob(os.path.join(folder, f"*.{ext}")))
    yearly_files = []
    for path in candidates:
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.isdigit() and 1990 <= int(stem) <= 2030:
            yearly_files.append(path)
    return sorted(yearly_files)


def _filter_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """Filter BEFORE any expensive per-column strip -- str.contains works fine
    on unstripped text since it's a substring search, so this is cheap and
    shrinks the data massively before we do anything heavier."""
    chunk.columns = chunk.columns.str.strip()
    if "State" not in chunk.columns or "Commodity" not in chunk.columns:
        return pd.DataFrame()

    mask = (
        chunk["State"].astype(str).str.contains(TARGET_STATE, case=False, na=False)
        & chunk["Commodity"].astype(str).str.contains("|".join(TARGET_CROPS), case=False, na=False)
    )
    small = chunk.loc[mask].copy()
    if small.empty:
        return small

    # Only strip whitespace on the small filtered subset, not the full chunk
    for col in small.select_dtypes(include="object").columns:
        small[col] = small[col].astype(str).str.strip()
    return small


def load_and_filter_one_file(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".csv":
        filtered_chunks = []
        for chunk in pd.read_csv(path, chunksize=CHUNK_SIZE):
            small = _filter_chunk(chunk)
            if not small.empty:
                filtered_chunks.append(small)
            del chunk
        result = pd.concat(filtered_chunks, ignore_index=True) if filtered_chunks else pd.DataFrame()
    else:
        # Excel files can't be chunked the same way -- read whole, but this
        # is fine since the large files in this dataset are the .csv years
        df = pd.read_excel(path)
        result = _filter_chunk(df)
        del df

    gc.collect()
    return result


if __name__ == "__main__":
    files = find_yearly_files(DATA_FOLDER)
    if not files:
        raise SystemExit(
            f"No yearly files found in '{DATA_FOLDER}'. Set DATA_FOLDER to the "
            f"folder containing 2001.csv ... 2026.csv (or .xlsx)."
        )

    print(f"Found {len(files)} yearly files: {[os.path.basename(f) for f in files]}\n")

    all_filtered = []
    for path in files:
        year_label = os.path.splitext(os.path.basename(path))[0]
        print(f"Reading {year_label}...")
        filtered = load_and_filter_one_file(path)
        print(f"  {len(filtered)} Tamil Nadu rice/cotton rows found")
        if len(filtered) > 0:
            all_filtered.append(filtered)
        del filtered
        gc.collect()

    if not all_filtered:
        raise SystemExit("No matching rows found in any year -- check column names/values.")

    combined = pd.concat(all_filtered, ignore_index=True)
    print(f"\nTotal combined rows (all years, Tamil Nadu, rice/cotton): {len(combined)}")

    # Now split Ariyalur vs fallback, same as before
    ariyalur_df = combined[combined["District"].str.contains(TARGET_DISTRICT, case=False, na=False)]
    print(f"Of which Ariyalur-specific: {len(ariyalur_df)}")

    final_df = ariyalur_df if len(ariyalur_df) > 0 else combined
    if len(ariyalur_df) == 0:
        print("No Ariyalur-specific records across any year -- using all Tamil Nadu "
              "markets as a proxy (nearby markets like Trichy/Perambalur/Thanjavur "
              "are what Ariyalur farmers would realistically sell into).")

    # Data quality: drop missing/zero prices
    final_df = final_df.copy()
    final_df["Modal_Price"] = pd.to_numeric(final_df["Modal_Price"], errors="coerce")
    before = len(final_df)
    final_df = final_df[final_df["Modal_Price"] > 0]
    dropped = before - len(final_df)
    if dropped:
        print(f"Dropped {dropped} rows with missing/zero Modal_Price.")

    final_df.to_csv("data_prices_ariyalur_tamilnadu_2001_2026.csv", index=False)
    print(f"\nSaved {len(final_df)} clean rows -> data_prices_ariyalur_tamilnadu_2001_2026.csv")
    print("\nCommodities found:", final_df["Commodity"].unique())
    print("Markets found:", final_df["Market"].unique())
    print("\nSample:")
    print(final_df.head(10).to_string())