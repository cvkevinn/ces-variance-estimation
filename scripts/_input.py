import logging
import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)


logger = logging.getLogger(__name__)


def create_qualitative_derived(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """
    This function creates up, down, same and netdiff variables for:
    c1010, c1110, c1210, c6010, c6110, c3210, c2110 and e2010.
    """
    df[column + "_up"] = np.where(
        pd.isna(df[column]),
        np.nan,
        np.where((df[column] == 1) | (df[column] == 3), 100, 0),
    )

    df[column + "_down"] = np.where(
        pd.isna(df[column]),
        np.nan,
        np.where((df[column] == 2) | (df[column] == 4), 100, 0),
    )

    df[column + "_same"] = np.where(
        pd.isna(df[column]), np.nan, np.where(df[column] == 5, 100, 0)
    )

    df[column + "_netdiff"] = df[column + "_up"] - df[column + "_down"]

    return df


def create_c4010_derived(df: pd.DataFrame) -> pd.DataFrame:
    df["c4010_grow"] = np.where(
        pd.isna(df["c4010"]), np.nan, np.where(df["c4010"] == 1, 100, 0)
    )
    df["c4010_shrink"] = np.where(
        pd.isna(df["c4010"]), np.nan, np.where(df["c4010"] == 2, 100, 0)
    )
    df["c4010_same"] = np.where(
        pd.isna(df["c4010"]), np.nan, np.where(df["c4010"] == 3, 100, 0)
    )
    df["c4010_netdiff"] = df["c4010_grow"] - df["c4010_shrink"]
    return df


def create_c7110_c7120_derived(df: pd.DataFrame, column: str) -> pd.DataFrame:
    df[column + "_harder"] = np.where(
        pd.isna(df[column]) | (df[column] == -777),
        np.nan,
        np.where((df[column] == 1) | (df[column] == 2), 100, 0),
    )

    df[column + "_easier"] = np.where(
        pd.isna(df[column]) | (df[column] == -777),
        np.nan,
        np.where((df[column] == 4) | (df[column] == 5), 100, 0),
    )

    df[column + "_same"] = np.where(
        pd.isna(df[column]) | (df[column] == -777),
        np.nan,
        np.where(df[column] == 3, 100, 0),
    )

    df[column + "_netdiff"] = df[column + "_harder"] - df[column + "_easier"]

    return df


def create_c7110_c7120_derived_ea6(df: pd.DataFrame, column: str) -> pd.DataFrame:
    df[column + "_harder"] = np.where(
        pd.isna(df[column]),
        np.nan,
        np.where((df[column] == 1) | (df[column] == 2), 100, 0),
    )

    df[column + "_easier"] = np.where(
        pd.isna(df[column]),
        np.nan,
        np.where((df[column] == 4) | (df[column] == 5), 100, 0),
    )

    df[column + "_same"] = np.where(
        pd.isna(df[column]),
        np.nan,
        np.where(df[column] == 3, 100, 0),
    )

    df[column + "_notapplicable"] = np.where(
        pd.isna(df[column]),
        np.nan,
        np.where((df[column] == -777), 100, 0),
    )

    df[column + "_netdiff"] = df[column + "_harder"] - df[column + "_easier"]
    return df


def create_q4010_derived(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """
    This function creates 'yes' and 'no' shares variables for:
    q4010.
    """
    df[column + "_yes"] = np.where(
        pd.isna(df[column]),
        np.nan,
        np.where((df[column] == 1), 100, 0),
    )

    df[column + "_no"] = np.where(
        pd.isna(df[column]),
        np.nan,
        np.where((df[column] == 0), 100, 0),
    )
    return df


def calculate_bootstrap_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["a0020"] = df["a0020"].astype("category")
    df["pr2010"] = df["pr2010"].astype("category")

    g_aw = df.groupby(["a0020", "wave"], sort=False, observed=True)
    g_awp = df.groupby(["a0020", "wave", "pr2010"], sort=False, observed=True)

    # Row counts per group (size counts all rows, including NaNs in other cols)
    df["n"] = g_aw["wave"].transform("size")
    df["ns"] = g_awp["wave"].transform("size")

    # Weighted sums per group
    df["N"] = g_aw["wgt_calib"].transform("sum")
    df["Ns"] = g_awp["wgt_calib"].transform("sum")

    return df


def calculate_bootstrap_flag(df: pd.DataFrame) -> pd.DataFrame:
    # if duplicates leaked in, guard again
    df = df.loc[:, ~df.columns.duplicated()].copy()

    a0020 = df["a0020"].astype(str)
    pr2010 = df["pr2010"].astype(str)
    wave_str = df["wave"].astype("Int64").fillna(0).astype(int).astype(str).str.zfill(2)

    df["sample"] = a0020 + pr2010 + "_" + wave_str
    return df


def calculate_all_vars_derived(df, varlist):
    for var in varlist:
        if var in df.columns:
            if var == "c4010":
                create_c4010_derived(df)
            elif (var == "c7110") or (var == "c7120"):
                create_c7110_c7120_derived(df, var)
            elif var == "q4010":
                create_q4010_derived(df, var)
            else:
                create_qualitative_derived(df, var)
        else:
            logger.warning(f"Variable '{var}' not found in dataframe. Skipping...")
    return df


def calculate_all_vars_derived_ea6(df, varlist):
    for var in varlist:
        if var in df.columns:
            if var == "c4010":
                create_c4010_derived(df)
            elif (var == "c7110") or (var == "c7120"):
                create_c7110_c7120_derived_ea6(df, var)
            elif var == "q4010":
                create_q4010_derived(df, var)
            else:
                create_qualitative_derived(df, var)
        else:
            logger.warning(f"Variable '{var}' not found in dataframe. Skipping...")
    return df


def main_input_preparations(
    df: pd.DataFrame,
    varlist: list[str],
    vars_type: str,
    breakdown_vars: list[str],
) -> pd.DataFrame:
    df = df.copy()
    ## Calculating derived qualitative variables when needed
    if vars_type == "qualitative":
        df = calculate_all_vars_derived(df, varlist)

    ## Cleaning/transformation
    df = df.dropna(subset=["wave"])
    df = df.dropna(subset=["pr2010"])
    df = df.dropna(subset=["wgt_bld"])
    df = df[df["wave"] >= 4]
    countries_to_filter = ["AT", "EL", "FI", "IE", "PT"]
    condition = ~((df["a0020"].isin(countries_to_filter)) & (df["wave"] < 28))
    df = df[condition]

    ## Changing variables type
    df["pr2010"] = df["pr2010"].astype(int)
    df["wave"] = df["wave"].astype(int)
    try:
        for var in breakdown_vars:
            df[var] = df[var].astype(int)
    except:
        pass

    ## Creating neccesary aggregates and flags variables for bootstrap calculation
    df = calculate_bootstrap_aggregates(df)
    df = calculate_bootstrap_flag(df)

    df.sort_values(by=["a0020", "a0010", "wave"], ignore_index=True, inplace=True)
    return df


def main_input_preparations_ea6(
    df: pd.DataFrame,
    varlist: list[str],
    vars_type: str,
    breakdown_vars: list[str],
) -> pd.DataFrame:
    df = df.copy()
    ## Calculating derived qualitative variables when needed
    if vars_type == "qualitative":
        df = calculate_all_vars_derived_ea6(df, varlist)

    ## Cleaning/transformation
    df = df.dropna(subset=["wave"])
    df = df.dropna(subset=["pr2010"])
    df = df.dropna(subset=["wgt_bld"])

    df = df[df["wave"] >= 4]
    countries_to_filter = ["AT", "EL", "FI", "IE", "PT"]
    # condition = ~((df["a0020"].isin(countries_to_filter)) & (df["wave"] < 28))
    # df = df[condition]
    df = df[~df["a0020"].isin(countries_to_filter)]  # We focus only in main 6

    ## Changing variables type
    df["pr2010"] = df["pr2010"].astype(int)
    df["wave"] = df["wave"].astype(int)
    try:
        for var in breakdown_vars:
            df[var] = df[var].astype(int)
    except:
        pass

    ## Creating neccesary aggregates and flags variables for bootstrap calculation
    df = calculate_bootstrap_aggregates(df)
    df = calculate_bootstrap_flag(df)

    df.sort_values(by=["a0020", "a0010", "wave"], ignore_index=True, inplace=True)
    return df


if __name__ == "__main__":
    pass
