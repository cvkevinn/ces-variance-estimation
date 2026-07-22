import logging
import pandas as pd
import numpy as np
from scripts._tools import (
    weighted_mean,
    weighted_quantile_midpoint_linear,
    weighted_quantile_inverse_cdf,
)
from scripts._winsor import calculate_winsorized_variable

logger = logging.getLogger(__name__)


def bootstrap_replicates(df: pd.DataFrame, rep: int, seed_number: int) -> pd.DataFrame:
    """
    STEP 1
    Generate bootstrap replicates of a given DataFrame by resampling with replacement.

    This function performs bootstrap resampling for each unique combination of
    country, sample type (PS or NPS), and wave, as determined by the "sample" column
    in the input DataFrame. For each combination, the function generates a specified
    number of replicate datasets.
    """
    list_codes = df["sample"].drop_duplicates().tolist()
    np.random.seed(seed_number)  # Set seed for reproducibility
    result_list = list()

    for code in list_codes:
        tmp = df[df["sample"] == code][
            [
                "a0010",
                "a0020",
                "wave",
                "pr2010",
                "sample",
                "wgt_calib",
                "wgt_bld",
                "n",
                "ns",
            ]
        ]

        ssize = len(tmp)
        listid = np.arange(1, ssize + 1)
        table = np.full((ssize, rep), np.nan)
        tmp.reset_index(drop=True, inplace=True)

        # Bootstrap replicates loop
        for k in range(rep):
            x = np.random.choice(listid, size=ssize, replace=True)
            counts = np.bincount(x, minlength=ssize + 1)[1:]  # Ignore 0th index
            table[:, k] = counts

        table_df = pd.DataFrame(table, columns=[f"m_{i+1}" for i in range(rep)])
        combined = pd.concat([tmp, table_df], axis=1)
        result_list.append(combined)

    result_df = pd.concat(result_list, ignore_index=True)
    return result_df


def bootstrap_weights(df_replicates: pd.DataFrame, rep: int) -> pd.DataFrame:
    """
    STEP 2
    Adjust individual sampling weights based on bootstrap replicates.

    This function modifies the sampling weights for each individual in the dataset
    by accounting for their multiplicity in each bootstrap replicate.
    """
    bwgts_list = list()
    d = df_replicates["wgt_calib"]
    ns = df_replicates["ns"]
    factor = d * ns / (ns - 1)

    for k in range(1, rep + 1):
        # logger.info(f"Bootstrap weight: replicate {k}")
        m = df_replicates.iloc[:, k + 8]
        bwgt = factor * m
        bwgts_list.append(bwgt.rename(f"bwgt_{k}"))
    bwgts_df = pd.concat(bwgts_list, axis=1)
    result_df = pd.concat([df_replicates.iloc[:, 0:9], bwgts_df], axis=1)

    return result_df


def bootstrap_weights_blended(df_bweights: pd.DataFrame, rep: int) -> pd.DataFrame:
    """
    STEP 3
    Compute blended bootstrap weights for each replicate.

    This function calculates the blended bootstrap weights for each individual in
    the dataset by combining the adjusted weights from step 2.
    """
    bwgts_bld_list = list()
    blending_factor = df_bweights["ns"] / df_bweights["n"]

    for k in range(1, rep + 1):
        logger.info(f"Bootstrap blended weight: replicate {k}")
        bwgt = df_bweights.iloc[:, k + 8]
        bwgt_bld = bwgt * blending_factor
        bwgts_bld_list.append(bwgt_bld.rename(f"bwgt_bld_{k}"))

    bwgts_bld_df = pd.concat(bwgts_bld_list, axis=1)
    result_df = pd.concat([df_bweights.iloc[:, 0:9], bwgts_bld_df], axis=1)

    return result_df


def bootstrap_mean_estimates(df, varlist, breakdown_flag, rep):
    """
    STEP 4 (part 1) - For quali variables.

    Calculate bootstrap mean estimates for specified variables AND specified
    breakdown!

    This function performs step 4 of the analysis. It computes the estimated value
    for each replicate using the bootstrap weights from step 3. The bootstrap
    variance estimate (STEP 4 (part 2)) is determined by the dispersion of these
    estimates. The variance per se, hence, part 2, is calculated in function
    _stats.main_calculate_stats).
    """
    all_var_results_list = list()

    for var in varlist:
        wgt = df["wgt_bld"].values
        studyvar = df[var].values
        group_vals = df[breakdown_flag].values

        unique_groups = np.unique(group_vals)
        var_results = list()

        for group_value in unique_groups:
            mask = group_vals == group_value
            _weights = wgt[mask]
            _values = studyvar[mask]

            # Calculate official mean estimates / aggregates (using blended weights)
            value = weighted_mean(_values, _weights)
            # disp = weighted_var(_values, _weights)

            row = {
                breakdown_flag: group_value,
                "value": value,
                "variable": f"{var}_mean",
            }
            var_results.append(row)

        var_results = pd.DataFrame(var_results)

        # Calculate bootstrap mean estimates
        for k in range(1, rep + 1):
            logger.info(f"Calculating '{var}' mean replicate {k}")
            wgt_bootstrap = df[f"bwgt_bld_{k}"].values
            replicate_results = list()

            for group_value in unique_groups:
                mask = group_vals == group_value
                _weights = wgt_bootstrap[mask]
                _values = studyvar[mask]
                replicate_mean = weighted_mean(_values, _weights)
                replicate_results.append(
                    {breakdown_flag: group_value, f"theta_{k}": replicate_mean}
                )

            replicate_results = pd.DataFrame(replicate_results)
            var_results = var_results.merge(
                replicate_results, on=breakdown_flag, how="left"
            )

        all_var_results_list.append(var_results)

    return pd.concat(all_var_results_list, ignore_index=True)


def bootstrap_mean_estimates_no_winsorized(df, varlist, breakdown_flag, rep):
    """
    STEP 4 (part 1) - For quant variables.

    Calculate bootstrap mean estimates for specified variables AND specified
    breakdown!

    This function performs step 4 of the analysis. It computes the estimated value
    for each replicate using the bootstrap weights from step 3. The bootstrap
    variance estimate (STEP 4 (part 2)) is determined by the dispersion of these
    estimates. The variance per se, hence, part 2, is calculated in function
    _stats.main_calculate_stats).
    """
    all_var_results_list = list()

    for var in varlist:
        # df = calculate_winsorized_variable(df, var, "wgt_bld")
        wgt = df["wgt_bld"].values
        studyvar = df[var].values
        # studyvar = df[f"{var}_w"].values
        group_vals = df[breakdown_flag].values

        unique_groups = np.unique(group_vals)
        var_results = list()

        for group_value in unique_groups:
            mask = group_vals == group_value
            _weights = wgt[mask]
            _values = studyvar[mask]

            # Calculate official mean estimates / aggregates (using blended weights)
            value = weighted_mean(_values, _weights)
            # disp = weighted_var(_values, _weights)

            row = {
                breakdown_flag: group_value,
                "value": value,
                "variable": f"{var}_mean",
            }
            var_results.append(row)

        var_results = pd.DataFrame(var_results)

        # Calculate bootstrap mean estimates
        for k in range(1, rep + 1):
            logger.info(
                f"Calculating '{var}' mean replicate {k} without winsorization."
            )
            wgt_bootstrap = df[f"bwgt_bld_{k}"].values
            replicate_results = list()

            for group_value in unique_groups:
                mask = group_vals == group_value
                _weights = wgt_bootstrap[mask]
                _values = studyvar[mask]
                replicate_mean = weighted_mean(_values, _weights)
                replicate_results.append(
                    {breakdown_flag: group_value, f"theta_{k}": replicate_mean}
                )

            replicate_results = pd.DataFrame(replicate_results)
            var_results = var_results.merge(
                replicate_results, on=breakdown_flag, how="left"
            )

        all_var_results_list.append(var_results)

    return pd.concat(all_var_results_list, ignore_index=True)


# def bootstrap_mean_estimates_winsorized_once(df, varlist, breakdown_flag, rep):
#     """
#     STEP 4 (part 1)
#     Calculate bootstrap mean estimates for specified variables AND specified
#     breakdown!

#     This function performs step 4 of the analysis. It computes the estimated value
#     for each replicate using the bootstrap weights from step 3. The bootstrap
#     variance estimate (STEP 4 (part 2)) is determined by the dispersion of these
#     estimates. The variance per se, hence, part 2 is calculated in function
#     _stats.main_calculate_stats).
#     """
#     all_var_results_list = list()

#     for var in varlist:
#         df = calculate_winsorized_variable(df, var, "wgt_bld")
#         wgt = df["wgt_bld"].values
#         studyvar = df[f"{var}_w"].values
#         group_vals = df[breakdown_flag].values

#         unique_groups = np.unique(group_vals)
#         var_results = list()

#         for group_value in unique_groups:
#             mask = group_vals == group_value
#             _weights = wgt[mask]
#             _values = studyvar[mask]

#             # Calculate official mean estimates / aggregates (using blended weights)
#             value = weighted_mean(_values, _weights)
#             # disp = weighted_var(_values, _weights)

#             row = {
#                 breakdown_flag: group_value,
#                 "value": value,
#                 "variable": f"{var}_mean_w",
#             }
#             var_results.append(row)

#         var_results = pd.DataFrame(var_results)

#         # Calculate bootstrap mean estimates
#         for k in range(1, rep + 1):
#             logger.info(
#                 f"Calculating '{var}_w' mean replicate {k} winsorized only once."
#             )
#             wgt_bootstrap = df[f"bwgt_bld_{k}"].values
#             replicate_results = list()

#             for group_value in unique_groups:
#                 mask = group_vals == group_value
#                 _weights = wgt_bootstrap[mask]
#                 _values = studyvar[mask]
#                 replicate_mean = weighted_mean(_values, _weights)
#                 replicate_results.append(
#                     {breakdown_flag: group_value, f"theta_{k}": replicate_mean}
#                 )

#             replicate_results = pd.DataFrame(replicate_results)
#             var_results = var_results.merge(
#                 replicate_results, on=breakdown_flag, how="left"
#             )

#         all_var_results_list.append(var_results)

#     return pd.concat(all_var_results_list, ignore_index=True)


def bootstrap_mean_estimates_winsorized(df, varlist, breakdown_flag, rep):
    """
    STEP 4 (part 1) - For quant variables.

    Calculate bootstrap winsorised mean estimates for specified variables AND
    specified breakdown!

    This function performs step 4 of the analysis. It computes the estimated value
    for each replicate using the bootstrap weights from step 3. The bootstrap
    variance estimate (STEP 4 (part 2)) is determined by the dispersion of these
    estimates. The variance per se, hence, part 2, is calculated in function
    _stats.main_calculate_stats).
    """
    all_var_results_list = list()

    for var in varlist:
        df = calculate_winsorized_variable(df, var, "wgt_bld")
        wgt = df["wgt_bld"].values
        studyvar = df[f"{var}_w"].values
        group_vals = df[breakdown_flag].values

        unique_groups = np.unique(group_vals)
        var_results = list()

        for group_value in unique_groups:
            mask = group_vals == group_value
            _weights = wgt[mask]
            _values = studyvar[mask]

            # Calculate official mean estimates / aggregates (using blended weights)
            value = weighted_mean(_values, _weights)
            # disp = weighted_var(_values, _weights)

            row = {
                breakdown_flag: group_value,
                "value": value,
                # "disp": disp,
                "variable": f"{var}_mean_w",
            }
            var_results.append(row)

        var_results = pd.DataFrame(var_results)

        # Calculate bootstrap mean estimates
        for k in range(1, rep + 1):
            logger.info(f"Calculating '{var}_w' mean replicate {k}")
            df = calculate_winsorized_variable(df, var, f"bwgt_bld_{k}")
            studyvar_k = df[f"{var}_w"].values
            wgt_bootstrap = df[f"bwgt_bld_{k}"].values
            replicate_results = list()

            for group_value in unique_groups:
                mask = group_vals == group_value
                _weights = wgt_bootstrap[mask]
                _values = studyvar_k[mask]
                replicate_mean = weighted_mean(_values, _weights)
                replicate_results.append(
                    {breakdown_flag: group_value, f"theta_{k}": replicate_mean}
                )

            replicate_results = pd.DataFrame(replicate_results)
            var_results = var_results.merge(
                replicate_results, on=breakdown_flag, how="left"
            )

        all_var_results_list.append(var_results)

    return pd.concat(all_var_results_list, ignore_index=True)


def bootstrap_median_estimates(df, varlist, breakdown_flag, rep):
    """
    STEP 4 (part 1) - For quant variables.

    Calculate bootstrap median estimates for specified variables AND specified
    breakdown!

    This function performs step 4 of the analysis. It computes the estimated value
    for each replicate using the bootstrap weights from step 3. The bootstrap
    variance estimate (STEP 4 (part 2)) is determined by the dispersion of these
    estimates. The variance per se, hence, part 2, is calculated in function
    _stats.main_calculate_stats).
    """
    all_var_results_list = list()

    for var in varlist:
        wght = df["wgt_bld"].values
        studyvar = df[var].values
        group_vals = df[breakdown_flag].values

        unique_groups = np.unique(group_vals)
        var_results = list()

        for group_value in unique_groups:
            mask = group_vals == group_value
            _weights = wght[mask]
            _values = studyvar[mask]

            # Calculate official median estimates / aggregates (using blended weights)
            # value = weighted_quantile_midpoint_linear(_values, _weights, [0.5])[0]
            value = weighted_quantile_midpoint_linear(_values, _weights)
            # disp = weighted_var(_values, _weights)

            row = {
                breakdown_flag: group_value,
                "value": value,
                # "disp": disp,
                "variable": f"{var}_median",
            }
            var_results.append(row)

        var_results = pd.DataFrame(var_results)

        # Calculate bootstrap median estimates
        for k in range(1, rep + 1):
            logger.info(f"Calculating '{var}' median replicate {k}")
            wght_bootstrap = df[f"bwgt_bld_{k}"].values
            replicate_results = list()

            for group_value in unique_groups:
                mask = group_vals == group_value
                _weights = wght_bootstrap[mask]
                _values = studyvar[mask]
                # replicate_median = weighted_quantile_midpoint_linear(
                #     _values, _weights, [0.5]
                # )[0]
                replicate_median = weighted_quantile_midpoint_linear(_values, _weights)

                replicate_results.append(
                    {breakdown_flag: group_value, f"theta_{k}": replicate_median}
                )

            replicate_results = pd.DataFrame(replicate_results)
            var_results = var_results.merge(
                replicate_results, on=breakdown_flag, how="left"
            )

        all_var_results_list.append(var_results)

    return pd.concat(all_var_results_list, ignore_index=True)


def bootstrap_quantile_estimates_new(df, varlist, breakdown_flag, rep, quantile):
    """
    STEP 4 (part 1) - For probin variables.

    Calculate bootstrap median estimates for specified variables AND specified
    breakdown!

    This function performs step 4 of the analysis. It computes the estimated value
    for each replicate using the bootstrap weights from step 3. The bootstrap
    variance estimate (STEP 4 (part 2)) is determined by the dispersion of these
    estimates. The variance per se, hence, part 2, is calculated in function
    _stats.main_calculate_stats).
    """
    all_var_results_list = list()

    for var in varlist:
        wght = df["wgt_bld"].values
        studyvar = df[var].values
        group_vals = df[breakdown_flag].values

        unique_groups = np.unique(group_vals)
        var_results = list()

        for group_value in unique_groups:
            mask = group_vals == group_value
            _weights = wght[mask]
            _values = studyvar[mask]

            # Calculate official median estimates / aggregates (using blended weights)
            value = weighted_quantile_inverse_cdf(_values, _weights, quantile)
            # disp = weighted_var(_values, _weights)

            row = {
                breakdown_flag: group_value,
                "value": value,
                # "disp": disp,
                "variable": f"{var}_quantile_{quantile}",
            }
            var_results.append(row)

        var_results = pd.DataFrame(var_results)

        # Calculate bootstrap median estimates
        for k in range(1, rep + 1):
            logger.info(f"Calculating '{var}' quantile {quantile} replicate {k}")
            wght_bootstrap = df[f"bwgt_bld_{k}"].values
            replicate_results = list()

            for group_value in unique_groups:
                mask = group_vals == group_value
                _weights = wght_bootstrap[mask]
                _values = studyvar[mask]
                replicate_quantile = weighted_quantile_inverse_cdf(_values, _weights)

                replicate_results.append(
                    {breakdown_flag: group_value, f"theta_{k}": replicate_quantile}
                )

            replicate_results = pd.DataFrame(replicate_results)
            var_results = var_results.merge(
                replicate_results, on=breakdown_flag, how="left"
            )

        all_var_results_list.append(var_results)

    return pd.concat(all_var_results_list, ignore_index=True)


def main_bootstrap_quantitative_estimates(
    df: pd.DataFrame,
    df_weights: pd.DataFrame,
    varlist: list[str],
    breakdown_vars: list[str],
    rep: int,
    winsorization: bool = False,  # If winsorization False, then it winsorised once.
):
    df_vars = df[["a0010"] + breakdown_vars + varlist]
    try:
        df_vars = df_vars.drop(columns="a0020")  # to avoid repetition
    except:
        pass

    data = pd.merge(
        df_weights,
        df_vars,
        on=["a0010", "wave"],
        how="inner",
    )
    data["breakdown_flag"] = data[breakdown_vars].astype(str).agg("_".join, axis=1)

    if winsorization:
        mean_results = bootstrap_mean_estimates_winsorized(
            data, varlist, "breakdown_flag", rep
        )
    else:
        # mean_results = bootstrap_mean_estimates_winsorized_once(
        #     data, varlist, "breakdown_flag", rep
        # )
        mean_results = bootstrap_mean_estimates_no_winsorized(
            data, varlist, "breakdown_flag", rep
        )

    median_results = bootstrap_median_estimates(data, varlist, "breakdown_flag", rep)

    final_results = pd.concat([mean_results, median_results], ignore_index=True)
    final_results.sort_values(
        by=["variable", "breakdown_flag"], ignore_index=True, inplace=True
    )
    return final_results


def main_bootstrap_prob_bin_estimates(
    df: pd.DataFrame,
    df_weights: pd.DataFrame,
    varlist: list[str],
    breakdown_vars: list[str],
    rep: int,
    # winsorization: bool = False,  # If winsorization False, then it winsorised once.
):
    df_vars = df[["a0010"] + breakdown_vars + varlist]
    try:
        df_vars = df_vars.drop(columns="a0020")  # to avoid repetition
    except:
        pass
    # maybe this one must be slightly modified in this case
    data = pd.merge(
        df_weights,
        df_vars,
        on=["a0010", "wave"],
        how="inner",
    )
    data["breakdown_flag"] = data[breakdown_vars].astype(str).agg("_".join, axis=1)
    median_results = bootstrap_quantile_estimates_new(
        data, varlist, "breakdown_flag", rep, 0.5
    )

    q1_results = bootstrap_quantile_estimates_new(
        data, varlist, "breakdown_flag", rep, 0.25
    )
    q3_results = bootstrap_quantile_estimates_new(
        data, varlist, "breakdown_flag", rep, 0.75
    )

    final_results = pd.concat(
        [median_results, q1_results, q3_results], ignore_index=True
    )

    # the part below should be changed depending on what is median_results
    final_results.sort_values(
        by=["variable", "breakdown_flag"], ignore_index=True, inplace=True
    )
    return final_results


def main_bootstrap_qualitative_estimates(
    df: pd.DataFrame,
    df_weights: pd.DataFrame,
    varlist: list[str],
    breakdown_vars: list[str],
    rep: int,
    winsorization: bool,
):
    df_vars = df[["a0010"] + breakdown_vars + varlist]
    try:
        df_vars = df_vars.drop(columns="a0020")  # to avoid repetition
    except:
        pass

    data = pd.merge(
        df_weights,
        df_vars,
        on=["a0010", "wave"],
        how="inner",
    )
    data["breakdown_flag"] = data[breakdown_vars].astype(str).agg("_".join, axis=1)

    mean_results = bootstrap_mean_estimates(data, varlist, "breakdown_flag", rep)
    mean_results.sort_values(
        by=["variable", "breakdown_flag"], ignore_index=True, inplace=True
    )
    return mean_results


if __name__ == "__main__":
    pass
