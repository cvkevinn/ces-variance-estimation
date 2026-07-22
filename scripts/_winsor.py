import pandas as pd
import numpy as np


def weighted_percentile(df, data_col, weight_col, percentile):
    """
    This function calculates the weighted percentile of the values in `data_col`,
    using the weights specified in `weight_col`. The DataFrame is sorted by the
    values in `data_col`, and the cumulative weights are used to determine the
    percentile value.

    Args:
        df : pandas.DataFrame
            The DataFrame containing the data and weight columns.
        data_col : str
            The name of the column containing the data values for which the percentile
            is to be computed.
        weight_col : str
            The name of the column containing the weights associated with the data values.
        percentile : float
            The desired percentile (between 0 and 100) to compute.

    Returns:
        value: float
            The value at the specified weighted percentile.
    """
    if data_col not in df.columns or weight_col not in df.columns:
        raise ValueError(
            "The DataFrame must contain the specified 'data_col' and 'weight_col'."
        )

    # Check for non-negative weights
    if df[weight_col].min() < 0:
        raise ValueError("Weights must be non-negative.")
   
    # Drop missing or outlier values
    df_clean = df.dropna(subset=[data_col])
    df_clean = df_clean[df_clean[data_col] >= -500]
 
    if df_clean.empty:
        return np.nan  # No data left to compute
 
    # Sort the DataFrame by the data column
    df_sorted = df_clean.sort_values(by=data_col)
    sorted_data = df_sorted[data_col]
    sorted_weights = df_sorted[weight_col]
 
    # Compute the cumulative sum of weights and normalize
    cum_weights = sorted_weights.cumsum()
    cum_weights /= cum_weights.iloc[-1]
    cum_weights *= 100
 
    # Find the index where the cumulative weight equals or exceeds the percentile
    idx = np.searchsorted(cum_weights, percentile, side="right")
    return sorted_data.iloc[idx]


def percentile_cutoffs(df, data_col, weight_col):
    percentiles = dict()
    for p in [2, 98]:
        percentiles[p] = weighted_percentile(df, data_col, weight_col, p)
    return percentiles


def calculate_winsorized_series(df, data_col, cutoffs):
    """
    This function performs top and bottom coding on the specified column (`data_col`).
    Values below the 2nd percentile are replaced with the 2nd percentile value,
    and values above the 98th percentile are replaced with the 98th percentile value.

    Args:
        df: pandas.DataFrame
            The input DataFrame containing the data.
        data_col: str
            The column name on which to perform winsorization.
        cutoffs: dict
            A dictionary containing the cutoffs for bottom and top coding,
            with keys 2 and 98 representing the 2nd and 98th percentiles.

    Returns:
        pandas.DataFrame
            The DataFrame with a new column containing the winsorized data.
    """
    # Extract cutoff values for the 2nd and 98th percentiles
    percentile_2 = cutoffs[2]
    percentile_98 = cutoffs[98]

    # Winsorization function that combines both top and bottom coding
    def winsorize(value):
        if np.isnan(value):
            return value
        if value < percentile_2:
            return percentile_2
        if value > percentile_98:
            return percentile_98
        return value

    # Create a new column with "_w" appended to the original column name
    df[f"{data_col}_w"] = df[data_col].apply(winsorize)

    return df


def calculate_winsorized_variable(
    df: pd.DataFrame,
    var_name: str,
    weight_col: str,
) -> pd.DataFrame:

    results = list()
    grouped = df.groupby(["a0020", "wave"])
    for name, group in grouped:
        p_cutoffs = percentile_cutoffs(group, var_name, weight_col)
        group = calculate_winsorized_series(group, var_name, p_cutoffs)
        results.append(group)
    df = pd.concat(results, ignore_index=True)
    # df.sort_values(by=["a0020", "a0010", "wave"], ignore_index=True, inplace=True)
    return df
