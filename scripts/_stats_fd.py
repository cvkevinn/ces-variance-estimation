import pandas as pd
import numpy as np
from scipy.stats import norm


def reshape_wide_t1_t2(df, breakdown_vars, value_col, lag):
    df_wide = df.pivot(
        index=breakdown_vars, columns="variable", values=value_col
    ).reset_index()
    df_wide.columns.name = None
    df_wide.columns = df_wide.columns.get_level_values(0)
    # Create two dataframes representing t+1 and t+2
    df_t1 = df_wide.copy()
    # df_t1["wave"] = df_t1["wave"] + 1
    df_t1["wave"] = df_t1["wave"] + lag
    df_t2 = df_wide.copy()
    df_merged = df_t1.merge(
        df_t2, on=breakdown_vars, how="inner", suffixes=("_t1", "_t2")
    )
    return df_merged


def reshape_long_t2(df_wide, breakdown_vars, value_name):
    df_long = pd.melt(
        df_wide, id_vars=breakdown_vars, var_name="variable", value_name=value_name
    )
    # Sorting output
    sort_vars = breakdown_vars.copy()  # [ ] I can use this! also for df_output
    sort_vars.append("variable")
    df_long.sort_values(by=sort_vars[::-1], ignore_index=True, inplace=True)
    return df_long


def calculate_sd_first_diff(df_t1, df_t2, correlation):
    return np.round(np.sqrt(df_t1**2 + df_t2**2 - 2 * correlation * df_t1 * df_t2), 4)


def calculate_estim_first_diff(df_t1, df_t2):
    return np.round(df_t2 - df_t1, 4)


def apply_calculation_diff(df, breakdown_vars, calc_function, **kwargs):
    break_cols = df[breakdown_vars]
    df_t1 = df.filter(regex="_t1$")
    df_t2 = df.filter(regex="_t2$")
    df_t2.columns = (
        df_t1.columns
    )  # Making sure column names match so that we can perfrom element-wise operation
    result = calc_function(df_t1, df_t2, **kwargs)
    result_final = pd.concat([break_cols, result], axis=1)
    result_final.columns = [
        col_name.replace("_t1", "") if col_name.endswith("_t1") else col_name
        for col_name in result_final.columns
    ]
    return result_final


def main_calculate_stats_fd(
    df: pd.DataFrame, breakdown_vars: list[str], correlation: float, lag: int
):
    df_wide_estim = reshape_wide_t1_t2(df, breakdown_vars, "value", lag)
    df_calculation_estim = apply_calculation_diff(
        df_wide_estim, breakdown_vars, calculate_estim_first_diff
    )
    df_long_estim = reshape_long_t2(df_calculation_estim, breakdown_vars, "fd_value")

    df_wide_sd = reshape_wide_t1_t2(df, breakdown_vars, "sd", lag)
    df_calculation_sd = apply_calculation_diff(
        df_wide_sd, breakdown_vars, calculate_sd_first_diff, correlation=correlation
    )
    df_long_sd = reshape_long_t2(df_calculation_sd, breakdown_vars, "fd_sd")

    df_main_stats = pd.merge(
        df_long_estim, df_long_sd, on=breakdown_vars + ["variable"], how="inner"
    )
    return df_main_stats


def main_calculate_other_stats(df_main_stats: pd.DataFrame):
    estim_fd = np.array(df_main_stats["fd_value"])
    sd_fd = np.array(df_main_stats["fd_sd"])
    # p_value_g = np.round((2 * norm.cdf(abs(estim_diff / sd_diff)) - 1), 4)
    p_value = np.round(2 * (1 - norm.cdf(abs(estim_fd / sd_fd))), 4)

    lower_bound = np.round(estim_fd - 1.96 * sd_fd, 4)
    upper_bound = np.round(estim_fd + 1.96 * sd_fd, 4)

    df_other_stats = pd.DataFrame(
        {
            "fd_lb_95": lower_bound,
            "fd_up_95": upper_bound,
            # "p_value_g": p_value_g,
            "fd_p_value": p_value,
        }
    )

    df_output_fd = pd.concat(
        [
            df_main_stats,
            df_other_stats,
        ],
        axis=1,
    )
    return df_output_fd


if __name__ == "__main__":
    pass
