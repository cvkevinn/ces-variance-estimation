import pandas as pd
import numpy as np
from others._tools_others import (
    compare_dataframes,
    download_table,
    dfs_long_to_dfe_wide,
    main_comparing_long_format,
    dfe_wide_to_dfs_long,
    MAPPING_BREAKDOWN_AGE_VALUES,
)
from settings import DISSEMINATION_ARCHIVE_DIR

# df = download_table("prj_ces_production", "aggregates_final_complete", "all")


def main_ces_website_shape(df: pd.DataFrame) -> pd.DataFrame:

    # ROUNDING
    df["population_size"] = df["population_size"].round(0)
    df["sample_size"] = df["sample_size"].round(0)
    df["value"] = df["value"].round(1)

    # RESHAPING TO DG-E WIDE FORMAT
    df_s_final = dfs_long_to_dfe_wide(df)

    # Small checks
    df_s_final = df_s_final.replace("__missing__", "")
    df_s_final["N_Weighted"] = df_s_final["N_Weighted"].round(0)
    df_s_final["N"] = df_s_final["N"].round(0)

    # 1) AGE VALUES AS IN DG-E
    reverse_mapping_breakdown_age = {
        v: k for k, v in MAPPING_BREAKDOWN_AGE_VALUES.items()
    }
    df_s_final["Breakdown_label"] = np.where(
        df_s_final["Breakdown"] == "Age",
        df_s_final["Breakdown_label"].map(reverse_mapping_breakdown_age),
        df_s_final["Breakdown_label"],
    )

    # 2) DELETING NOT INCLUDED AGGREGATES
    ## 2.1 Oldest group
    df_s_final = df_s_final[df_s_final["Breakdown_label"] != "70+ years"]

    ## 2.2 Delete aggregates with sample size <20
    df_s_final = df_s_final[~(df_s_final["N"] < 20)]

    # 3) Sorting before exporting
    df_s_final.sort_values(
        by=[
            "Var",
            "Breakdown",
            "Breakdown_label",
            "wave",
        ],
        ignore_index=True,
        inplace=True,
    )
    # 4) DELETING NOT INCLUDED COLUMNS
    df_s_final.drop(
        columns=["wave", "Topic", "Expectations_p25", "Expectations_p75"],
        axis=1,
        inplace=True,
    )
    df_s_final.rename(columns={"date": "wave"}, inplace=True)

    return df_s_final


if __name__ == "__main__":

    ########################### ANALYSING DIFFERENCES IN QUARTERLY VARIABLES

    # df_s_original = download_table("prj_ces_production", "aggregates_all", "all")

    # df_s_q_2 = download_table(
    #     "prj_ces_production", "aggregates_all_quarterly_core_wgtbld_q", "all"
    # )

    # # TREATING IDK ANSWERS AS PART OF SAMPLE SIZE
    # df_s_q_main = download_table(
    #     "prj_ces_production", "aggregates_all_quarterly_quarterly_wgtbld_q", "all"
    # )
    # # TREATING IDK ANSWERS AS NAN, HENCE NOT PART OF SAMPLE SIZE
    # df_s_q_main2 = download_table(
    #     "prj_ces_production", "aggregates_all_quarterly_quarterly_wgtbld_q2", "all"
    # )

    # df_s = download_table("prj_ces_production", "aggregates_final_complete", "all")
    # Ad-hoc revision checks read local CSV exports of the quarterly aggregates.

    # df_e = pd.read_csv(PATH_DFE)
    df_s = download_table("prj_ces_production", "aggregates_final_ea6", "all")
    df_s1 = df_s[
        ~((df_s["breakdown_other"] == "age") & (df_s["breakdown_other_categ"] == 4))
    ]
    df_s1["value"] = df_s1["value"].round(1)
    df_s2 = df_s1[~(df_s1["sample_size"] < 20)]
    df_s3 = df_s2[
        df_s2["indicator"].isin(
            ["mean_w", "median", "share", "expectations_med", "uncertainty_med"]
        )
    ]
    df_s4 = df_s3[
        ~((df_s3["variable"].isin(["q2300", "q2350", "q2390"])) & (df_s3["wave"] < 13))
    ]
    df_s5 = df_s4[df_s4["qualitative_measure"] != "no"]
    df_s5_compare = dfs_long_to_dfe_wide(df_s5)

    PATH_DFE2 = DISSEMINATION_ARCHIVE_DIR / "Aggregate_indicators_CES_ea6.csv"
    df_ea6 = pd.read_csv(PATH_DFE2)
    df_ea6_compared = dfe_wide_to_dfs_long(df_ea6)

    # df_ea6_c = dfe_wide_to_dfs_long(df_ea6)
    # id_cols = [
    #     "wave",
    #     "country",
    #     "breakdown_other",
    #     "breakdown_other_categ",
    #     "variable",
    #     "qualitative_measure",
    #     "indicator",
    # ]

    # matches_df, mismatches_df = compare_dataframes(df_s, df_ea6_c, id_cols, "value")

    matches_df, mismatches_df, unmatched_df1, unmatched_df2 = (
        main_comparing_long_format(df_s5, df_ea6, "value")
    )

    # df_e = pd.read_csv(PATH_DFE_OLD)

    # ## MORE CHECKS
    # matches_v0, mismatches_v0 = main_comparing_long_format(
    #     df_s_test3, df_ea6, "sample_size"
    # )
    # id_cols = [
    #     "wave",
    #     "country",
    #     "breakdown_other",
    #     "breakdown_other_categ",
    #     "variable",
    #     "qualitative_measure",
    #     "indicator",
    # ]
    # matches, mismatches = compare_dataframes(
    #     df_s_test3, df_s_test2, id_cols, "sample_size"
    # )

    # # mismatches_v0_ = mismatches_v0[mismatches_v0["variable"].isin(["q2300","q2350", "q2390"])]

    # matches_v1, mismatches_v1 = main_comparing_long_format(df_s_q_1, df_e, "value")
    # matches_v2, mismatches_v2 = main_comparing_long_format(df_s_q_2, df_e, "value")
    # matches_v3, mismatches_v3 = main_comparing_long_format(df_s_q_main, df_e, "value")
    # matches_v4, mismatches_v4 = main_comparing_long_format(df_s_q_main2, df_e, "value")

    # matches_ssize1, mismatches_ssize1 = main_comparing_long_format(
    #     df_s_q_1, df_e, "population_size"
    # )
    # matches_ssize2, mismatches_ssize2 = main_comparing_long_format(
    #     df_s_q_2, df_e, "population_size"
    # )
    # matches_ssize3, mismatches_ssize3 = main_comparing_long_format(
    #     df_s_q_main, df_e, "population_size"
    # )
    # matches_ssize4, mismatches_ssize4 = main_comparing_long_format(
    #     df_s_q_main2, df_e, "population_size"
    # )
    # # Wide format: you can compare columns "Mean", "Median", "Up", "Down", etc
    # mistmaches_df2 = main_comparing_wide_format(df_s, df_e, "Mean")


# for var in df_s4["variable"].unique():
#     subset_df = df_s4[df_s4["variable"]==var]
#     min_wave = subset_df["wave"].min()
#     max_wave = subset_df["wave"].max()
#     print(f"{var}, min wave:{min_wave}, max wave:{max_wave}")


# for col in df_ea6_compared.columns:
#     x = len(df_ea6_compared[col].unique())
#     print(f"{col} has {x} unique values")

# for col in df_s4.columns:
#     x = len(df_s4[col].unique())
#     print(f"{col} has {x} unique values")
