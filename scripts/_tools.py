import logging
import pandas as pd
import numpy as np
from connectors import devo
from typing import Iterable, Sequence
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

from settings import table_storage_path

logger = logging.getLogger(__name__)


CORE_COLS = [
    "a0010",
    "a0020",
    "wave",
    "a1110_calib_rec",
    "b7040_imp_quintiles",
    "pr2010",
    "wgt_calib",
    "wgt_bld",
]


def _normalize_cols(
    varlist: str | Iterable[str] | None, core_cols: Sequence[str]
) -> list[str]:
    if varlist is None:
        requested = set()
    elif isinstance(varlist, str):
        requested = {varlist}
    else:
        requested = set(varlist)
    return sorted(set(core_cols) | requested)


def _build_where_clause(
    wave: int | None = None, waves: Sequence[int] | None = None
) -> str:
    if waves:
        ints = ",".join(str(int(w)) for w in waves)
        return f" WHERE wave IN ({ints})"
    if wave is not None:
        return f" WHERE wave = {int(wave)}"
    return ""


def download_table_generic(
    table_fqdn: str,
    varlist: str | list[str] | None,
    *,
    wave: int | None = None,
    waves: Sequence[int] | None = None,
    core_cols: Sequence[str] = CORE_COLS,
) -> pd.DataFrame:
    """
    Download one dataframe with (core_cols and varlist), optionally for one wave or a list of waves.
    Exactly one of wave or waves may be provided (or neither to fetch all).
    """
    if wave is not None and waves is not None:
        raise ValueError("Provide either 'wave' or 'waves', not both.")

    cols = _normalize_cols(varlist, core_cols)
    query_vars = ", ".join(cols)
    where = _build_where_clause(wave=wave, waves=waves)

    logger.info(f"Downloading TABLE: '{table_fqdn}' {where or ''}")
    query = f"SELECT {query_vars} FROM {table_fqdn}{where}"
    df = devo.read_sql(query)
    devo.close()
    return df


def download_table_fixed(
    varlist: str | list[str] | None,
    wave: int | None = None,
    waves: list[int] | None = None,
    core_cols: list[str] = CORE_COLS,
) -> pd.DataFrame:
    return download_table_generic(
        "lab_prj_ces_production.core_super_view_agg",
        varlist,
        wave=wave,
        waves=waves,
        core_cols=core_cols,
    )


def download_table_fixed_q(
    varlist: str | list[str] | None,
    wave: int | None = None,
    waves: list[int] | None = None,
    core_cols: list[str] = CORE_COLS,
) -> pd.DataFrame:
    return download_table_generic(
        "lab_prj_ces_production.quarterly_super_view_agg",
        varlist,
        wave=wave,
        waves=waves,
        core_cols=core_cols,
    )


def download_table(
    lab_name: str,
    table_name: str,
    varlist: str | list[str],
    wave: int | None = None,
) -> pd.DataFrame:

    # Handling the varlist
    if isinstance(varlist, str):
        if varlist != "all":
            raise ValueError("If varlist is string, the only input possible is 'all'.")
        query_vars = "*"
    else:
        query_vars = ", ".join(varlist)

    logger.info(
        f"Downloading TABLE: '{table_name}' from LAB 'lab_{lab_name}'. VARIABLES: {query_vars}."
    )

    base_query = f"SELECT {query_vars} FROM lab_{lab_name}.{table_name}"

    if wave is not None:
        query = f"{base_query} WHERE wave = {wave}"
    else:
        query = base_query

    df = devo.read_sql(query)
    return df


def upload_table(df: pd.DataFrame, datalab: str, table_name: str):

    s3_path = table_storage_path(datalab, table_name)
    logger.info(f"Uploading table '{table_name}' to DEVO 'lab_{datalab}'")

    devo.create_table(
        df,
        lab=f"lab_{datalab}",
        table_name=f"{table_name}",
        path=f"{s3_path}",
        external=True,
    )
    # Closing to prevent timeout
    devo.close()
    logging.info("Upload successful")


def weighted_mean(x, w):
    mask = ~np.isnan(x) & ~np.isnan(w)
    return np.sum(x[mask] * w[mask]) / np.sum(w[mask])


def weighted_var(x, w):
    mask = ~np.isnan(x) & ~np.isnan(w)
    mean = weighted_mean(x[mask], w[mask])
    var = np.sum(w[mask] * (x[mask] - mean) ** 2) / np.sum(w[mask])
    return var


def weighted_quantile_midpoint_linear(values, weights, quantile=0.5):
    """
    Compute a single weighted quantile using the midpoint-CDF + linear interpolation.
    Logic matches the original version; only aggregation is vectorized.
    """
    if not (0.0 <= quantile <= 1.0):
        raise ValueError("quantile must be between 0 and 1")

    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)

    # drop NaNs in values (and corresponding weights)
    mask = ~np.isnan(values)
    values = values[mask]
    weights = weights[mask]

    if values.size == 0:
        return np.nan

    # sort by values
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]

    # aggregate weights for repeated values
    unique_values, indices = np.unique(values, return_inverse=True)
    aggregated_weights = np.zeros_like(unique_values, dtype=float)
    np.add.at(aggregated_weights, indices, weights)

    # weighted cumulative sum
    weighted_cumsum = np.cumsum(aggregated_weights)
    total_w = weighted_cumsum[-1]

    cumulative_distribution = weighted_cumsum / total_w
    prob_x = aggregated_weights / total_w
    final_cumulative_distribution = cumulative_distribution - 0.5 * prob_x

    # same interval search as your original code
    def custom_interp(q):
        if q <= final_cumulative_distribution[0]:
            return unique_values[0]
        elif q >= final_cumulative_distribution[-1]:
            return unique_values[-1]

        for i in range(1, len(unique_values)):
            if (
                final_cumulative_distribution[i - 1]
                <= q
                <= final_cumulative_distribution[i]
            ):
                x1, x2 = unique_values[i - 1], unique_values[i]
                G_x1 = final_cumulative_distribution[i - 1]
                G_x2 = final_cumulative_distribution[i]
                return x1 + (x2 - x1) * (q - G_x1) / (G_x2 - G_x1)

        return unique_values[-1]

    return float(custom_interp(quantile))


def weighted_quantile_inverse_cdf(values, weights, quantile=0.5):
    if not (0.0 <= quantile <= 1.0):
        raise ValueError("Quantile value must be between 0 and 1")

    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)

    # drop NaNs
    mask = ~np.isnan(values)
    values = values[mask]
    weights = weights[mask]

    if values.size == 0:
        return np.nan

    # sort
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]

    # cumweights
    cumw = np.cumsum(weights)
    total_w = cumw[-1]

    target = total_w * quantile
    idx = np.searchsorted(cumw, target, side="left")

    if idx >= len(values):
        idx = len(values) - 1
    return float(values[idx])


def wave_to_date(wave: int):
    """
    Converts a wave number to a string in the format "MM/YYYY".

    Parameters:
        wave (int): The wave number (e.g., 1 corresponds to "01/2020", 2 to "02/2020").
    """
    # Base year and month
    base_year = 2020
    base_month = 1

    # Calculate the month and year for the given wave
    month = (base_month + wave - 1) % 12  # Calculate the month (1-12)
    year = base_year + (base_month + wave - 1) // 12  # Calculate the year

    # If month is 0, it means it's December of the previous year
    if month == 0:
        month = 12
        year -= 1

    # Format the result as "MM/YYYY"
    # return f"{year}-{month:02d}-01"
    return f"{month:02d}/{year}"


def append_with_overwrite(
    df_existing: pd.DataFrame,
    df_new: pd.DataFrame,
    *,
    key_cols: list[str] = ["wave", "variable"],
    overwrite: bool = True,
) -> pd.DataFrame:
    """
    Append new rows into an existing dataframe, optionally overwriting
    rows with the same keys.

    Parameters
    ----------
    df_existing : pd.DataFrame
        Existing data.
    df_new : pd.DataFrame
        New data to append.
    key_cols : list[str], default ["wave", "variable"]
        Columns that uniquely identify a row. Used for deduplication.
    overwrite : bool, default True
        If True, drop existing rows with the same keys as df_new before appending.

    Returns
    -------
    pd.DataFrame
        Combined dataframe with deduplicated keys.
    """
    if df_existing.empty:
        return df_new.copy()

    if overwrite:
        # drop rows in existing that have keys present in new
        mask = (
            df_existing[key_cols]
            .apply(tuple, axis=1)
            .isin(df_new[key_cols].apply(tuple, axis=1))
        )
        df_existing = df_existing.loc[~mask]

    return pd.concat([df_existing, df_new], ignore_index=True)


def configure_logging(
    log_file: Optional[str] = None, *, overwrite: bool = True
) -> None:

    root = logging.getLogger()
    if getattr(root, "_app_logging_configured", False):
        return  # already configured; avoid duplicate handlers

    root.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="(%Y-%m-%d %H:%M:%S)",
    )

    # Remove any existing handlers (from default IPython)
    if overwrite:
        for h in root.handlers[:]:
            root.removeHandler(h)

    # --- Console handler ---
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # --- File handler ---
    if log_file:
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)

        fh = RotatingFileHandler(
            log_file, mode="a", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # Mark as configured (preventing re-adding handlers)
    root._app_logging_configured = True


if __name__ == "__main__":
    pass
