import pandas as pd
from connectors import devo


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

    base_query = f"SELECT {query_vars} FROM lab_{lab_name}.{table_name}"

    if wave is not None:
        query = f"{base_query} WHERE wave = {wave}"
    else:
        query = base_query

    df = devo.read_sql(query)
    return df