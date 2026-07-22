
import pandas as pd
from connectors import devo

from settings import OUTPUT_ROOT, STORAGE_BUCKET_EDP

aggregates_edp = pd.read_csv(OUTPUT_ROOT / "ces_aggregates_edp_devo_all.csv")

aggregates_edp.columns = aggregates_edp.columns.str.lower()

aggregates_edp["obs_date"] = aggregates_edp["time_period"]
aggregates_edp = aggregates_edp.rename(columns={"time_period": "period_name"})

aggregates_edp = aggregates_edp[["series_key", "period_name", "obs_date", "obs_value"]]

s = aggregates_edp["obs_date"].astype(str).str.strip()

# Convert quarter labels to first month of quarter:
# 2022-Q2 -> 2022-04, 2022-Q3 -> 2022-07, etc.
month_key = s.str.replace(
    r"^(\d{4})-Q([1-4])$",
    lambda m: f"{m.group(1)}-{(int(m.group(2)) - 1) * 3 + 1:02d}",
    regex=True,
)

# Store as dataframe columns
aggregates_edp["obs_period"] = pd.to_datetime(
    month_key, format="%Y-%m", errors="coerce"
).dt.to_period("M")

aggregates_edp["base_period"] = pd.Period("2022-04", freq="M")

# Wave starts at 28 for 2022-04
aggregates_edp["wave"] = (
    28
    + aggregates_edp["obs_period"].astype("Int64")
    - aggregates_edp["base_period"].astype("Int64")
)



# Compute wave via year/month arithmetic (works even when Period casting fails)
obs_ts = aggregates_edp["obs_period"].dt.to_timestamp()
base_ts = pd.Timestamp("2022-04-01")

aggregates_edp["wave"] = (
    28
    + (obs_ts.dt.year - base_ts.year) * 12
    + (obs_ts.dt.month - base_ts.month)
).astype("Int64")


check = (
    aggregates_edp.loc[
        aggregates_edp["obs_date"].isin(["2022-04", "2022-Q2", "2022-Q3", "2026-04"]),
        ["obs_date", "wave"],
    ]
    .sort_values("obs_date")
)

print(check)


# split and upload parquet files to DEVO:
aggregates_devo = aggregates_edp[["series_key", "period_name", "obs_date", "obs_value", "wave"]]

destination_pq_path = f"s3a://{STORAGE_BUCKET_EDP}/dlb_ces/db/ces_aggregates_edp_devo_wave"


for wave, df in aggregates_devo.groupby("wave"):

    pq_name = f"ces_aggregates_edp_devo_wave_{wave}.parquet"

    df_pq = aggregates_devo[aggregates_devo["wave"] == wave]
    df_pq = df_pq.drop(columns="wave")
    df_pq = df_pq.reset_index(drop=True)

    print(f"Uploading wave {wave} to DEVO as {pq_name}...")
    devo.to_parquet(
        df=df_pq,
        path = f"{destination_pq_path}/{pq_name}",
    )


# recreate table on DEVO:
devo.execute(f"DROP TABLE IF EXISTS xlab_dlb_ces.aggregate_indicators_ces_edp PURGE;")
devo.execute(f"CREATE EXTERNAL TABLE IF NOT EXISTS xlab_dlb_ces.aggregate_indicators_ces_edp LIKE PARQUET '{destination_pq_path}/{pq_name}' STORED AS PARQUET LOCATION '{destination_pq_path}';")
