import logging
import numpy as np
import os
from typing import Optional, List
from unicodedata import numeric
import pandas as pd

from connectors import devo
from datetime import datetime
from data_preparations.monthly_data_prep import (
    main as run_data_preparatations_monthly,
)
from data_preparations.quarterly_data_prep import (
    main as run_data_preparations_quarterly,
)
from scripts.calculations_production import main as run_aggregates
from scripts._tools import configure_logging, upload_table, download_table
from settings import table_storage_path
from scripts._upload import (
    add_unique_keys,
    assert_no_duplicates,
    append_with_overwrite_safe,
    summarize_upload_plan,
    get_conflicting_keys,
    get_conflict_rows,
    compare_conflicts,
    diff_counts_by_variable_multi,
    log_diff_counts_by_variable,
)
from others.ces_internal import main_ces_internal_shape
from others.ces_website import main_ces_website_shape
from others.ces_dashboard import main_ces_db_shape
from others._tools_others import write_excel_by_topic

from ces_edp.preparing_data import main_preparations_edp
from ces_edp.transform_sdmx_file import transform_file, update_release_time
from ces_edp.validate_file_with_fr import api_validation
from ces_edp._constants import REGISTRY_ACC, REGISTRY_PROD
from settings import CACHE_DIR, CES_CODELIST_PATH, LOG_DIR, OUTPUT_ROOT


LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = f"Aggregates_Variance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
configure_logging(str(LOG_DIR / LOG_FILE), overwrite=True)
logger = logging.getLogger(__name__)


DST_SCHEMA = "lab_prj_ces_production"
DST_TABLE = "aggregates_final"  # or  "aggregates_final_ea6"
SRC_TABLE_FQDN = f"{DST_SCHEMA}.{DST_TABLE}"


def read_existing_or_empty() -> pd.DataFrame:
    try:
        df = devo.read_sql(f"SELECT * FROM {SRC_TABLE_FQDN}")
        devo.close()
        logger.info("Loaded %d existing rows.", len(df))
        return df
    except Exception as e:
        logger.warning("No existing table found (%s). Using empty frame.", e)
        return pd.DataFrame()


def run_pipeline(
    config: str,
    wave: Optional[int],
    waves: Optional[List[int]],
):
    # Validate user inputs: allow only one of wave / waves
    if wave is not None and waves is not None:
        raise ValueError("Please set either WAVE or WAVES, not both.")
    if waves is not None and len(waves) == 0:
        raise ValueError("WAVES was provided but empty. Use None or a non-empty list.")

    df_existing = read_existing_or_empty()
    # Ensure existing has key_str (idempotent; noop if already present)
    df_existing = add_unique_keys(df_existing, key_str_col="key_str")

    # Guard existing uniqueness by natural key
    assert_no_duplicates(df_existing)

    if waves is not None:
        waves_msg = ", ".join(map(str, sorted(set(int(w) for w in waves))))
        logger.info("Running aggregates for waves: %s", waves_msg)
    elif wave is not None:
        logger.info("Running aggregates for wave: %s", int(wave))
    else:
        logger.info("Running aggregates for all waves (full history).")

    # Run aggregates — pass only the relevant argument
    if waves is not None:
        df_new = run_aggregates(config, waves=waves)  # multiple waves
    elif wave is not None:
        df_new = run_aggregates(config, wave=wave)  # single wave
    else:
        df_new = run_aggregates(config)  # all waves

    # Always add key_str to new results (idempotent)
    # df_new = add_unique_keys(df_new, key_str_col="key_str")

    # Align different NA values in breakdown categories
    df_new["breakdown_other_categ"] = df_new["breakdown_other_categ"].astype("string").fillna("<na>")
    df_new['breakdown_other_categ'] = df_new['breakdown_other_categ'].replace({'<na>': np.nan})
    df_new["breakdown_other_categ"] = df_new["breakdown_other_categ"].astype('float') 

    return df_existing, df_new


def _latest_wave_in_table(schema: str, table: str) -> int | None:
    try:
        df = devo.read_sql(f"SELECT MAX(wave) AS max_wave FROM {schema}.{table}")
        devo.close()
        val = df["max_wave"].iloc[0]
        if pd.notna(val):
            latest = int(val)
            logger.info("Latest wave in %s.%s is %d", schema, table, latest)
            return latest
        logger.info("Latest wave in %s.%s is None (empty table).", schema, table)
        return None
    except Exception as e:
        logger.warning(
            "Could not read %s.%s (run data preparations): %s", schema, table, e
        )
        return None


def clear_cache_folder(wave: int) -> None:
    """Drop cached parquet snapshots that do not belong to the current wave."""
    if not CACHE_DIR.exists():
        logger.info("Cache folder %s does not exist; nothing to clear.", CACHE_DIR)
        return

    for file_path in CACHE_DIR.glob("*.parquet"):
        if str(wave) in file_path.name:
            continue
        try:
            file_path.unlink()
            logger.info("Deleted cache file: %s", file_path)
        except Exception as e:
            logger.warning("Could not delete cache file %s: %s", file_path, e)

# ---------------------------------
# PRODUCTION
# ---------------------------------
# USER SETTINGS
CONFIG_PATH = "scripts/config.yaml"
BACKUP = False  # Whether to create a backup of the existing DEVO table before overwriting
WAVE = 77 # e.g. 67 or None
WAVES = None # [37, 38, 39, 40, 41]  # e.g. [66, 67] or None
OVERWRITE = True
# EDP SPECIFICATIONS
MONTH = "2026_05"
WAVE_TO_EDP = 77  # NOTE: Add ONE WAVE, the one that will be appended to EDP dataset
PATH = str(OUTPUT_ROOT / MONTH / "ECB_Aggregates")
os.makedirs(PATH, exist_ok=True)  # Creating ECB_Aggregates
DISS_TIME = "26/06/2026;10:00"  # Select desired diss date and time


# 0) UPDATE INPUT DATA
## 0.0 Quick latest wave in table
clear_cache_folder(WAVE)
_latest_wave_in_table("lab_prj_ces_production", "core_super_view_agg")
_latest_wave_in_table("lab_prj_ces_production", "quarterly_super_view_agg")


## 0.1 Updating super view aggregate tables if needed:
### FIRST: Run MATLAB code for probin variables
run_data_preparatations_monthly()
run_data_preparations_quarterly()


# 1) RUNNING AGGREGATES
df_existing, df_new = run_pipeline(CONFIG_PATH, WAVE, WAVES)


# 2) SUMMARY OF UPLOAD PLAN
plan = summarize_upload_plan(df_existing, df_new, OVERWRITE)
logger.info("Upload plan: %s", plan)


# 3) IN DEPTH ANALYSIS
## 3.1 Inspecting all conflicts
conflict_keys = get_conflicting_keys(df_existing, df_new)
logger.info("Conflicting key rows: %d", len(conflict_keys))
conflict_rows = get_conflict_rows(df_existing, df_new)


## 3.2 Analising differences in conflicts
cols_to_compare = ["value", "sample_size", "population_size"]
conflict_compare = compare_conflicts(df_existing, df_new, cols_to_compare)
diff_counts = diff_counts_by_variable_multi(conflict_compare, metrics=cols_to_compare)
log_diff_counts_by_variable(diff_counts)

# Checking differences in values
conflict_compare_true = conflict_compare[(conflict_compare["value_changed"] == True) | 
                                         (conflict_compare["sample_size_changed"] == True) | 
                                         (conflict_compare["population_size_changed"] == True) ]
conflict_compare_true["value_diff_abs"].max()

# export comparisons to csv for further inspection if there are any
if len(conflict_compare_true) > 0:
    conflict_compare.to_csv(PATH + "/revisions_compare_all.csv", index=False)
    conflict_compare_true.to_csv(PATH + "/revisions_compare_conflicts.csv", index=False)

# 4) SECURE CONCATENATION
df_out = append_with_overwrite_safe(df_existing, df_new, OVERWRITE)
# In case you need to make 'breakdown_other' or 'qualitative_measure' a string/object type, run:
# df_new['qualitative_measure'] = df_new['qualitative_measure'].astype('string')
# [ ] Fix Null in flag_n

# to create a backup aggregates table if needed - before overwriting
if BACKUP:
    datalab = "prj_ces_production"
    table_name = "aggregates_backup_26"
    devo.create_table(df_existing, lab=f"lab_{datalab}", table_name=f"{table_name}",
                            path=table_storage_path(datalab, table_name), external=True)

# 5) UPLOAD
upload_table(df_out, "prj_ces_production", DST_TABLE)
logger.info("Upload completed (%d rows).", len(df_out))
df_out["wave"].max()

# ---------------------------------
# AGGREGATES INTERNAL CSV
# ---------------------------------

# USER SETTINGS
FILE_1 = "Aggregate_indicators_CES.csv"
df_aggregates = download_table("prj_ces_production", "aggregates_final", "all")
df_ces_internal = main_ces_internal_shape(df_aggregates)
df_ces_internal.to_csv(os.path.join(PATH, FILE_1), index=False)

# ---------------------------------
# AGGREGATES WEBSITE XLSX
# ---------------------------------
# USER SETTINGS
CONFIG_PATH = "scripts/config.yaml"
# FILE_OLD_NAME = "Aggregate_indicators_dissemination.xlsx"
FILE_2 = (
    "ecb.CES_aggregate_indicators.en.xlsx"  # NOTE: Naming convention for website upload
)

df_aggregates = download_table("prj_ces_production", "aggregates_final", "all")
df_ces_website = main_ces_website_shape(df_aggregates)
write_excel_by_topic(
    df_wide=df_ces_website,
    yaml_path=CONFIG_PATH,
    out_xlsx=os.path.join(PATH, FILE_2),
)

# ---------------------------------
# DASHBOARD INPUT CSV
# ---------------------------------
# USER SETTINGS
FILE_3 = "aggregate_indicators_db_long.csv"

df_agg_1 = download_table("prj_ces_production", "aggregates_final_ea6", "all")
df_agg_2 = download_table("prj_ces_production", "aggregates_final", "all")
df_agg_1 = df_agg_1[df_agg_1["wave"] < 28]
df_agg_1 = df_agg_1[
    ~(
        (df_agg_1["variable"].isin(["q2300", "q2350", "q2390"]))
        & (df_agg_1["wave"].isin([4, 7, 10]))
    )
]
df_agg_1["country"] = df_agg_1["country"].replace("EA6", "EA")
df_agg_2 = df_agg_2[df_agg_2["wave"] >= 28]

df_ces_dashboard = main_ces_db_shape(df_agg_1, df_agg_2)
df_ces_dashboard.to_csv(os.path.join(PATH, FILE_3), index=False)

# ---------------------------------
# EDP
# ---------------------------------
# USER SETTINGS
PATH_CES_CODELIST = str(CES_CODELIST_PATH)
REGISTRY = REGISTRY_ACC  # or REGISTRY_PROD. NOTE: Set environment from where CES_codelist is fetched

FILE_CSV = f"ces_aggregates_edp_w{WAVE_TO_EDP}.csv"
FILE_XML = f"ces_aggregates_edp_w{WAVE_TO_EDP}.csv.xml"
# FILE_CSV = "ces_aggregates_edp_ea6.csv"
# FILE_XML = "ces_aggregates_edp_ea6.csv.xml"

# 1 DOWNLOADING AGGREGATES
df_agg = download_table("prj_ces_production", "aggregates_final", "all", WAVE_TO_EDP)

# 2 EDP FORMAT TABLE
df_final = main_preparations_edp(
    df_agg, reg=REGISTRY, cache_xml=PATH_CES_CODELIST, cache_mode="refresh"
)
df_final.to_csv(os.path.join(PATH, FILE_CSV), index=False)

# 3 TRANSFORMING FILE CSV TO XML TYPE
file_to_read = os.path.join(PATH, FILE_CSV)
file_to_save = os.path.join(PATH, FILE_XML)
csv_delimiter = "comma"  # provide following options comma, tab, semicolon, space
structure_ref = "ECB:ECB_CES1"  # OPTIONAL: If using CSV this needs to be provided. Provide agency and DSD Id sepearated with a :, e.g. ECB:ECB_EXR1, empty string if not needed
transform_file(
    env="acc",
    read_file=file_to_read,
    save_file=file_to_save,
    csv_delimiter=csv_delimiter,
    structure=structure_ref,
)

# 4 UPDATE DESIRED RELEASE DATE AND TIME
dt_embargo = datetime.strptime(DISS_TIME, "%d/%m/%Y;%H:%M")
release_time = dt_embargo.strftime("%Y-%m-%dT%H:%M:%S")
update_release_time(file_to_save, release_time)

# 4 VALIDATING XML FILE
res = api_validation(
    path=os.path.join(PATH, FILE_XML),
    ignore_mandatory_att=True,
    print_json=False,
    print_output=True,
    env="acc",
)
print("There are errors: ", res)

# ---------->>> IF NO ERRORS THEN UPLOAD THE 'FILE_XML' TO THE DIRECT DATA
# DISSEMINATION TOOL (acceptance environment first, then production).


# 5 EXPORT CSV FOR SPACE PROVISION (DISS)
FILE_CSV_DEVO = f"ces_aggregates_edp_devo_w{WAVE_TO_EDP}.csv"
series_key_cols = ['FREQ', 'REF_AREA', 'CES_BREAKDOWN', 'CES_CUSTOM', 'CES_VARIABLE', 'CES_ANSWER', 'CES_DENOM']
df_final['SERIES_KEY'] = 'CES.' + df_final[series_key_cols].astype(str).agg('.'.join, axis=1)
df_final['OBS_DATE'] = df_final['TIME_PERIOD']

df_space = df_final[['SERIES_KEY', 'TIME_PERIOD', 'OBS_DATE', 'OBS_VALUE']]
df_space.to_csv(os.path.join(PATH, FILE_CSV_DEVO), index=False)


