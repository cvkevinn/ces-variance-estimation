from __future__ import annotations
from pathlib import Path
from typing import Iterable, Literal, Tuple, Dict, List, Sequence, Optional
import hashlib
import pandas as pd
import numpy as np
import yaml
import logging
from scripts.calculations_1 import main_calculations as run_stats
from scripts.calculations_2_fd import main_calculations_fd as run_stats_fd
from scripts._tools import download_table_fixed, download_table_fixed_q, wave_to_date

logger = logging.getLogger(__name__)

# ---------------------------------
# Cache primitives
# ---------------------------------

CACHE_DIR = Path("./cache")
CACHE_DIR.mkdir(exist_ok=True)

Freq = Literal["M", "Q"]


def _cache_key(
    freq: Freq,
    wave: int | None,
    lag: int | None,
    waves: Optional[List[int]],
    _cols_unused: Iterable[str],
) -> Path:
    if waves is not None:
        ws = sorted(set(int(w) for w in waves))
        h = hashlib.sha1(",".join(map(str, ws)).encode()).hexdigest()[:8]
        # add hint: first-last and count
        hint = f"{ws[0]}-{ws[-1]}_n{len(ws)}"
        tag = f"{freq}_waves_{hint}_{h}"
    elif wave is None:
        tag = f"{freq}_all"
    else:
        tag = f"{freq}_w{wave}_lag{lag}"
    return CACHE_DIR / f"{tag}.parquet"


def _download_from_source(
    freq: Freq,
    cols: Sequence[str],
    wave: int | None,
    lag: int | None,
    waves: Optional[List[int]],
) -> pd.DataFrame:
    if waves is not None:
        if freq == "Q":
            return download_table_fixed_q(list(cols), waves=waves)
        return download_table_fixed(list(cols), waves=waves)

    if wave is None:
        if freq == "Q":
            return download_table_fixed_q(list(cols), wave=None)
        return download_table_fixed(list(cols), wave=None)

    if lag is None:
        raise ValueError("lag must be provided when wave is specified.")

    wave_pair = [wave - lag, wave]
    if freq == "Q":
        return download_table_fixed_q(list(cols), waves=wave_pair)
    return download_table_fixed(list(cols), waves=wave_pair)


def load_or_download(
    freq: Freq,
    cols: List[str],
    wave: int | None,
    lag: int | None,
    *,
    waves: Optional[List[int]] = None,
) -> pd.DataFrame:
    if not cols:
        return pd.DataFrame()

    key = _cache_key(freq, wave, lag, waves, cols)

    def _needs_redownload(df: pd.DataFrame) -> bool:
        # 1) columns missing?
        missing_cols = [c for c in cols if c not in df.columns]
        if missing_cols:
            return True
        # 2) when waves are requested, ensure all those waves exist in cache
        if waves is not None and "wave" in df.columns:
            have = set(int(w) for w in pd.Series(df["wave"]).dropna().unique())
            need = set(int(w) for w in waves)
            if not need.issubset(have):
                return True
        return False

    if key.exists():
        df = pd.read_parquet(key)
        if not _needs_redownload(df):
            return df
        # re-download superset (columns) – rows will come from source
        cols_union = sorted(set(df.columns) | set(cols))
        df = _download_from_source(freq, cols_union, wave, lag, waves)
        df.to_parquet(key, index=False)
        return df

    # Cold download
    df = _download_from_source(freq, cols, wave, lag, waves)
    df.to_parquet(key, index=False)
    return df


# ---------------------------------
# Small helpers
# ---------------------------------


def _list_or_empty(x):
    return x if isinstance(x, list) else []


def _resolve_var_frequency(var_cfg: dict, block_freq: Freq) -> Freq:
    return var_cfg.get("frequency", block_freq)


def _resolve_var_lag(var_cfg: dict, block_lag: int) -> int:
    return int(var_cfg.get("lag", block_lag))


def _resolve_var_winsor(var_cfg: dict, wins_default: bool) -> bool:
    return bool(var_cfg.get("winsorize", wins_default))


def _augment_with_fd_lag(waves: List[int], lag: int) -> List[int]:
    if not waves:
        return waves
    base = set(int(w) for w in waves)
    need = {int(w) - int(lag) for w in base}
    return sorted(base | need)


# ---------------------------------
# Gather union of columns per (freq, lag) to prewarm cache
# ---------------------------------


def _collect_needed_columns_by_freq_lag(cfg: dict) -> Dict[Freq, Dict[int, set[str]]]:
    buckets: Dict[Freq, Dict[int, set[str]]] = {"M": {}, "Q": {}}

    def add_col(freq: Freq, lag: int, col: str):
        buckets.setdefault(freq, {}).setdefault(lag, set()).add(col)

    # Quantitative
    q_block = cfg.get("quantitative") or {}
    q_block_freq: Freq = q_block.get("frequency", "M")
    q_block_lag: int = int(q_block.get("lag", 1))
    for v in _list_or_empty(q_block.get("variables")):
        name = v["name"]
        f = _resolve_var_frequency(v, q_block_freq)
        l = _resolve_var_lag(v, q_block_lag)
        add_col(f, l, name)

    # Qualitative
    qa_block = cfg.get("qualitative") or {}
    qa_block_freq: Freq = qa_block.get("frequency", "M")
    qa_block_lag: int = int(qa_block.get("lag", 1))
    for v in _list_or_empty(qa_block.get("variables")):
        name = v["name"]
        f = _resolve_var_frequency(v, qa_block_freq)
        l = _resolve_var_lag(v, qa_block_lag)
        add_col(f, l, name)

    # Prob-bin
    p_block = cfg.get("prob_bin") or {}
    p_block_freq: Freq = p_block.get("frequency", "M")
    p_block_lag: int = int(p_block.get("lag", 1))
    tails: List[str] = _list_or_empty(p_block.get("columns_from_base"))
    for v in _list_or_empty(p_block.get("variables")):
        base = v["base"]
        f = _resolve_var_frequency(v, p_block_freq)
        l = _resolve_var_lag(v, p_block_lag)
        for t in tails:
            add_col(f, l, f"{base}{t}")

    return buckets


# ---------------------------------
# Output layout normalizer
# ---------------------------------


def finalize_layout(
    df: pd.DataFrame, breakdown: List[str], var_type: str
) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    df = df.copy()

    if "breakdown_flag" in df.columns:
        df.drop(columns=["breakdown_flag"], inplace=True)

    if breakdown == ["wave"]:
        df.insert(1, "country", "EA")
        df.insert(2, "breakdown_other", pd.NA)
        df.insert(3, "breakdown_other_categ", pd.NA)
    elif breakdown == ["wave", "a0020"]:
        df.rename(columns={"a0020": "country"}, inplace=True)
        df.insert(2, "breakdown_other", pd.NA)
        df.insert(3, "breakdown_other_categ", pd.NA)
    elif breakdown == ["wave", "a1110_calib_rec"]:
        df.insert(1, "country", "EA")
        df.insert(2, "breakdown_other", "age")
        df.rename(columns={"a1110_calib_rec": "breakdown_other_categ"}, inplace=True)
    elif breakdown == ["wave", "b7040_imp_quintiles"]:
        df.insert(1, "country", "EA")
        df.insert(2, "breakdown_other", "income")
        df.rename(
            columns={"b7040_imp_quintiles": "breakdown_other_categ"}, inplace=True
        )

    df.insert(
        4, "var_type", "categorical" if var_type == "qualitative" else "numerical"
    )

    df[["variable", "indicator"]] = df["variable"].str.split("_", n=1, expand=True)

    if var_type == "qualitative":
        df[["qualitative_measure", "indicator"]] = df["indicator"].str.split(
            "_", n=1, expand=True
        )
        df["indicator"] = "share"
        move1 = df.pop("qualitative_measure")
        move2 = df.pop("indicator")
        df.insert(7, "qualitative_measure", move1)
        df.insert(8, "indicator", move2)
    else:
        if "qualitative_measure" not in df.columns:
            df.insert(7, "qualitative_measure", pd.NA)
        move = df.pop("indicator")
        df.insert(8, "indicator", move)

    return df


# ---------------------------------
# Smart merge
# ---------------------------------


def _smart_merge(
    df_out: pd.DataFrame, df_fd: pd.DataFrame, keys: List[str]
) -> pd.DataFrame:
    if df_fd is None or df_fd.empty:
        how = "left"
    else:
        left_keys = df_out[keys].drop_duplicates()
        right_keys = (
            df_fd[keys].drop_duplicates()
            if all(k in df_fd.columns for k in keys)
            else pd.DataFrame(columns=keys)
        )
        merged_probe = left_keys.merge(right_keys, on=keys, how="left", indicator=True)
        needs_left = (merged_probe["_merge"] != "both").any()
        how = "left" if needs_left else "inner"
    return df_out.merge(df_fd, on=keys, how=how)


# ---------------------------------
# Core run helper
# ---------------------------------


def _loop_breakdowns(
    df_raw: pd.DataFrame,
    varnames: List[str],
    kind: Literal["quantitative", "qualitative", "prob_bin"],
    breakdowns: List[List[str]],
    rep: int,
    winsorization: bool,
    fd_corr: float,
    lag: int,
    *,
    suffix_schema_default: Optional[List[str]] = None,
    var_suffix_map: Optional[Dict[str, List[str]]] = None,
    target_waves: Optional[List[int]] = None,
) -> pd.DataFrame:
    """
    Compute aggregates + FD on full set (including lag rows), then
    filter the final formatted output to target_waves if provided.
    """
    all_frames = []

    for br in breakdowns:
        per_br_frames = []
        for var in varnames:
            logger.info(f"Variable '{var}' with breakdown {br}:")
            if var not in df_raw.columns:
                continue
            df_local = df_raw.dropna(subset=[var]).copy()
            if df_local.empty:
                logger.info(
                    f"Variable '{var}' does not have observations in the wave/waves analyzed."
                )
                continue

            if kind == "qualitative":
                df_out = run_stats(
                    df_local,
                    [var],
                    kind,
                    br,
                    rep,
                    winsorization,
                    42,
                    suffix_schema_default=suffix_schema_default,
                    var_suffix_map=var_suffix_map,
                )
            else:
                df_out = run_stats(df_local, [var], kind, br, rep, winsorization, 42)

            df_fd = run_stats_fd(df_out, br, fd_corr, lag)
            keys = br + ["variable"]
            merged = _smart_merge(df_out, df_fd, keys)
            formatted = finalize_layout(merged, br, kind)

            if target_waves is not None and "wave" in formatted.columns:
                formatted = formatted[formatted["wave"].isin(target_waves)]

            if not formatted.empty:
                per_br_frames.append(formatted)

        if per_br_frames:
            all_frames.append(pd.concat(per_br_frames, ignore_index=True))

    return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()


# ---------------------------------
# Quantitative
# ---------------------------------


def calculation_quantitative_vars(
    cfg_block: dict,
    rep: int,
    fd_corr: float,
    wave: int | None,
    waves: Optional[List[int]] = None,
    *,
    target_waves: Optional[List[int]] = None,
) -> pd.DataFrame:
    variables = _list_or_empty(cfg_block.get("variables"))
    if not variables:
        return pd.DataFrame()

    wins_default = cfg_block.get("winsorize_default", True)
    block_freq: Freq = cfg_block.get("frequency", "M")
    block_lag: int = int(cfg_block.get("lag", 1))
    breakdowns = _list_or_empty(cfg_block.get("breakdowns"))

    groups: Dict[Tuple[Freq, bool, int], List[str]] = {}
    for v in variables:
        name = v["name"]
        freq = _resolve_var_frequency(v, block_freq)
        lag = _resolve_var_lag(v, block_lag)
        win = _resolve_var_winsor(v, wins_default)
        groups.setdefault((freq, win, lag), []).append(name)

    out_all = []
    for (freq, win, lag), varlist in groups.items():
        waves_aug = _augment_with_fd_lag(waves, lag) if waves is not None else None
        df_raw = load_or_download(freq, varlist, wave, lag, waves=waves_aug)
        df_raw = df_raw.dropna(subset=varlist, how="all").copy()

        out = _loop_breakdowns(
            df_raw,
            varlist,
            "quantitative",
            breakdowns,
            rep,
            win,
            fd_corr,
            lag,
            target_waves=target_waves,
        )
        out_all.append(out)

    return pd.concat(out_all, ignore_index=True) if out_all else pd.DataFrame()


# ---------------------------------
# Qualitative
# ---------------------------------


def calculation_qualitative_vars(
    cfg_block: dict,
    rep: int,
    fd_corr: float,
    wave: int | None,
    waves: Optional[List[int]] = None,
    *,
    target_waves: Optional[List[int]] = None,
) -> pd.DataFrame:
    variables = _list_or_empty(cfg_block.get("variables"))
    if not variables:
        return pd.DataFrame()

    block_freq: Freq = cfg_block.get("frequency", "M")
    block_lag: int = int(cfg_block.get("lag", 1))
    breakdowns = _list_or_empty(cfg_block.get("breakdowns"))

    suffix_schema_default: Optional[List[str]] = cfg_block.get("suffix_schema_default")
    var_suffix_map: Dict[str, List[str]] = {}
    for v in variables:
        nm = v.get("name")
        sch = v.get("suffix_schema")
        if nm and sch:
            var_suffix_map[nm] = sch

    groups: Dict[Tuple[Freq, int], List[str]] = {}
    for v in variables:
        name = v["name"]
        freq = _resolve_var_frequency(v, block_freq)
        lag = _resolve_var_lag(v, block_lag)
        groups.setdefault((freq, lag), []).append(name)

    out_all = []
    for (freq, lag), base_vars in groups.items():
        waves_aug = _augment_with_fd_lag(waves, lag) if waves is not None else None
        df_raw = load_or_download(freq, base_vars, wave, lag, waves=waves_aug)
        df_raw = df_raw.dropna(subset=base_vars, how="all").copy()

        out = _loop_breakdowns(
            df_raw,
            base_vars,
            "qualitative",
            breakdowns,
            rep,
            False,
            fd_corr,
            lag,
            suffix_schema_default=suffix_schema_default,
            var_suffix_map=var_suffix_map,
            target_waves=target_waves,
        )
        out_all.append(out)

    return pd.concat(out_all, ignore_index=True) if out_all else pd.DataFrame()


# ---------------------------------
# Prob-bin
# ---------------------------------


def _build_prob_cols(bases: List[str], tails: List[str]) -> List[str]:
    return [f"{b}{t}" for b in bases for t in tails]


def calculation_probin_vars(
    cfg_block: dict,
    rep: int,
    fd_corr: float,
    wave: int | None,
    waves: Optional[List[int]] = None,
    *,
    target_waves: Optional[List[int]] = None,
) -> pd.DataFrame:
    variables = _list_or_empty(cfg_block.get("variables"))
    if not variables:
        return pd.DataFrame()

    block_freq: Freq = cfg_block.get("frequency", "M")
    block_lag: int = int(cfg_block.get("lag", 1))
    breakdowns = _list_or_empty(cfg_block.get("breakdowns"))
    tails: List[str] = _list_or_empty(cfg_block.get("columns_from_base"))

    groups: Dict[Tuple[Freq, int], List[str]] = {}
    for v in variables:
        base = v["base"]
        freq = _resolve_var_frequency(v, block_freq)
        lag = _resolve_var_lag(v, block_lag)
        groups.setdefault((freq, lag), []).append(base)

    out_all = []
    for (freq, lag), bases in groups.items():
        cols = _build_prob_cols(bases, tails)
        waves_aug = _augment_with_fd_lag(waves, lag) if waves is not None else None
        df_raw = load_or_download(freq, cols, wave, lag, waves=waves_aug)
        df_raw = df_raw.dropna(subset=cols, how="all").copy()

        out = _loop_breakdowns(
            df_raw,
            cols,
            "prob_bin",
            breakdowns,
            rep,
            True,
            fd_corr,
            lag,
            target_waves=target_waves,
        )
        out.loc[out["indicator"] == "imean_v2_median", "indicator"] = "median_exp"
        out.loc[out["indicator"] == "iqr_v2_median", "indicator"] = "median_uncert"

        out_all.append(out)

    return pd.concat(out_all, ignore_index=True) if out_all else pd.DataFrame()


# ---------------------------------
# Orchestrator
# ---------------------------------


def main(
    config_path: str,
    wave: int | None = None,
    waves: Optional[List[int]] = None,
) -> pd.DataFrame:
    """
    You may pass either:
      - wave=<int>     -> compute for that wave, FD needs wave-lag (downloaded but filtered out)
      - waves=[...]    -> compute for that set, FD needs (w-lag) (downloaded but filtered out)
      - neither        -> all waves
    """
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    rep = int(cfg["defaults"]["rep"])
    fd_corr = float(cfg["defaults"].get("fd_correlation", 0.8))

    # define which waves to keep in final output
    if waves is not None:
        target_waves = sorted(set(int(w) for w in waves))
    elif wave is not None:
        target_waves = [int(wave)]
    else:
        target_waves = None  # keep all

    # prewarm
    cols_by_freq_lag = _collect_needed_columns_by_freq_lag(cfg)
    for freq, lag_map in cols_by_freq_lag.items():
        for lag, cols in lag_map.items():
            if not cols:
                continue
            if waves is not None:
                waves_aug = _augment_with_fd_lag(waves, lag)
                _ = load_or_download(
                    freq, sorted(cols), wave=None, lag=None, waves=waves_aug
                )
            else:
                _ = load_or_download(
                    freq,
                    sorted(cols),
                    wave=wave,
                    lag=lag if wave is not None else None,
                    waves=None if wave is not None else None,
                )

    # run
    frames: List[pd.DataFrame] = []

    q_block = cfg.get("quantitative")
    if q_block:
        frames.append(
            calculation_quantitative_vars(
                q_block, rep, fd_corr, wave, waves=waves, target_waves=target_waves
            )
        )

    qa_block = cfg.get("qualitative")
    if qa_block:
        frames.append(
            calculation_qualitative_vars(
                qa_block, rep, fd_corr, wave, waves=waves, target_waves=target_waves
            )
        )

    p_block = cfg.get("prob_bin")
    if p_block:
        frames.append(
            calculation_probin_vars(
                p_block, rep, fd_corr, wave, waves=waves, target_waves=target_waves
            )
        )

    df_total = (
        pd.concat(
            [f for f in frames if f is not None and not f.empty], ignore_index=True
        )
        if frames
        else pd.DataFrame()
    )
    if not df_total.empty:
        df_total.sort_values(
            ["variable", "country", "wave"], inplace=True, ignore_index=True
        )
        # Recording to delete "d" and unreliable "u"
        df_total["flag_n"] = np.select(
            [
                df_total["sample_size"].lt(20),
                df_total["sample_size"].ge(20) & df_total["sample_size"].lt(50),
            ],
            ["d", "u"],
            default="",
        )

        # Recording number of replicates in aggregates calculation
        df_total["n_replicates"] = rep

        # Ensure date is present and first column
        if "date" not in df_total.columns:
            df_total.insert(0, "date", df_total["wave"].map(wave_to_date))
        else:
            # if date exists but not first, move it to the front
            if df_total.columns[0] != "date":
                date_col = df_total.pop("date")
                df_total.insert(0, "date", date_col)

        # --- LAST CLEANUP / MAPPING ---
        drop_indicators = ["iqr_v2_quantile_0.25", "iqr_v2_quantile_0.75"]
        df_total = df_total[~df_total["indicator"].isin(drop_indicators)]

        mapping_indicator = {
            "mean": "mean_w",
            "imean_v2_quantile_0.25": "expectations_p25",
            "imean_v2_quantile_0.5": "expectations_med",
            "imean_v2_quantile_0.75": "expectations_p75",
            "iqr_v2_quantile_0.5": "uncertainty_med",
        }
        df_total["indicator"] = df_total["indicator"].replace(mapping_indicator)

    return df_total


if __name__ == "__main__":
    # Examples:
    # result = main("scripts/config.yaml", wave=None)
    result1 = main("scripts/config.yaml", wave=68)
    # result3 = main("scripts/config.yaml", waves=[66, 67, 68])  # fix this
    pass
