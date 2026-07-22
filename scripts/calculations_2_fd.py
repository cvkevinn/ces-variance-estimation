import logging
import pandas as pd
from scripts._stats_fd import main_calculate_stats_fd, main_calculate_other_stats

logger = logging.getLogger(__name__)


def main_calculations_fd(
    df_output: pd.DataFrame, breakdown_vars: list[str], correlation: float, lag: int
):
    # We have to pass df_output_t2 and df_output_t1 HERE
    if not isinstance(breakdown_vars, list) or not all(
        isinstance(var, str) for var in breakdown_vars
    ):
        raise ValueError("breakdown_vars must be a list of strings")

    df_main_stats = main_calculate_stats_fd(df_output, breakdown_vars, correlation, lag)
    df_output_fd = main_calculate_other_stats(df_main_stats)
    return df_output_fd


if __name__ == "__main__":
    pass
