import logging
import pandas as pd
from data_preparations._tools_data_prep import (
    # download_core_superview,
    download_table,
    upload_table,
    merge_variable_versions,
    drop_old_versions,
    calculate_q2300_derived,
    calculate_q2350_derived,
    calculate_q2390_derived,
    calculate_q4010_derived,
)

logger = logging.getLogger(__name__)

## INFLATION VARIABLES
quant_inf = []
quali_inf = []

## LABOUR ECONOMICS AND ECONOMIC GROWTH VARIABLES
quant_labor_econgrowth = [
    "q2300",
    "q2302",
    "q2350",
    "q2352",
    "q2390",
    "q2391",
    "q2392",
    "q2393",
    "q2394",
]
quali_labor_econgrowth = []

## INCOME AND CONSUMPTION VARIABLES
quant_income_consumption = []
quali_income_consumption = []

## HOUSING AND CREDIT ACCESS VARIABLES

quant_house_credit = [
    "q4010_1",
    "q4010_2",
    "q4010_3",
    "q4010_4",
    "q4010_5",
    "q4010_6",
    "q4010_7",
    "q4010_8",
    "q4010_9",
    "q4011_1",
    "q4011_2",
    "q4011_3",
    "q4011_4",
    "q4011_5",
    "q4011_6",
    "q4011_7",
    "q4011_8",
    "q4011_9",
]
quali_house_credit = []

"""
ALL VARIABLES TO DOWNLOAD
"""
all_variables = (
    quant_inf
    + quali_inf
    + quant_labor_econgrowth
    + quali_labor_econgrowth
    + quant_income_consumption
    + quali_income_consumption
    + quant_house_credit
    + quali_house_credit
)


"""
MAP HERE VARIABLES WITH DIFFERENT VERSIONS
"""
variables_several_versions = {
    "q2300_rec": ["q2300", "q2302"],  # q2301, q2303  quant_labor
    "q2350_rec": ["q2350", "q2352"],  # , q2353   quant_labor
    "q2390_rec": ["q2390", "q2391", "q2392", "q2393", "q2394"],  # quant_labor
    "q4010_1_rec": ["q4010_1", "q4011_1"],
    "q4010_2_rec": ["q4010_2", "q4011_2"],
    "q4010_3_rec": ["q4010_3", "q4011_3"],
    "q4010_4_rec": ["q4010_4", "q4011_4"],
    "q4010_5_rec": ["q4010_5", "q4011_5"],
    "q4010_6_rec": ["q4010_6", "q4011_6"],
    "q4010_7_rec": ["q4010_7", "q4011_7"],
    "q4010_8_rec": ["q4010_8", "q4011_8"],
    "q4010_9_rec": ["q4010_9", "q4011_9"],
}


def main():
    # 1 DOWNLOADING DATA
    ## Quarterly table
    all_variables.extend(["survey_status", "wgt_bld_q", "wgt_calib_q"])
    df_q = download_table("prj_ces", "quarterly", all_variables)
    df_q_valid = df_q[df_q["survey_status"] == 1]

    ## Base variable "b7040_imp_quintiles_q"
    df_1 = download_table(
        "prj_ces", "quarterly_hhincome_stat", ["b7040_imp_quintiles_q"]
    )
    df_q_valid = pd.merge(df_q_valid, df_1, on=["a0010", "a0020", "a0030"], how="left")

    ## Base variable "pr2010"
    df_2 = download_table("prj_ces", "recruitment", ["pr2010"])
    df_2.drop(columns="a0030", inplace=True)
    df_q_valid = pd.merge(df_q_valid, df_2, on=["a0010", "a0020"], how="left")

    ## Base variable "a1110_calib_rec_q"
    df_3 = download_table("prj_ces", "quarterly_derived", ["a1110_calib_rec_q"])
    df_q_valid = pd.merge(df_q_valid, df_3, on=["a0010", "a0020", "a0030"], how="left")

    # 2 DATA TRANSFORMATION
    logger.info("Transforming variables for 'quarterly_super_view_agg'")
    ## 2.1 MERGING DIFERENT VERSIONS INTO 1
    df_raw = merge_variable_versions(df_q_valid, variables_several_versions)
    df_raw = drop_old_versions(df_raw, variables_several_versions)

    ## 2.2 SPECIFIC TRANSFORMATIONS
    df_raw = calculate_q2300_derived(df_raw)
    df_raw = calculate_q2350_derived(df_raw)
    df_raw = calculate_q2390_derived(df_raw)
    df_raw = calculate_q4010_derived(df_raw)

    # 3 RENAMING: SO THAT AGGREGATES PIPELINES READS CORRECTLY
    # base variables coming from quarterly table
    df_raw_final = df_raw.rename(
        columns={
            "a0030": "wave",
            "b7040_imp_quintiles_q": "b7040_imp_quintiles",
            "a1110_calib_rec_q": "a1110_calib_rec",
            "wgt_bld_q": "wgt_bld",
            "wgt_calib_q": "wgt_calib",
        }
    )
    # recoded variables
    df_raw_final = df_raw_final.rename(
        columns={
            "q2300_rec": "q2300",
            "q2350_rec": "q2350",
            "q2390_rec": "q2390",
            "q4010_rec": "q4010",
        }
    )

    # 4. UPLOAD
    max_wave = df_raw_final["wave"].max()
    logger.info("Latest wave of new table is %s", max_wave)
    upload_table(df_raw_final, "prj_ces_production", "quarterly_super_view_agg")


if __name__ == "__main__":
    main()
