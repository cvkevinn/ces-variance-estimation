import pandas as pd
import yaml
import os

from settings import CONFIG_PATH, TAGS_DIR


def var_topic_map_yaml() -> dict:
    with open(CONFIG_PATH, "r") as file:
        config = yaml.safe_load(file)

    blocks = ["quantitative", "qualitative", "prob_bin"]
    var_topic_map = {}
    for b in blocks:
        for d in config[b]["variables"]:
            if "name" in d:
                k = d["name"]
            else:
                k = d["base"]
            var_topic_map[k] = d["topic"]
    return var_topic_map


def tags_edp() -> dict:
    var_topic_map = var_topic_map_yaml()
    topics_map = {
        "house_credit": "Housing and credit access",
        "income_consumption": "Income and consumption",
        "inflation": "Inflation",
        "labor_econgrowth": "Labour and economic growth",
    }

    map = {k: topics_map.get(v, v) for k, v in var_topic_map.items()}
    map_final = {k.upper(): v for k, v in map.items()}
    return map_final

def generalise_series_key(key: str) -> str:
    '''
    Needed for categories in EDP
    '''
    parts = key.split(".")
    # Expecting 8 parts: CES M AT ALL T C1010 DEC WS
    if len(parts) != 8:
        # Decide what you want here: raise, return original, or log
        return key
    return ".".join([
        parts[0],   # CES
        "*", "*", "*", "*",  # wildcard positions 2–5
        parts[5],   # variable name, e.g. C1010
        "*", "*"    # last two as wildcard
    ])


if __name__ == "__main__":
    # tags
    tags_mapping = tags_edp()

    # NOTE: DOWNLOAD csv data from the ECB Data Portal (it contains 'SERIES_KEYS')
    # NOTE: and save it as `data.csv` inside `ces_edp/tags_edp/`.
    # Acceptance: https://s-data.ecb.europa.eu/data/datasets
    # Production: https://data.ecb.europa.eu/data/datasets

    filename_csv_edp = "data.csv"
    df_edp = pd.read_csv(os.path.join(TAGS_DIR, filename_csv_edp))

    # Creating 'TAGS_SET' variable
    df_edp["TAGS_SET"] = (
        df_edp["CES_VARIABLE"].map(tags_mapping).fillna("Inflation").astype(str)
    )

    # Cleaning
    df = df_edp.loc[:, ["KEY", "TAGS_SET"]]
    df.rename(columns={"KEY": "KEY_SERIES"}, inplace=True)
    df_unique = df.drop_duplicates(subset="KEY_SERIES", ignore_index=True)

    df_categories = df_unique.copy()
    df_categories["KEY_SERIES_GENERAL"] = df_unique["KEY_SERIES"].map(generalise_series_key)
    df_categories_unique = df_categories.drop_duplicates(subset="KEY_SERIES_GENERAL", ignore_index=True)
    
    categories_to_keys = (
    df_categories_unique.groupby("TAGS_SET")["KEY_SERIES_GENERAL"]
      .unique()        # keep only unique keys per tag
      .apply(list)     # turn numpy array into plain list
      .to_dict()
    )

    # Export
    df_unique.to_excel(
        TAGS_DIR / "ces_tags.xlsx",
        index=False,
        sheet_name="Export Worksheet",
    )
