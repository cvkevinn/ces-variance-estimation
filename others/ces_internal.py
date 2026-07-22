import pandas as pd
import numpy as np
from others._tools_others import dfs_long_to_dfe_wide, download_table
from others._tools_others import MAPPING_BREAKDOWN_AGE_VALUES

# df = download_table("prj_ces_production", "aggregates_final_complete", "all")


def main_ces_internal_shape(df: pd.DataFrame) -> pd.DataFrame:

    # ROUNDING
    df["population_size"] = df["population_size"].round(0)
    df["sample_size"] = df["sample_size"].round(0)
    df["value"] = df["value"].round(1)

    # RESHAPING TO DG-E WIDE FORMAT
    df_s_final = dfs_long_to_dfe_wide(df)

    # Small checks
    df_s_final = df_s_final.replace("__missing__", "")

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

    # 3) DELETING NOT INCLUDED COLUMNS
    df_s_final.drop(
        columns=["date", "Expectations_p25", "Expectations_p75"], axis=1, inplace=True
    )

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
    return df_s_final


if __name__ == "__main__":
    pass
