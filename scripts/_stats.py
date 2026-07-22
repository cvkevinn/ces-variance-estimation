import pandas as pd
import numpy as np


def calculate_breakdown_aggregates(df, df_estimates, breakdown_vars):
    df["breakdown_flag"] = df[breakdown_vars].astype(str).agg("_".join, axis=1)
    # Group by breakdown_flag to get both sample size and population size
    df_agg = (
        df.groupby("breakdown_flag")
        .agg(sample_size=("wgt_bld", "size"), population_size=("wgt_bld", "sum"))
        .reset_index()
    )
    df_agg = pd.merge(df_estimates, df_agg, on="breakdown_flag")
    df_agg = pd.merge(
        df[breakdown_vars + ["breakdown_flag"]].drop_duplicates(),
        df_agg,
        on="breakdown_flag",
    )
    return df_agg


def calculate_statistics(df_agg, rep):
    estimates = df_agg.filter(regex=r"^theta_")
    estimates_subset = estimates.iloc[:, :rep]

    std = estimates_subset.std(axis=1)
    margin = 1.96 * np.sqrt((rep - 1) / rep) * std
    # value_estimate = np.round(df_results["estim"], 2)
    value_estimate = df_agg["value"]
    lower_bound = np.round(value_estimate - margin, 4)
    upper_bound = np.round(value_estimate + margin, 4)
    std = np.round(std, 4)
    # Creating Statistics df
    df_statistics = pd.DataFrame(
        {
            "sd": std,
            # "margin": margin,
            "lb_95": lower_bound,
            "ub_95": upper_bound,
        }
    )

    # df_agg["value"] = df_agg["value"].round(1)

    results_final = pd.concat([df_agg, df_statistics], axis=1)
    return results_final


def main_calculate_stats(df, df_estimates, breakdown_vars, rep):
    df_agg = calculate_breakdown_aggregates(df, df_estimates, breakdown_vars)
    df_final = calculate_statistics(df_agg, rep)
    output_final = df_final[
        breakdown_vars
        + [
            "breakdown_flag",
            "variable",
            "value",
            "sd",
            "lb_95",
            "ub_95",
            "sample_size",
            "population_size",
        ]
    ]
    return output_final


if __name__ == "__main__":
    pass
