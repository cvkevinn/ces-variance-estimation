import re
import yaml
import logging
import numpy as np
import pandas as pd
from pandas.io.formats import excel
from connectors import devo
from datetime import datetime
from others._constants_mapping import (
    VAR_TOPIC_MAPPING,
    VAR_LABEL_MAPPING,
    COLUMNS_ORDER_DFS,
    COLUMNS_ORDER_DFE,
    MAPPING_COLUMN_NAMES,
    MAPPING_BREAKDOWN_AGE_VALUES,
)
from settings import table_storage_path

excel.ExcelFormatter.header_style = None


def download_table(
    lab_name: str,
    table_name: str,
    varlist: str | list[str],
    wave: int | None = None,
) -> pd.DataFrame:

    # Handling the varlist
    if isinstance(varlist, str):
        if varlist != "all":
            raise ValueError("If varlist is string, the only input possible is 'all'.")
        query_vars = "*"
    else:
        query_vars = ", ".join(varlist)

    base_query = f"SELECT {query_vars} FROM lab_{lab_name}.{table_name}"

    if wave is not None:
        query = f"{base_query} WHERE wave = {wave}"
    else:
        query = base_query

    df = devo.read_sql(query)
    return df


def upload_table(df: pd.DataFrame, datalab: str, table_name: str):

    s3_path = table_storage_path(datalab, table_name)
    logging.warning(f"Uploading table '{table_name}' to DEVO 'lab_{datalab}'")

    devo.create_table(
        df,
        lab=f"lab_{datalab}",
        table_name=f"{table_name}",
        path=f"{s3_path}",
        external=True,
    )
    # Closing to prevent timeout
    devo.close()
    logging.warning("Upload successful")


def replace_missing_in_string_column(df, col, placeholder="__missing__"):
    """
    Replace empty strings, single spaces, None, and NaN in a string column
    with a specified placeholder (default: "__missing__").

    Parameters:
        df (pd.DataFrame): The dataframe containing the column
        col (str): Name of the column to process
        placeholder (str): Placeholder to use for missing or empty values

    Returns:
        pd.DataFrame: Modified dataframe with replaced values
    """
    df = df.copy()

    # Convert the column to string type to safely apply string comparisons
    df[col] = df[col].astype(str)

    # Replace problematic values
    df[col] = df[col].replace(["", " ", "None", "nan", "NaN"], placeholder)

    return df


def dfe_wide_to_dfs_long(df_e: pd.DataFrame) -> pd.DataFrame:

    # TREATING CORRECTLY MISSING VALUES TO RESHAPE
    df_e = replace_missing_in_string_column(df_e, ["Breakdown", "Breakdown_label"])

    # REASHAPING
    df_e_long = pd.melt(
        df_e,
        id_vars=[
            "wave",
            # "Topic", # We dont have this in df_s
            # "Var_label", # We dont have this in df_s
            "Var",
            "Breakdown",
            "Breakdown_label",
            "N",  # No needed, but we want to keep it
            "N_Weighted",  # No needed, but we want to keep it
        ],
        value_vars=[
            "Mean",
            "Median",
            "The_same",
            "Up",
            "Down",
            "Net_perc",
            "Grow",
            "Shrink",
            "Harder",
            "Easier",
            "Yes",
            "Expectations_med",
            "Uncertainty_med",
            "Not_applicable",
            # "flag_N",
        ],
        var_name="indicator",
        value_name="value",
    )

    # IDENTIFIERS
    # Create "country" column
    df_e_long["country"] = np.where(
        df_e_long["Breakdown"] == "Country", df_e_long["Breakdown_label"], "EA"
    )  # Fully vectorised and more readable.

    # Create "breakdown_other"
    df_e_long["breakdown_other"] = np.where(
        (df_e_long["Breakdown"].isin(["Age", "Income"])),
        df_e_long["Breakdown"],
        "__missing__",
    )

    df_e_long["breakdown_other_categ"] = np.where(
        df_e_long["Breakdown"].isin(["Age", "Income"]),
        df_e_long["Breakdown_label"],
        "__missing__",
    )

    # INDICATORS
    # Creating column "qualitative_measure"
    df_e_long["qualitative_measure"] = np.where(
        ~df_e_long["indicator"].isin(
            ["Mean", "Median", "Expectations_med", "Uncertainty_med"]
        ),  # Not in this list
        df_e_long["indicator"],
        "__missing__",
    )

    # Creating column "indicator" as in df_s.
    df_e_long["indicator_dfs"] = np.where(
        df_e_long["indicator"].isin(
            ["Mean", "Median", "Expectations_med", "Uncertainty_med"]
        ),
        df_e_long["indicator"],
        "share",
    )
    df_e_long.drop(columns="indicator", inplace=True)
    df_e_long.rename(
        columns={"indicator_dfs": "indicator"}, inplace=True
    )  # new "indicator"

    # MAPPING: matching exact values as in dfs
    # 1
    df_e_long["breakdown_other"] = df_e_long["breakdown_other"].str.lower()
    # 2
    df_e_long["breakdown_other_categ"] = (
        df_e_long["breakdown_other_categ"]
        .map(MAPPING_BREAKDOWN_AGE_VALUES)
        .combine_first(df_e_long["breakdown_other_categ"])
    )
    # 3
    df_e_long["qualitative_measure"] = (
        df_e_long["qualitative_measure"]
        .map(MAPPING_COLUMN_NAMES)
        .combine_first(df_e_long["qualitative_measure"])
    )
    df_e_long["indicator"] = (
        df_e_long["indicator"]
        .map(MAPPING_COLUMN_NAMES)
        .combine_first(df_e_long["indicator"])
    )

    # CLEANING
    # Renaming columns as in df_s
    df_e_long.rename(columns=MAPPING_COLUMN_NAMES, inplace=True)

    # Dropping and ordering columns as in df_s
    extra_cols = [col for col in df_e_long.columns if col not in COLUMNS_ORDER_DFS]
    if extra_cols:
        print("Dropping extra columns that doesn't appear in df_s table:", extra_cols)
    df_e_long = df_e_long[
        [col for col in COLUMNS_ORDER_DFS if col in df_e_long.columns]
    ]

    # Dropping missing values in "value"
    df_e_long.dropna(subset=["value"], inplace=True)

    # Sorting values
    df_e_long = df_e_long.sort_values(
        by=[
            "variable",
            "indicator",
            "qualitative_measure",
            "country",
            "breakdown_other",
            "breakdown_other_categ",
            "wave",
        ],
        ignore_index=True,
    )

    # Round to the first decimal values in column "value"
    # df_e_long["value"] = df_e_long["value"].round(1)

    return df_e_long


def dfs_long_to_dfe_wide(df_s: pd.DataFrame) -> pd.DataFrame:
    # TREATING CORRECTLY MISSING VALUES TO RESHAPE
    df_s = replace_missing_in_string_column(
        df_s, ["breakdown_other", "breakdown_other_categ", "qualitative_measure"]
    )
    df_s["breakdown_other_categ"] = df_s["breakdown_other_categ"].str.replace(
        r"\.0$", "", regex=True
    )

    # BUILDING IDENTIFIERS:
    # Creating "Breakdown"column
    df_s["Breakdown"] = np.where(
        df_s["breakdown_other"].isin(["age", "income"]),
        df_s["breakdown_other"].str.capitalize(),  # In capital letter as in df_e
        np.where(df_s["country"] == "EA", "Wave", "Country"),
    )

    # Creating "Breakdown_label" column #
    df_s["Breakdown_label"] = np.where(
        df_s["breakdown_other"].isin(["age", "income"]),
        df_s["breakdown_other_categ"],
        np.where(df_s["country"] != "EA", df_s["country"], "__missing__"),
    )

    # PREPARING INDICATOR:
    # Creating a "indicator_for_wide" that will collect share and non-share type
    df_s["indicator_for_wide"] = np.where(
        df_s["indicator"] == "share", df_s["qualitative_measure"], df_s["indicator"]
    )

    # RESHAPING TO WIDE FORMAT
    df_s_wide = df_s.pivot(
        index=[
            "date",
            "wave",
            "Breakdown",
            "Breakdown_label",
            "variable",
            "sample_size",
            "population_size",
            "flag_n",
        ],
        columns=["indicator_for_wide"],
        values=["value"],
    )
    # Flatting multi-index after pivot
    df_s_wide = df_s_wide.reset_index()
    df_s_wide.columns = [
        col if isinstance(col, str) else col[1] if col[0] == "value" else col[0]
        for col in df_s_wide.columns
    ]
    # Adding 2 missing columns
    df_s_wide["Topic"] = df_s_wide["variable"].map(VAR_TOPIC_MAPPING)
    df_s_wide["Var_label"] = df_s_wide["variable"].map(VAR_LABEL_MAPPING)

    # CLEANING
    # Renaming columns
    reverse_mappping = {v: k for k, v in MAPPING_COLUMN_NAMES.items()}
    df_s_wide.rename(columns=reverse_mappping, inplace=True)

    # Reordening columns to match
    available_columns = [col for col in COLUMNS_ORDER_DFE if col in df_s_wide.columns]
    df_s_wide = df_s_wide[available_columns]

    # Sorting values
    df_s_wide = df_s_wide.sort_values(
        by=["Var", "Breakdown", "Breakdown_label", "wave"],
        ignore_index=True,
    )

    return df_s_wide


def compare_dataframes(
    df1, df2, id_cols, value_col="value", rtol=1e-5, atol=1e-8, nan_equal=True
):
    """
    Compare values in two dataframes by identifier columns.

    Parameters:
    - df1, df2: DataFrames to compare
    - id_cols: list of columns that UNIQUELY identify each row
    - value_col: name of the column to compare (default is "value")
    - rtol, atol: relative and absolute tolerance for comparing floats
    - nan_equal: if True, treats NaNs as equal; if False, NaNs are considered different

    Returns:
    - Tuple of DataFrames: (matches, mismatches, unmatched_df1, unmatched_df2)
    """
    # Inner join on identifier columns
    merged = df1.merge(df2, on=id_cols, suffixes=("_df1", "_df2"))

    # Find unmatched rows from both dataframes
    df1_keys = df1[id_cols].drop_duplicates()
    df2_keys = df2[id_cols].drop_duplicates()
    merged_keys = merged[id_cols].drop_duplicates()

    unmatched_df1 = df1[
        ~df1[id_cols].apply(tuple, axis=1).isin(merged_keys.apply(tuple, axis=1))
    ]
    unmatched_df2 = df2[
        ~df2[id_cols].apply(tuple, axis=1).isin(merged_keys.apply(tuple, axis=1))
    ]

    # Warning
    if len(df1) != len(merged):
        print(
            f"Warning: df1 has {len(df1)} rows but only {len(merged)} rows matched in the merge."
        )
    if len(df2) != len(merged):
        print(
            f"Warning: df2 has {len(df2)} rows but only {len(merged)} rows matched in the merge."
        )

    # Compare values using np.isclose (handles scalars and arrays)
    is_match = np.isclose(
        merged[f"{value_col}_df1"],
        merged[f"{value_col}_df2"],
        rtol=rtol,
        atol=atol,
        equal_nan=nan_equal,
    )
    # Create matches and mismatches dataframes
    matches_df = merged.loc[
        is_match, id_cols + [f"{value_col}_df1", f"{value_col}_df2"]
    ]
    mismatches_df = merged.loc[
        ~is_match, id_cols + [f"{value_col}_df1", f"{value_col}_df2"]
    ]

    # Print summary
    print(f"{len(matches_df)} matches found.")
    print(f"{len(mismatches_df)} mismatches found.")
    print(f"{len(unmatched_df1)} rows from df1 had no match in df2.")
    print(f"{len(unmatched_df2)} rows from df2 had no match in df1.")

    return matches_df, mismatches_df, unmatched_df1, unmatched_df2


def main_comparing_long_format(
    df_s: pd.DataFrame, df_e: pd.DataFrame, col_to_compare: str = "value"
):

    # PREPARE_DF_S
    df_s = replace_missing_in_string_column(
        df_s, ["breakdown_other", "breakdown_other_categ", "qualitative_measure"]
    )
    df_s["breakdown_other_categ"] = df_s["breakdown_other_categ"].str.replace(
        r"\.0$", "", regex=True
    )

    # TRANSFORMING DF_E TO DF_S LONG FORMAT
    df_e_long = dfe_wide_to_dfs_long(df_e)

    # CALCULATING REAL_MISMATCHES
    id_cols = [
        "wave",
        "country",
        "breakdown_other",
        "breakdown_other_categ",
        "variable",
        "qualitative_measure",
        "indicator",
    ]
    matches_df, mismatches_df, unmatched_df1, unmatched_df2 = compare_dataframes(
        df_s, df_e_long, id_cols, col_to_compare
    )
    mismatches_df["difference"] = abs(
        mismatches_df[col_to_compare + "_df1"] - mismatches_df[col_to_compare + "_df2"]
    )
    real_mismatches = mismatches_df[mismatches_df["difference"] > 0.1]
    return matches_df, mismatches_df, unmatched_df1, unmatched_df2


def main_comparing_wide_format(
    df_s: pd.DataFrame, df_e: pd.DataFrame, col_to_compare: str
):

    # PREPARE_DF_E
    df_e = replace_missing_in_string_column(df_e, ["Breakdown", "Breakdown_label"])

    # TRANSFORMING DF_S TO DF_E LONG FORMAT
    df_s_wide = dfs_long_to_dfe_wide(df_s)

    # CALCULATING REAL_MISMATCHES
    id_cols = [
        "wave",
        "Var",
        "Breakdown",
        "Breakdown_label",
    ]
    matches_df, mismatches_df = compare_dataframes(
        df_s_wide, df_e, id_cols, col_to_compare
    )
    mismatches_df["difference"] = abs(
        mismatches_df[col_to_compare + "_df1"] - mismatches_df[col_to_compare + "_df2"]
    )
    real_mismatches = mismatches_df[mismatches_df["difference"] > 0.1]
    return matches_df, real_mismatches


def convert_date_dashboard(date_str):
    # Parse and reformat
    dt = datetime.strptime(date_str, "%m/%Y")
    return dt.strftime("%Y-%m-%d")


# --------
# Exporting by topic
# ------


def _sheet_name(topic_key: str, name_map: dict[str, str]) -> str:
    if topic_key is None or pd.isna(topic_key):
        raw = "Unmapped"
    else:
        key = str(topic_key)
        raw = name_map.get(key, key.replace("_", " ").title())
    # Excel-safe
    return re.sub(r"[:\\/?*\[\]]", "-", raw)[:31]


def _walk_for_variables(node):
    """Recursively find items with 'variables' lists and yield (var_name, topic)."""
    out = []
    if isinstance(node, dict):
        # If this node has a variables list, harvest it
        vars_list = node.get("variables")
        if isinstance(vars_list, list):
            for d in vars_list:
                if not isinstance(d, dict):
                    continue
                name = d.get("name") or d.get("base") or d.get("var") or d.get("code")
                topic = d.get("topic")
                if name and topic:
                    out.append((str(name), str(topic)))
        # Recurse into children
        for v in node.values():
            out.extend(_walk_for_variables(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_walk_for_variables(v))
    return out


def _load_var2topic(yaml_path: str) -> tuple[dict, list]:
    """
    Builds var->topic mapping from:
      - Root 'topics': {TOPIC: [c1150, ...]}
      - Any nested block with 'variables': [{name|base: code, topic: TOPIC}, ...]
    Returns (mapping, topic_order).
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    var2topic, topic_order = {}, []

    # A) Root 'topics' style (not used in your file, but supported)
    topics_block = cfg.get("topics")
    if isinstance(topics_block, dict):
        for topic, names in topics_block.items():
            if topic not in topic_order:
                topic_order.append(topic)
            for v in names or []:
                var2topic[str(v)] = topic

    # B) Walk nested blocks (works for quantitative/qualitative/prob_bin)
    pairs = _walk_for_variables(cfg)
    for name, topic in pairs:
        if name not in var2topic:
            var2topic[name] = topic
        # preserve first-seen topic order
        if topic not in topic_order:
            topic_order.append(topic)

    if not var2topic:
        raise ValueError(
            "config.yaml missing variable↔topic mapping (looked in nested 'variables' and root 'topics')."
        )
    return var2topic, topic_order


def write_excel_by_topic(
    df_wide: pd.DataFrame,
    yaml_path: str,
    out_xlsx: str,
    var_col: str = "Var",
    topic_name_map: dict[str, str] | None = None,
) -> None:

    TOPIC_SHEET_NAME_MAP = {
        "house_credit": "Housing and credit access",
        "income_consumption": "Income and consumption",
        "inflation": "Inflation",
        "labor_econgrowth": "Labour and economic growth",
    }

    var2topic, topic_order = _load_var2topic(yaml_path)  # topic_order unused now
    name_map = topic_name_map or TOPIC_SHEET_NAME_MAP

    # base code, e.g. 'c1150' from 'c1150_imean'
    base = df_wide[var_col].astype(str).str.extract(r"^([A-Za-z]\d{4})", expand=False)
    df = df_wide.assign(_topic=base.map(var2topic))

    # --- ONLY CHANGE: enforce order from name_map, then any extras
    present = pd.Series(df["_topic"].dropna().unique()).tolist()
    ordered = [t for t in name_map.keys() if t in present]
    extras = sorted(set(present) - set(ordered))
    sheet_order = ordered + extras
    # ---

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as xw:
        for topic in sheet_order:
            df[df["_topic"].eq(topic)].drop(columns=["_topic"]).to_excel(
                xw, sheet_name=_sheet_name(topic, name_map), index=False
            )
        if df["_topic"].isna().any():
            df[df["_topic"].isna()].drop(columns=["_topic"]).to_excel(
                xw, sheet_name=_sheet_name(None, name_map), index=False
            )
