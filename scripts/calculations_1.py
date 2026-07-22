import logging
import pandas as pd
from scripts._input import main_input_preparations, main_input_preparations_ea6
from scripts._boots import (
    bootstrap_replicates,
    bootstrap_weights,
    bootstrap_weights_blended,
    main_bootstrap_quantitative_estimates,
    main_bootstrap_qualitative_estimates,
    main_bootstrap_prob_bin_estimates,
)
from scripts._adjust import main_adjusted_weights
from scripts._stats import main_calculate_stats

logger = logging.getLogger(__name__)


def main_calculations(
    df_raw: pd.DataFrame,
    varlist: list[str],
    vars_type: str,
    breakdown_vars: list[str],
    rep: int,
    winsorization: bool,
    seed_number: int,
    # NEW: YAML-driven suffix config
    suffix_schema_default: list[str] | None = None,
    var_suffix_map: dict[str, list[str]] | None = None,
) -> pd.DataFrame:

    if vars_type not in ["qualitative", "quantitative", "prob_bin"]:
        raise ValueError(
            "vars_type must be either 'qualitative' or 'quantitative' or 'prob_bin'"
        )

    if not isinstance(breakdown_vars, list) or not all(
        isinstance(var, str) for var in breakdown_vars
    ):
        raise ValueError("breakdown_vars must be a list of strings")

    # df = main_input_preparations_ea6(df_raw, varlist, vars_type, breakdown_vars)
    df = main_input_preparations(df_raw, varlist, vars_type, breakdown_vars)
    df_replicates = bootstrap_replicates(df, rep, seed_number)
    df_bweights = bootstrap_weights(df_replicates, rep)
    df_bweights_blended = bootstrap_weights_blended(df_bweights, rep)
    df_bweights_blended_adj = main_adjusted_weights(df_bweights_blended, rep)

    if vars_type == "qualitative":
        derived_cols: list[str] = []
        for v in varlist:
            # Get per-variable suffix schema, else fallback to default
            suffixes = None
            if var_suffix_map and v in var_suffix_map:
                suffixes = var_suffix_map[v]
            elif suffix_schema_default:
                suffixes = suffix_schema_default
            else:
                raise ValueError(f"No suffix schema found for variable '{v}'")

            derived_cols.extend([f"{v}_{s}" for s in suffixes])

        df_estimates = main_bootstrap_qualitative_estimates(
            df,
            df_bweights_blended_adj,
            derived_cols,
            breakdown_vars,
            rep,
            winsorization,
        )
    elif vars_type == "prob_bin":
        df_estimates = main_bootstrap_prob_bin_estimates(
            df,
            df_bweights_blended_adj,
            varlist,
            breakdown_vars,
            rep,
        )
    else:
        df_estimates = main_bootstrap_quantitative_estimates(
            df,
            df_bweights_blended_adj,
            varlist,
            breakdown_vars,
            rep,
            winsorization,
        )

    df_output = main_calculate_stats(df, df_estimates, breakdown_vars, rep)
    return df_output


if __name__ == "__main__":
    pass
