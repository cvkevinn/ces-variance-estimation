from __future__ import annotations
import logging
from typing import Iterable, Dict, List
import pandas as pd
from pandas.api import types as ptypes

logger = logging.getLogger(__name__)

# ---------------------------------
# Canonical natural key
# ---------------------------------
# We always include 'qualitative_measure' in the key; for quantitative rows
# it will just be empty/<NA>, which keeps the key stable across types.
KEY_COLUMNS: List[str] = [
    "wave",
    "variable",
    "country",
    "breakdown_other",
    "breakdown_other_categ",
    "qualitative_measure",  # empty/<NA> for quantitative
    "indicator",
]


# ---------------------------------
# Internal helpers
# ---------------------------------


def _ensure_key_columns(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    """Ensure all key columns exist; if missing, add as <NA> (string dtype)."""
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = pd.Series(pd.array([None] * len(out), dtype="string"))
    return out


def _norm_series(s: pd.Series) -> pd.Series:
    """
    Normalize values for key generation:
      - cast to pandas 'string' dtype
      - convert NA to '<NA>' literal
      - strip whitespace and lower-case (stable, case-insensitive)
    """
    return s.astype("string").fillna("<NA>").str.strip().str.lower()

def _normalize_key_columns(df: pd.DataFrame, key_cols: Iterable[str]) -> pd.DataFrame:
    """
    Ensure key columns exist and normalize them consistently
    (handles float + NaN vs string + <NA>, etc.).
    """
    out = _ensure_key_columns(df, key_cols)
    out = out.copy()
    for c in key_cols:
        out[c] = _norm_series(out[c])
    return out

# ---------------------------------
# Public: key builders & checks
# ---------------------------------


def add_unique_keys(
    df: pd.DataFrame,
    key_str_col: str = "key_str",
    cols: Iterable[str] = KEY_COLUMNS,
) -> pd.DataFrame:
    """
    Add a human-readable composite key column 'key_str' built from the natural key.
    Idempotent: if the column already exists, it is not added again.
    """
    out = _ensure_key_columns(df, cols)
    if key_str_col in out.columns:
        return out

    parts = [_norm_series(out[c]) for c in cols]
    key_str = parts[0]
    for p in parts[1:]:
        key_str = key_str + "|" + p
    out[key_str_col] = key_str
    return out


def find_duplicates(
    df: pd.DataFrame, cols: Iterable[str] = KEY_COLUMNS
) -> pd.DataFrame:
    """
    Return duplicated rows by natural key. If none, returns empty DataFrame.
    """
    if df.empty:
        return df.copy()
    norm = _ensure_key_columns(df, cols)
    for c in cols:
        norm[c] = _norm_series(norm[c])
    mask = norm.duplicated(subset=list(cols), keep=False)
    return df.loc[mask].copy()


def assert_no_duplicates(df: pd.DataFrame, cols: Iterable[str] = KEY_COLUMNS) -> None:
    """
    Raise a clear error if duplicates exist by natural key.
    """
    dups = find_duplicates(df, cols=cols)
    if not dups.empty:
        sample = dups[list(cols)].drop_duplicates().head(10)
        raise ValueError(
            "Duplicate aggregates detected by uniqueness key.\n"
            f"Example duplicates (first 10):\n{sample.to_string(index=False)}"
        )


# ---------------------------------
# Upload planning & safe append
# ---------------------------------


def summarize_upload_plan(
    df_existing: pd.DataFrame, df_new: pd.DataFrame, overwrite: bool
) -> Dict[str, object]:
    """
    Return a small summary dict of what would happen on upload.
    Uses the canonical natural key (KEY_COLUMNS).
    """
    if df_new.empty:
        return {
            "mode": "overwrite" if overwrite else "append-only",
            "new_rows": 0,
            "existing_rows": int(len(df_existing)),
            "key_columns": KEY_COLUMNS,
            "conflicting_key_rows": 0,
            "will_replace_rows": 0,
        }

    # ex_norm = (
    #     _normalize_key_columns(df_existing, KEY_COLUMNS)
    #     if not df_existing.empty
    #     else df_existing
    # )
    # ne_norm = _normalize_key_columns(df_new, KEY_COLUMNS)

    ex_norm = df_existing.copy()
    ne_norm = df_new.copy()

    # Internal uniqueness checks first (fast fail)
    assert_no_duplicates(ne_norm, cols=KEY_COLUMNS)
    if not ex_norm.empty:
        assert_no_duplicates(ex_norm, cols=KEY_COLUMNS)

    if ex_norm.empty:
        n_conflicts = 0
        n_replace = 0
    else:
        keys_new = ne_norm[KEY_COLUMNS].drop_duplicates()
        common = ex_norm.merge(keys_new, on=KEY_COLUMNS, how="inner")
        n_conflicts = int(len(common))
        n_replace = int(common[KEY_COLUMNS].drop_duplicates().shape[0])

    return {
        "mode": "overwrite" if overwrite else "append-only",
        "new_rows": int(len(df_new)),
        "existing_rows": int(len(df_existing)),
        "key_columns": KEY_COLUMNS,
        "conflicting_key_rows": n_conflicts,
        "will_replace_rows": n_replace if overwrite else 0,
    }


def get_conflicting_keys(
    df_existing: pd.DataFrame,
    df_new: pd.DataFrame,
    key_cols: Iterable[str] = KEY_COLUMNS,
) -> pd.DataFrame:
    """
    Return the set of natural keys that appear in BOTH frames.
    One row per key.
    """
    if df_existing.empty or df_new.empty:
        return pd.DataFrame(columns=list(key_cols))

    ex_norm = _normalize_key_columns(df_existing, key_cols)
    ne_norm = _normalize_key_columns(df_new, key_cols)

    return (
        ex_norm[list(key_cols)]
        .drop_duplicates()
        .merge(ne_norm[list(key_cols)].drop_duplicates(), on=list(key_cols), how="inner")
    )


def get_conflict_rows(
    df_existing: pd.DataFrame,
    df_new: pd.DataFrame,
    key_cols: Iterable[str] = KEY_COLUMNS,
    include_sources: bool = True,
) -> pd.DataFrame:
    """
    Return the FULL rows for both sides for all conflicting keys.
    Adds a column '_source' ∈ {'existing','new'} (if include_sources=True).
    """
    keys = get_conflicting_keys(df_existing, df_new, key_cols=key_cols)
    if keys.empty:
        return pd.DataFrame(
            columns=list(key_cols) + (["_source"] if include_sources else [])
        )

    ex_rows_norm = _normalize_key_columns(df_existing, key_cols).merge(
        keys, on=list(key_cols), how="inner"
    )
    ne_rows_norm = _normalize_key_columns(df_new, key_cols).merge(
        keys, on=list(key_cols), how="inner"
    )

    if include_sources:
        ex_rows = ex_rows_norm.assign(_source="existing")
        ne_rows = ne_rows_norm.assign(_source="new")

    return pd.concat([ex_rows_norm, ne_rows_norm], ignore_index=True)


def compare_conflicts(
    df_existing: pd.DataFrame,
    df_new: pd.DataFrame,
    compare_cols: list[str],
    key_cols: Iterable[str] = KEY_COLUMNS,
) -> pd.DataFrame:
    """
    For each conflicting key, return side-by-side values for the requested
    columns plus simple diffs:
      - If numeric: absolute difference (col_diff_abs)
      - If non-numeric: 'changed' boolean (col_changed)
    """
    keys = get_conflicting_keys(df_existing, df_new, key_cols=key_cols)
    if keys.empty:
        # empty but with expected columns
        base = pd.DataFrame(columns=list(key_cols))
        for c in compare_cols:
            base[f"{c}_existing"] = pd.Series(dtype="object")
            base[f"{c}_new"] = pd.Series(dtype="object")
            base[f"{c}_diff_abs"] = pd.Series(dtype="float64")
            base[f"{c}_changed"] = pd.Series(dtype="boolean")
        return base

    ex_norm = _normalize_key_columns(df_existing, key_cols)
    ne_norm = _normalize_key_columns(df_new, key_cols)

    left = keys.merge(ex_norm[list(key_cols) + compare_cols], on=list(key_cols), how="left")
    right = keys.merge(ne_norm[list(key_cols) + compare_cols], on=list(key_cols), how="left")

    # suffix join
    comp = left.merge(
        right,
        on=list(key_cols),
        how="left",
        suffixes=("_existing", "_new"),
    )

    # diffs
    for c in compare_cols:
        ce = f"{c}_existing"
        cn = f"{c}_new"

        # numeric?
        is_num = ptypes.is_numeric_dtype(comp[ce]) and ptypes.is_numeric_dtype(comp[cn])
        if is_num:
            comp[f"{c}_diff_abs"] = (comp[ce] - comp[cn]).abs()
            comp[f"{c}_changed"] = comp[ce] != comp[cn]
        else:
            comp[f"{c}_diff_abs"] = pd.NA
            comp[f"{c}_changed"] = comp[ce].astype("string") != comp[cn].astype(
                "string"
            )

    return comp


def diff_counts_by_variable_multi(
    conflict_compare: pd.DataFrame,
    metrics: list[str] | None = None,
) -> pd.DataFrame:
    """
    Return a DataFrame indexed by 'variable' with one column per metric,
    counting how many conflicting rows changed for that metric.

    If metrics is None, auto-detect metrics by scanning '*_changed' columns.
    """
    if conflict_compare.empty:
        return pd.DataFrame()

    # auto-detect metrics if not provided
    if metrics is None:
        metrics = [c[:-8] for c in conflict_compare.columns if c.endswith("_changed")]

    out = {}
    for m in metrics:
        changed_col = f"{m}_changed"
        if changed_col not in conflict_compare.columns:
            continue
        # sum booleans per variable -> integer count of differences
        s = conflict_compare.groupby("variable")[changed_col].sum(min_count=0)
        out[m] = s.astype(int)

    if not out:
        return pd.DataFrame()

    df = pd.DataFrame(out).fillna(0).astype(int).sort_index()
    return df


def log_diff_counts_by_variable(diff_counts: pd.DataFrame) -> None:
    """
    Pretty logger for the counts DataFrame returned by diff_counts_by_variable_multi.
    Logs only non-zero counts for clarity.
    """
    if diff_counts.empty:
        logger.info("No conflicting differences detected on requested metrics.")
        return

    for metric in diff_counts.columns:
        nonzero = diff_counts[metric][diff_counts[metric] > 0]
        if nonzero.empty:
            logger.info("No differences for '%s'.", metric)
        else:
            logger.info("Differences by variable for '%s':", metric)
            for var, cnt in nonzero.items():
                logger.info("  %s -> %d different rows", var, cnt)


def append_with_overwrite_safe(
    df_existing: pd.DataFrame, df_new: pd.DataFrame, overwrite: bool
) -> pd.DataFrame:
    """
    Append/overwrite with strong safety checks using the canonical natural key.

    Rules:
    - New data must be internally unique by KEY_COLUMNS.
    - If overwrite=False and there are key collisions with existing → raise.
    - If overwrite=True → drop conflicting keys from existing, then concat.
    - Final output must be unique by KEY_COLUMNS.
    """
    if df_new.empty:
        logger.info("append_with_overwrite_safe: no new rows (no-op).")
        return df_existing.copy()

    ne = _ensure_key_columns(df_new, KEY_COLUMNS)
    ex = (
        _ensure_key_columns(df_existing, KEY_COLUMNS)
        if not df_existing.empty
        else df_existing
    )

    # 1) New data must be internally unique
    assert_no_duplicates(ne, cols=KEY_COLUMNS)

    # 2) Detect conflicts with existing
    if not ex.empty:
        conflicts = (
            ex[KEY_COLUMNS]
            .merge(ne[KEY_COLUMNS].drop_duplicates(), on=KEY_COLUMNS, how="inner")
            .drop_duplicates()
        )
    else:
        conflicts = pd.DataFrame(columns=KEY_COLUMNS)

    overwritten_count = len(conflicts)  # ← for logger

    # 3) If append-only and conflicts exist → refuse
    if not overwrite and not conflicts.empty:
        raise ValueError(
            "Refusing to upload: found key collisions with overwrite=False.\n"
            f"Sample conflicts:\n{conflicts.head(10).to_string(index=False)}"
        )

    # 4) If overwrite → drop conflicting keys from existing, then concat
    if overwrite and not conflicts.empty and not ex.empty:
        keep_existing = (
            ex.merge(conflicts.assign(_hit=1), on=KEY_COLUMNS, how="left")
            .loc[lambda d: d["_hit"].isna()]
            .drop(columns="_hit")
        )
        out = pd.concat([keep_existing, ne], ignore_index=True)
    else:
        out = pd.concat([ex, ne], ignore_index=True) if not ex.empty else ne.copy()

    # 5) Final guard: output must be unique
    assert_no_duplicates(out, cols=KEY_COLUMNS)

    # ---- logger summary (minimal addition) ----
    if overwrite:
        logger.info(
            "append_with_overwrite_safe: %d new rows, %d overwritten, final size %d.",
            len(ne),
            overwritten_count,
            len(out),
        )
    else:
        logger.info(
            "append_with_overwrite_safe: %d new rows appended, final size %d.",
            len(ne),
            len(out),
        )

    return out
