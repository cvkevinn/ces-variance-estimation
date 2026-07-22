import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def calculate_adjustment_factors(df_weights: pd.DataFrame, rep: int) -> pd.DataFrame:
    df_weights_red = df_weights.drop(
        columns=["a0010", "pr2010", "sample", "wgt_calib", "n", "ns"]
    )

    sum_df = df_weights_red.groupby(["a0020", "wave"], as_index=False).sum()
    weight_columns = df_weights.filter(regex=r"^bwgt_bld_\d+$")
    df_factor = sum_df.copy()
    df_factor[weight_columns.columns] = 1 / sum_df[weight_columns.columns].div(
        sum_df["wgt_bld"], axis=0
    )

    rename_dict = {f"bwgt_bld_{i}": f"adj_factor_{i}" for i in range(1, rep + 1)}
    df_factor = df_factor.rename(columns=rename_dict)
    return df_factor


def calculate_adjusted_weights(
    df_weights: pd.DataFrame, df_factors: pd.DataFrame
) -> pd.DataFrame:

    df_all = pd.merge(df_weights, df_factors, on=["a0020", "wave"], how="inner")

    weight_columns = df_all.filter(regex=r"^bwgt_bld_\d+$")
    factor_columns = df_all.filter(regex=r"^adj_factor_\d+$")

    adjusted_weights = weight_columns.mul(factor_columns.values)

    result = df_all[
        ["a0010", "a0020", "wave", "pr2010", "sample", "n", "ns", "wgt_bld_x"]
    ].join(adjusted_weights)
    result.rename(columns={"wgt_bld_x": "wgt_bld"}, inplace=True)
    return result


def main_adjusted_weights(df_weights: pd.DataFrame, rep: int) -> pd.DataFrame:
    logger.info(f"Applying correction: Bootstrap adjusted blended weights.")
    df_factors = calculate_adjustment_factors(df_weights, rep)
    result = calculate_adjusted_weights(df_weights, df_factors)
    return result


if __name__ == "__main__":
    pass
