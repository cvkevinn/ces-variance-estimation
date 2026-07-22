import pandas as pd
import numpy as np
from others._tools_others import (
    dfs_long_to_dfe_wide,
    download_table,
    convert_date_dashboard,
)
from others._constants_mapping import MAPPING_BREAKDOWN_AGE_VALUES

# # from dge_aggregates import main_dge_aggregates
# df = download_table("prj_ces_production", "aggregates_final_complete", "all")
# df_agg_1 = download_table("prj_ces_production", "aggregates_final_ea6", "all")
# df_agg_2 = download_table("prj_ces_production", "aggregates_final_complete", "all")
# df_agg_1 = df_agg_1[df_agg_1["wave"] < 28]
# df_agg_2 = df_agg_2[df_agg_2["wave"] >= 28]


def main_ces_db_shape(df1: pd.DataFrame, df2: pd.DataFrame) -> pd.DataFrame:

    # APPENDING
    df = pd.concat([df1, df2], axis=0, ignore_index=True)
    df = df[df["qualitative_measure"] != "notapplicable"]

    # ROUNDING
    df["population_size"] = df["population_size"].round(0)
    df["sample_size"] = df["sample_size"].round(0)
    df["value"] = df["value"].round(1)

    # RESHAPING TO DG-E WIDE FORMAT
    df_s = dfs_long_to_dfe_wide(df)

    # Small checks
    df_s = df_s.replace("__missing__", "")

    # 1) AGE VALUES AS IN DG-E
    reverse_mapping_breakdown_age = {
        v: k for k, v in MAPPING_BREAKDOWN_AGE_VALUES.items()
    }
    df_s["Breakdown_label"] = np.where(
        df_s["Breakdown"] == "Age",
        df_s["Breakdown_label"].map(reverse_mapping_breakdown_age),
        df_s["Breakdown_label"],
    )

    # 2) DELETING NOT INCLUDED AGGREGATES
    ## 2.1 Oldest group
    df_s = df_s[df_s["Breakdown_label"] != "70+ years"]

    ## 2.2 Delete aggregates with sample size <20
    df_s = df_s[~(df_s["N"] < 20)]

    # 3) DELETING NOT INCLUDED COLUMNS IN DASBOARD
    df_s.drop(columns=["wave"], axis=1, inplace=True)

    #### TO DASBOARD LONG FORMAT
    df_s_long_db = (
        pd.melt(
            df_s,
            id_vars=["date", "Var", "Breakdown", "Breakdown_label", "N"],
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
                "Expectations_p25",
                "Expectations_p75",
            ],
            var_name="ANSWER",
            value_name="OBS_VALUE",
        )
        .dropna(subset=["OBS_VALUE"])
        .rename(
            columns={
                "date": "OBS_DATE",
                "Var": "QUESTION",
                "Breakdown": "BREAKDOWN_TYPE",
                "Breakdown_label": "BREAKDOWN_GROUP",
                "N": "REPLIES",
            },
        )
    )

    # 1) CHECK TREATING MISSING
    df_s_long_db["BREAKDOWN_TYPE"] = df_s_long_db["BREAKDOWN_TYPE"].replace(
        "Wave", "__missing__"
    )
    df_s_long_db = df_s_long_db.replace("__missing__", "")

    # 2) AD-HOC CHANGES
    df_s_long_db["BREAKDOWN_TYPE"] = df_s_long_db["BREAKDOWN_TYPE"].replace(
        {"Income": "INCOME", "Age": "AGE", "Country": "COUNTRY"}
    )
    ans2q = {
        "Uncertainty_med": "c1150_iqr",
        "Expectations_med": "c1150_imean",
        "Expectations_p25": "c1150_imean",
        "Expectations_p75": "c1150_imean",
    }
    m = df_s_long_db["QUESTION"].eq("c1150")
    df_s_long_db.loc[m, "QUESTION"] = (
        df_s_long_db.loc[m, "ANSWER"].map(ans2q).fillna("c1150")
    )

    # 3) CHANGING DATES FORMAT
    df_s_long_db["OBS_DATE"] = df_s_long_db["OBS_DATE"].apply(convert_date_dashboard)

    # 4) SORTING
    df_s_long_db = df_s_long_db.sort_values(
        by=["QUESTION", "ANSWER", "BREAKDOWN_TYPE", "BREAKDOWN_GROUP", "OBS_DATE"],
        ignore_index=True,
    )
    return df_s_long_db


if __name__ == "__main__":
    pass
