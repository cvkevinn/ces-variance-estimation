import logging
from typing import Mapping, Optional, Sequence, Literal
import numpy as np
import pandas as pd
from ces_edp._constants import (
    EA_MAP,
    AGE_MAP,
    INCOME_MAP,
    QUALITATIVE_MAP,
    INDICATOR_MAP,
)
from ces_edp._get_codelists import get_codelists, REGISTRY_ACC
from ces_edp._tools import download_table
from settings import CES_CODELIST_PATH

logger = logging.getLogger(__name__)


EXP_C1150 = {"expectations_med", "expectations_p25", "expectations_p75"}  # c1150_exp
UNCERT_C1150 = {"uncertainty_med"}  # c1150_uncert
COUNT_VARS = {"sample_size", "population_size"}

# This maps naming from DSD and Codelists (which is slightly different)
MAP_COLUMNS = {
    "FREQ": "CL_FREQ",
    "REF_AREA": "CL_AREA",
    "CES_BREAKDOWN": "CL_CES_BREAKDOWN",
    "CES_CUSTOM": "CL_CES_CUSTOM",
    "CES_VARIABLE": "CL_CES_VARIABLE",
    "CES_ANSWER": "CL_CES_ANSWER",
    "CES_DENOM": "CL_CES_DENOM",
}

ORDER = [
    "FREQ",
    "REF_AREA",
    "CES_BREAKDOWN",
    "CES_CUSTOM",
    "CES_VARIABLE",
    "CES_ANSWER",
    "CES_DENOM",
    "TIME_PERIOD",
    "OBS_VALUE",
    "OBS_STATUS",
    "CONF_STATUS",
    "TIME_FORMAT",
    "COLLECTION",
    "DECIMALS",
    "TITLE_COMPL",
    "TITLE",
    "UNIT",
    "UNIT_MULT",
]


def append_count_rows(df: pd.DataFrame, id_cols: list[str]):
    """
    Take 'sample_size' and 'population_size' columns and append them as extra rows under 'value'.
    - var_type = 'numerical'
    - qualitative_measure = 'NUM_VAR'
    - indicator: sample_size -> 'sample_size', population_size -> 'population_size'
    """
    value_vars = [c for c in ("sample_size", "population_size") if c in df.columns]
    if not value_vars:
        return df.copy()

    tmp = "__tmp_counts__"

    # Before melting, keep only one row per id_cols combination
    # because sample_size/population_size are the same for all indicators with same id_cols
    df_for_melt = df[id_cols + value_vars].drop_duplicates(subset=id_cols)

    stack = (
        df_for_melt.melt(
            id_vars=id_cols,
            value_vars=value_vars,
            var_name="which",
            value_name=tmp,
        )
        .dropna(subset=[tmp])  # skip missing counts
        .assign(
            qualitative_measure="numerical",
            indicator=lambda x: x["which"],
        )
        .drop(columns="which")
        .rename(columns={tmp: "value"})
    )

    base = df.drop(columns=value_vars, errors="ignore")

    out = pd.concat([base, stack], ignore_index=True, sort=False)
    return out


def build_title_compl(
    df: pd.DataFrame,
    codelists: Mapping[str, Mapping[str, str]],  # you codelist i.e., xml already parsed
    columns: Sequence[str],
    out_col: str = "TITLE_COMPL",
    sep: str = " - ",
    warn_unmapped: bool = True,
) -> pd.DataFrame:
    """
    Map codes in `columns` to their descriptions via `codelists[col]` and join them with `sep`.
    """
    # Map each column using its same-named codelist
    mapped = pd.DataFrame(
        {col: df[col].map(codelists.get(col, {})) for col in columns},
        index=df.index,
    )

    # Optional warnings for unmapped codes
    if warn_unmapped:
        for col in columns:
            if col not in codelists:
                logger.warning("No codelist found for column '%s'.", col)
                continue
            missing_mask = mapped[col].isna() & df[col].notna()
            if missing_mask.any():
                missing_vals = df.loc[missing_mask, col].astype(str).value_counts()
                logger.warning(
                    "Unmapped codes in column '%s': %s",
                    col,
                    ", ".join(f"{k} (n={v})" for k, v in missing_vals.items()),
                )

    # Join non-empty descriptions across the requested columns
    df[out_col] = mapped.apply(
        lambda r: sep.join([x for x in r if pd.notna(x) and x != ""]),
        axis=1,
    )
    return df


def main_preparations_edp(
    df: pd.DataFrame,
    *,
    reg: str = REGISTRY_ACC,
    cache_xml: Optional[str] | None = None,  # path to cached XML file or None
    cache_mode: Literal["prefer", "refresh", "ignore", "only"] = "prefer",
) -> pd.DataFrame:
    """Transform raw CES rows into EDP-formatted output.

    This function:
      1) normalizes variables (e.g., `c1150` → `c1150_exp` / `c1150_uncert`),
      2) appends count variables to long form,
      3) derives `FREQ`, `CES_BREAKDOWN`, `CES_ANSWER`, `CES_DENOM`,
      4) builds `OBS_VALUE`, `DECIMALS`, `TIME_PERIOD`, `TIME_FORMAT`,
      5) fills admin columns, and
      6) constructs `TITLE_COMPL` using SDMX codelists (fetched and cached via `cache_mode`).

    Column ordering in the returned DataFrame follows the predefined `ORDER` list;
    missing expected columns are logged as warnings.

    Args:
      df: Input DataFrame containing the raw CES data.
      cache_xml: Path to the codelist XML cache file, or None to skip caching.
      reg: SDMX registry (e.g., REGISTRY_ACC or REGISTRY_PROD).
      cache_mode: Cache policy for codelist XML: "prefer" | "refresh" | "ignore" | "only".
        * "prefer" (default): read from `cache_path` if it exists; otherwise fetch
        from the network and write the response to `cache_path`.
        * "refresh": always fetch from the network and overwrite `cache_path`.
        * "ignore": always fetch from the network; do not read or write `cache_path`.
        * "only": read from `cache_path` only; raise FileNotFoundError if missing.
    Returns:
      A new DataFrame with EDP columns in canonical order.

    Raises:
      FileNotFoundError: If `cache_mode="only"` and `cache_xml` is missing.
      requests.HTTPError: If codelist fetching fails with a non-2xx status.
      xml.etree.ElementTree.ParseError: If codelist XML cannot be parsed.
    """

    # 0) keep only needed columns (copy to avoid side effects)
    needed = [
        "date",
        "wave",
        "country",
        "breakdown_other",
        "breakdown_other_categ",
        "variable",
        "qualitative_measure",
        "indicator",
        "value",
        "sample_size",
        "population_size",
        "flag_n",
    ]
    df = df.loc[:, [c for c in needed if c in df.columns]].copy()
    ## Delete aggregates with sample size < 20
    df = df[df["sample_size"] >= 20].reset_index(drop=True)

    # 1) normalize variable c1150 -> c1150_exp / c1150_uncert
    m = df["variable"].eq("c1150")
    df.loc[m & df["indicator"].isin(EXP_C1150), "variable"] = "c1150_exp"
    df.loc[m & df["indicator"].isin(UNCERT_C1150), "variable"] = "c1150_uncert"

    # 2) count_vars to long
    id_cols = [
        "date",
        "wave",
        "country",
        "breakdown_other",
        "breakdown_other_categ",
        "variable",
    ]
    df = append_count_rows(df, id_cols)

    # 3) FREQ
    is_q = df["variable"].str.lower().str.startswith("q", na=False)
    df["FREQ"] = np.where(is_q, "Q", "M").astype(str)

    # 4) CES_BREAKDOWN
    code = df["breakdown_other_categ"].astype("Int64")
    is_age = df["breakdown_other"].eq("age")
    is_inc = df["breakdown_other"].eq("income")
    brk = np.where(
        is_age, code.map(AGE_MAP), np.where(is_inc, code.map(INCOME_MAP), "ALL")
    )
    df["CES_BREAKDOWN"] = pd.Series(brk, index=df.index).fillna("ALL").astype(str)
    df = df.loc[df["CES_BREAKDOWN"].ne("AGE_70+")].reset_index(
        drop=True
    )  # Oldest don't go public

    # 5) CES_ANSWER / CES_DENOM
    df["CES_ANSWER"] = (
        df["qualitative_measure"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(QUALITATIVE_MAP)
        .fillna("NUM_VAR")
        .astype(str)
    )
    df["CES_DENOM"] = (
        df["indicator"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(INDICATOR_MAP)
        .astype(str)
    )

    # 6) DECIMALS / OBS_VALUE
    df["DECIMALS"] = np.where(df["indicator"].isin(COUNT_VARS), 0, 1).astype(int)
    v = pd.to_numeric(df["value"], errors="coerce")
    df["OBS_VALUE"] = np.where(df["DECIMALS"].eq(0), v.round(0), v.round(1))

    # 7) TIME fields (driven by FREQ)
    d = pd.to_datetime(df["date"], format="%m/%Y", errors="coerce")
    df["TIME_PERIOD"] = np.where(
        df["FREQ"].eq("Q"),
        d.dt.to_period("Q").astype("string").str.replace("Q", "-Q", n=1),
        d.dt.to_period("M").astype("string"),
    ).astype(str)
    df["TIME_FORMAT"] = np.where(df["FREQ"].eq("Q"), "P3M", "P1M").astype(str)

    # 9) OBS_STATUS -> U = unreliable
    is_u = df["flag_n"].str.lower().eq("u")
    df["OBS_STATUS"] = np.where(is_u, "U", "A").astype(str)

    # 8) static/admin
    df["REF_AREA"] = df["country"].replace(EA_MAP).astype(str)
    df["CES_VARIABLE"] = df["variable"].str.upper().astype(str)
    df["COLLECTION"] = "U"
    df["CONF_STATUS"] = "F"
    df["UNIT"] = "PN"
    df["UNIT_MULT"] = 0
    df["CES_CUSTOM"] = "T"

    # 9) TITLE_COMPL
    codelists = get_codelists(registry=reg, cache_xml=cache_xml, cache_mode=cache_mode)

    # rename → build → rename back (check invert is safe)
    if len(set(MAP_COLUMNS.values())) != len(MAP_COLUMNS):
        logger.error("MAP_COLUMNS values are not unique; cannot invert safely.")
    df2 = df.rename(columns=MAP_COLUMNS)
    df2 = build_title_compl(
        df2,
        codelists,
        columns=[
            "CL_FREQ",
            "CL_AREA",
            "CL_CES_BREAKDOWN",
            "CL_CES_CUSTOM",
            "CL_CES_VARIABLE",
            "CL_CES_ANSWER",
            "CL_CES_DENOM",
        ],
        out_col="TITLE_COMPL",  # This is long title
        warn_unmapped=True,
    )
    df2 = build_title_compl(
        df2,
        codelists,
        columns=[
            # "CL_FREQ", # These two variables appear directly in EDP
            # "CL_AREA", # These two variables appear directly in EDP
            "CL_CES_VARIABLE",
            # "CL_CES_ANSWER",
            "CL_CES_DENOM",
            # "CL_CES_BREAKDOWN",
            # "CL_CES_CUSTOM",
        ],
        out_col="TITLE",  # This is short title
        sep=", ",
        warn_unmapped=True,
    )
    inv = {v: k for k, v in MAP_COLUMNS.items()}
    df3 = df2.rename(columns=inv)

    # 10) final order & warning
    final_cols = [c for c in ORDER if c in df3.columns]
    miss = [c for c in ORDER if c not in df3.columns]
    if miss:
        logger.warning("Missing expected columns (skipped): %s", miss)

    return df3.loc[:, final_cols]


if __name__ == "__main__":

    df = download_table("prj_ces_production", "aggregates_final", "all", 71)
    # Transforming to edp format
    CACHE_PATH = str(CES_CODELIST_PATH)
    df_final = main_preparations_edp(
        df, reg=REGISTRY_ACC, cache_xml=CACHE_PATH, cache_mode="refresh"
    )
