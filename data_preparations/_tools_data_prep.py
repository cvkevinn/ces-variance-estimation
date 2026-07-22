import os
import logging
from matplotlib import table
import pandas as pd
import numpy as np
from connectors import devo
from scripts._winsor import calculate_winsorized_variable
from settings import table_storage_path

logger = logging.getLogger(__name__)


# --------------------------
# Creating monthly derived variables
# --------------------------
def calculate_c6020_derived(df):
    df = df.copy()
    df["c6020_agg"] = df["c6020"].where(df["c6020"] != -999)
    df = calculate_winsorized_variable(df, "c6020_agg", "wgt_bld")
    ## conditional median of values that fall between bracket edges

    # perceptions
    condition1 = df["c6020_agg_w"].between(-2, 0, "neither")
    condition2 = df["c6020_agg_w"].between(-4, -2, "right")
    condition3 = df["c6020_agg_w"].between(-7, -4, "right")
    condition4 = df["c6020_agg_w"].between(-11, -7, "right")
    condition5 = df["c6020_agg_w"].between(-16, -11, "right")
    condition6 = df["c6020_agg_w"].between(-20, -16, "both")
    condition7 = df["c6020_agg_w"].between(-float("inf"), -20, "neither")

    condition8 = df["c6020_agg_w"].between(0, 2, "neither")
    condition9 = df["c6020_agg_w"].between(2, 4, "left")
    condition10 = df["c6020_agg_w"].between(4, 7, "left")
    condition11 = df["c6020_agg_w"].between(7, 11, "left")
    condition12 = df["c6020_agg_w"].between(11, 16, "left")
    condition13 = df["c6020_agg_w"].between(16, 20, "both")
    condition14 = df["c6020_agg_w"].between(20, float("inf"), "neither")

    condition_median = [
        condition1,
        condition2,
        condition3,
        condition4,
        condition5,
        condition6,
        condition7,
        condition8,
        condition9,
        condition10,
        condition11,
        condition12,
        condition13,
        condition14,
    ]

    condition1_rep = (df["c6030"] == 1) & (df["c6010"].isin([2, 4]))
    condition2_rep = (df["c6030"] == 2) & (df["c6010"].isin([2, 4]))
    condition3_rep = (df["c6030"] == 3) & (df["c6010"].isin([2, 4]))
    condition4_rep = (df["c6030"] == 4) & (df["c6010"].isin([2, 4]))
    condition5_rep = (df["c6030"] == 5) & (df["c6010"].isin([2, 4]))
    condition6_rep = (df["c6030"] == 6) & (df["c6010"].isin([2, 4]))
    condition7_rep = (df["c6030"] == 7) & (df["c6010"].isin([2, 4]))

    condition8_rep = (df["c6030"] == 1) & (df["c6010"].isin([1, 3]))
    condition9_rep = (df["c6030"] == 2) & (df["c6010"].isin([1, 3]))
    condition10_rep = (df["c6030"] == 3) & (df["c6010"].isin([1, 3]))
    condition11_rep = (df["c6030"] == 4) & (df["c6010"].isin([1, 3]))
    condition12_rep = (df["c6030"] == 5) & (df["c6010"].isin([1, 3]))
    condition13_rep = (df["c6030"] == 6) & (df["c6010"].isin([1, 3]))
    condition14_rep = (df["c6030"] == 7) & (df["c6010"].isin([1, 3]))

    condition_rep = [
        condition1_rep,
        condition2_rep,
        condition3_rep,
        condition4_rep,
        condition5_rep,
        condition6_rep,
        condition7_rep,
        condition8_rep,
        condition9_rep,
        condition10_rep,
        condition11_rep,
        condition12_rep,
        condition13_rep,
        condition14_rep,
    ]

    for c in range(0, 14):
        filtered_df = df[condition_median[c]]
        cond_med = filtered_df.groupby("wave")["c6020_agg_w"].median()
        df.loc[condition_rep[c], "c6020_median"] = df.loc[condition_rep[c], "wave"].map(
            cond_med
        )

    df["c6020_rec"] = df["c6020_agg_w"].combine_first(df["c6020_median"])

    # additional corrections for waves / brackets with missing values
    condition_neg = (df["c6020_rec"].isna()) & (df["c6010"].isin([2, 4]))
    df.loc[(condition_neg & (df["c6030"] == 1)), "c6020_rec"] = -1
    df.loc[(condition_neg & (df["c6030"] == 2)), "c6020_rec"] = -2.5
    df.loc[(condition_neg & (df["c6030"] == 3)), "c6020_rec"] = -5
    df.loc[(condition_neg & (df["c6030"] == 4)), "c6020_rec"] = -8.5
    df.loc[(condition_neg & (df["c6030"] == 5)), "c6020_rec"] = -13
    df.loc[(condition_neg & (df["c6030"] == 6)), "c6020_rec"] = -17.5

    condition_pos = (df["c6020_rec"].isna()) & (df["c6010"].isin([1, 3]))
    df.loc[(condition_pos & (df["c6030"] == 1)), "c6020_rec"] = 1
    df.loc[(condition_pos & (df["c6030"] == 2)), "c6020_rec"] = 2.5
    df.loc[(condition_pos & (df["c6030"] == 3)), "c6020_rec"] = 5
    df.loc[(condition_pos & (df["c6030"] == 4)), "c6020_rec"] = 8.5
    df.loc[(condition_pos & (df["c6030"] == 5)), "c6020_rec"] = 13
    df.loc[(condition_pos & (df["c6030"] == 6)), "c6020_rec"] = 17.5

    # manual corrections following Stata code
    condition_neg_7 = (df["c6020_rec"].isna()) & (
        df["c6010"].isin([2, 4]) & (df["c6030"] == 7)
    )
    df.loc[condition_neg_7 & (df["a0020"] == "AT"), "c6020_rec"] = -29
    df.loc[condition_neg_7 & (df["a0020"] == "BE"), "c6020_rec"] = -23.2
    df.loc[condition_neg_7 & (df["a0020"] == "DE"), "c6020_rec"] = -29
    df.loc[condition_neg_7 & (df["a0020"] == "EL"), "c6020_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "ES"), "c6020_rec"] = -30
    df.loc[condition_neg_7 & (df["a0020"] == "FI"), "c6020_rec"] = -29
    df.loc[condition_neg_7 & (df["a0020"] == "FR"), "c6020_rec"] = -25.5
    df.loc[condition_neg_7 & (df["a0020"] == "IE"), "c6020_rec"] = -26.5
    df.loc[condition_neg_7 & (df["a0020"] == "IT"), "c6020_rec"] = -28
    df.loc[condition_neg_7 & (df["a0020"] == "NL"), "c6020_rec"] = -22
    df.loc[condition_neg_7 & (df["a0020"] == "PT"), "c6020_rec"] = -29

    condition_pos_7 = (df["c6020_rec"].isna()) & (
        df["c6010"].isin([1, 3]) & (df["c6030"] == 7)
    )
    df.loc[condition_pos_7 & (df["a0020"] == "AT"), "c6020_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "BE"), "c6020_rec"] = 27.15
    df.loc[condition_pos_7 & (df["a0020"] == "DE"), "c6020_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "EL"), "c6020_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "ES"), "c6020_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "FI"), "c6020_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "FR"), "c6020_rec"] = 25
    df.loc[condition_pos_7 & (df["a0020"] == "IE"), "c6020_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "IT"), "c6020_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "NL"), "c6020_rec"] = 25.5
    df.loc[condition_pos_7 & (df["a0020"] == "PT"), "c6020_rec"] = 30
    df = df.drop(["c6020", "c6030", "c6020_agg", "c6020_agg_w", "c6020_median"], axis=1)
    return df


def calculate_c6120_derived(df):
    df = df.copy()
    df["c6120_agg"] = df["c6120"].where(df["c6120"] != -999)
    df = calculate_winsorized_variable(df, "c6120_agg", "wgt_bld")

    condition1_exp = df["c6120_agg_w"].between(-2, 0, "neither")
    condition2_exp = df["c6120_agg_w"].between(-4, -2, "right")
    condition3_exp = df["c6120_agg_w"].between(-7, -4, "right")
    condition4_exp = df["c6120_agg_w"].between(-11, -7, "right")
    condition5_exp = df["c6120_agg_w"].between(-16, -11, "right")
    condition6_exp = df["c6120_agg_w"].between(-20, -16, "both")
    condition7_exp = df["c6120_agg_w"].between(-float("inf"), -20, "neither")

    condition8_exp = df["c6120_agg_w"].between(0, 2, "neither")
    condition9_exp = df["c6120_agg_w"].between(2, 4, "left")
    condition10_exp = df["c6120_agg_w"].between(4, 7, "left")
    condition11_exp = df["c6120_agg_w"].between(7, 11, "left")
    condition12_exp = df["c6120_agg_w"].between(11, 16, "left")
    condition13_exp = df["c6120_agg_w"].between(16, 20, "both")
    condition14_exp = df["c6120_agg_w"].between(20, float("inf"), "neither")

    condition_median_exp = [
        condition1_exp,
        condition2_exp,
        condition3_exp,
        condition4_exp,
        condition5_exp,
        condition6_exp,
        condition7_exp,
        condition8_exp,
        condition9_exp,
        condition10_exp,
        condition11_exp,
        condition12_exp,
        condition13_exp,
        condition14_exp,
    ]

    condition1_rep_exp = (df["c6130"] == 1) & (df["c6110"].isin([2, 4]))
    condition2_rep_exp = (df["c6130"] == 2) & (df["c6110"].isin([2, 4]))
    condition3_rep_exp = (df["c6130"] == 3) & (df["c6110"].isin([2, 4]))
    condition4_rep_exp = (df["c6130"] == 4) & (df["c6110"].isin([2, 4]))
    condition5_rep_exp = (df["c6130"] == 5) & (df["c6110"].isin([2, 4]))
    condition6_rep_exp = (df["c6130"] == 6) & (df["c6110"].isin([2, 4]))
    condition7_rep_exp = (df["c6130"] == 7) & (df["c6110"].isin([2, 4]))

    condition8_rep_exp = (df["c6130"] == 1) & (df["c6110"].isin([1, 3]))
    condition9_rep_exp = (df["c6130"] == 2) & (df["c6110"].isin([1, 3]))
    condition10_rep_exp = (df["c6130"] == 3) & (df["c6110"].isin([1, 3]))
    condition11_rep_exp = (df["c6130"] == 4) & (df["c6110"].isin([1, 3]))
    condition12_rep_exp = (df["c6130"] == 5) & (df["c6110"].isin([1, 3]))
    condition13_rep_exp = (df["c6130"] == 6) & (df["c6110"].isin([1, 3]))
    condition14_rep_exp = (df["c6130"] == 7) & (df["c6110"].isin([1, 3]))

    condition_rep_exp = [
        condition1_rep_exp,
        condition2_rep_exp,
        condition3_rep_exp,
        condition4_rep_exp,
        condition5_rep_exp,
        condition6_rep_exp,
        condition7_rep_exp,
        condition8_rep_exp,
        condition9_rep_exp,
        condition10_rep_exp,
        condition11_rep_exp,
        condition12_rep_exp,
        condition13_rep_exp,
        condition14_rep_exp,
    ]

    for c in range(0, 14):
        filtered_df = df[condition_median_exp[c]]
        cond_med = filtered_df.groupby("wave")["c6120_agg_w"].median()
        df.loc[condition_rep_exp[c], "c6120_median"] = df.loc[
            condition_rep_exp[c], "wave"
        ].map(cond_med)

    df["c6120_rec"] = df["c6120_agg_w"].combine_first(df["c6120_median"])

    ## conditional median of values that fall between bracket edges
    condition_neg = (df["c6120_rec"].isna()) & (df["c6110"].isin([2, 4]))
    df.loc[(condition_neg & (df["c6130"] == 1)), "c6120_rec"] = -1
    df.loc[(condition_neg & (df["c6130"] == 2)), "c6120_rec"] = -2.5
    df.loc[(condition_neg & (df["c6130"] == 3)), "c6120_rec"] = -5
    df.loc[(condition_neg & (df["c6130"] == 4)), "c6120_rec"] = -8.5
    df.loc[(condition_neg & (df["c6130"] == 5)), "c6120_rec"] = -13
    df.loc[(condition_neg & (df["c6130"] == 6)), "c6120_rec"] = -17.5

    condition_pos = (df["c6120_rec"].isna()) & (df["c6110"].isin([1, 3]))
    df.loc[(condition_pos & (df["c6130"] == 1)), "c6120_rec"] = 1
    df.loc[(condition_pos & (df["c6130"] == 2)), "c6120_rec"] = 2.5
    df.loc[(condition_pos & (df["c6130"] == 3)), "c6120_rec"] = 5
    df.loc[(condition_pos & (df["c6130"] == 4)), "c6120_rec"] = 8.5
    df.loc[(condition_pos & (df["c6130"] == 5)), "c6120_rec"] = 13
    df.loc[(condition_pos & (df["c6130"] == 6)), "c6120_rec"] = 17.5

    # manual corrections following Stata code
    condition_neg_7 = (df["c6120_rec"].isna()) & (
        df["c6110"].isin([2, 4]) & (df["c6130"] == 7)
    )
    df.loc[condition_neg_7 & (df["a0020"] == "AT"), "c6120_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "BE"), "c6120_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "DE"), "c6120_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "EL"), "c6120_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "ES"), "c6120_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "FI"), "c6120_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "FR"), "c6120_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "IE"), "c6120_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "IT"), "c6120_rec"] = -30
    df.loc[condition_neg_7 & (df["a0020"] == "NL"), "c6120_rec"] = -25
    df.loc[condition_neg_7 & (df["a0020"] == "PT"), "c6120_rec"] = -25

    condition_pos_7 = (df["c6120_rec"].isna()) & (
        df["c6110"].isin([1, 3]) & (df["c6130"] == 7)
    )
    df.loc[condition_pos_7 & (df["a0020"] == "AT"), "c6120_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "BE"), "c6120_rec"] = 25
    df.loc[condition_pos_7 & (df["a0020"] == "DE"), "c6120_rec"] = 25
    df.loc[condition_pos_7 & (df["a0020"] == "EL"), "c6120_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "ES"), "c6120_rec"] = 25
    df.loc[condition_pos_7 & (df["a0020"] == "FI"), "c6120_rec"] = 25.5
    df.loc[condition_pos_7 & (df["a0020"] == "FR"), "c6120_rec"] = 22.2
    df.loc[condition_pos_7 & (df["a0020"] == "IE"), "c6120_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "IT"), "c6120_rec"] = 30
    df.loc[condition_pos_7 & (df["a0020"] == "NL"), "c6120_rec"] = 25
    df.loc[condition_pos_7 & (df["a0020"] == "PT"), "c6120_rec"] = 30
    df = df.drop(["c6120", "c6130", "c6120_agg", "c6120_agg_w", "c6120_median"], axis=1)
    return df


# --------------------------
# Creating quartaerly derived variables
# --------------------------
def calculate_q2300_derived(df):
    df["q2300_rec"] = df["q2300_rec"].replace([-999, -888, -777, -666], np.nan)
    # df = df.rename(columns={"a0030": "wave"})
    # df = calculate_winsorized_variable(df, "q2300_rec", "wgt_bld_q")
    # df.drop(
    #     columns=["q2300_rec"],
    #     inplace=True,
    # )
    return df


def calculate_q2350_derived(df):
    df["q2350_rec"] = df["q2350_rec"].replace([-999, -888, -777, -666], np.nan)
    # df = df.rename(columns={"a0030": "wave"})
    # df = calculate_winsorized_variable(df, "q2350_rec", "wgt_bld_q")
    # df.drop(
    #     columns=["q2350_rec"],
    #     inplace=True,
    # )
    return df


def calculate_q2390_derived(df):
    df["q2390_rec"] = df["q2390_rec"].replace([-999, -888, -777, -666], np.nan)
    # df = df.rename(columns={"a0030": "wave"})
    # df = calculate_winsorized_variable(df, "q2390_rec", "wgt_bld_q")
    # df.drop(
    #     columns=["q2390_rec"],
    #     inplace=True,
    # )
    return df


def calculate_q4010_derived(df: pd.DataFrame) -> pd.DataFrame:
    q4010_sum = [f"q4010_{i}_rec" for i in range(1, 9)]
    df["q4010_sum"] = df[q4010_sum].sum(axis=1, min_count=1)
    df.loc[(df["q4010_sum"] > 0), "q4010_rec"] = 1
    df.loc[df["q4010_9_rec"] == 1, "q4010_rec"] = 0
    df.drop(
        columns=[
            "q4010_1_rec",
            "q4010_2_rec",
            "q4010_3_rec",
            "q4010_4_rec",
            "q4010_5_rec",
            "q4010_6_rec",
            "q4010_7_rec",
            "q4010_8_rec",
            "q4010_9_rec",
            "q4010_sum",
        ],
        inplace=True,
    )
    return df


# --------------------------
# Other tools
# --------------------------


def get_latest_probin_table():
    logger.info(f"Getting probabilistic bin microdata table from DEVO.")
    
    query=f"SELECT * FROM lab_prj_ces.core_uncertainty_probbins"

    df = devo.read_sql(query)
    devo.close()

    return df


def merge_variable_versions(df, mapping_dict):
    df_out = df.copy()
    for new_var, old_vars in mapping_dict.items():
        df_out[new_var] = np.nan
        for var in old_vars:
            if var in df_out.columns:
                df_out[new_var] = df_out[new_var].combine_first(df_out[var])
    return df_out


def drop_old_versions(df, mapping_dict):
    cols_to_drop = [
        col for sublist in mapping_dict.values() for col in sublist if col in df.columns
    ]
    return df.drop(columns=cols_to_drop)


def download_table(
    datalab: str,
    table_name: str,
    varlist: list[str],
    # status: str,
) -> pd.DataFrame:

    base_vars = ["a0010", "a0020", "a0030"]
    if isinstance(varlist, str):
        if varlist != "all":
            raise ValueError("If varlist is string, the only input possible is 'all'.")
        else:
            query_vars = "*"
    else:
        query_vars = ", ".join(base_vars + varlist)
    logger.info(
        f"Downloading TABLE: '{table_name}' from LAB 'lab_{datalab}'. VARIABLES: {query_vars}."
    )
    query = f"SELECT {query_vars} FROM lab_{datalab}.{table_name}"
    df = devo.read_sql(query)
    return df


def upload_table(df: pd.DataFrame, datalab: str, table_name: str):

    s3_path = table_storage_path(datalab, table_name)
    logger.info(f"Uploading table '{table_name}' to 'lab_{datalab}'")

    devo.create_table(
        df,
        lab=f"lab_{datalab}",
        table_name=f"{table_name}",
        path=f"{s3_path}",
        external=True,
    )
    # Closing to prevent timeout
    devo.close()
    logger.info(f"Table 'lab_{datalab}.{table_name}': Uploaded Successfully.")


def download_core_superview(
    varlist: str | list[str],
    wave: int | None = None,
    # quarterly: bool = False,
) -> pd.DataFrame:

    # if quarterly:
    #     base_vars = {
    #         "a0010_q",
    #         "a0020_q",
    #         "wave_q",
    #         "a1110_calib_rec_q",  # quarterly_derived
    #         "b7040_imp_quintiles_q",  # quarterly_hhincome_stat
    #         "pr2010",  # recruitment
    #         "wgt_calib_q",
    #         "wgt_bld_q",
    #         # "wgt_bld",
    #         "survey_status_q",
    #     }
    # else:
    base_vars = {
        "a0010",
        "a0020",
        "wave",
        "a1110_calib_rec",
        "b7040_imp_quintiles",
        "pr2010",
        "wgt_calib",
        "wgt_bld",
        "survey_status",
    }

    # Handling the varlist
    if isinstance(varlist, str):
        if varlist != "all":
            raise ValueError("If varlist is string, the only input possible is 'all'.")
        query_vars = "*"
    else:
        query_vars = ", ".join(base_vars.union(varlist))

    if wave is not None:
        logger.info(
            f"Downloading TABLE: 'core_super_view' from LAB 'lab_prj_ces'. WAVE: {wave}. VARIABLES: {query_vars}."
        )
        query = (
            f"SELECT {query_vars} FROM lab_prj_ces.core_super_view WHERE wave = {wave}"
        )
    else:
        logger.info(
            f"Downloading TABLE: 'core_super_view' from LAB 'lab_prj_ces'. VARIABLES: {query_vars}."
        )
        query = f"SELECT {query_vars} FROM lab_prj_ces.core_super_view"
    return devo.read_sql(query)


# def download_prob_bin(varlist: str | list[str], wave: int = None) -> pd.DataFrame:

#     logging.warning(
#         f"Downloading TABLE: 'ces_prob_bin' WAVE: {wave} from DEVO 'lab_prj_ces_production'"
#     )

#     base_vars = {"a0010", "wave_ces"}

#     # Handling the varlist
#     if isinstance(varlist, str):
#         if varlist != "all":
#             raise ValueError("If varlist is string, the only input possible is 'all'.")
#         query_vars = "*"
#     else:
#         query_vars = ", ".join(base_vars.union(varlist))

#     if wave is not None:
#         query = f"SELECT {query_vars} FROM lab_prj_ces_production.ces_prob_bin WHERE wave_ces = {wave}"
#     else:
#         query = f"SELECT {query_vars} FROM lab_prj_ces_production.ces_prob_bin"
#     df = devo.read_sql(query)

#     # Closing to prevent timeout
#     devo.close()
#     return df
