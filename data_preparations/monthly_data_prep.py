import logging
import pandas as pd
from data_preparations._tools_data_prep import (
    download_core_superview,
    merge_variable_versions,
    drop_old_versions,
    upload_table,
    calculate_c6020_derived,
    calculate_c6120_derived,
    get_latest_probin_table,
)

logger = logging.getLogger(__name__)

## INFLATION VARIABLES
quant_inf = ["c1020", "c1120", "c1220", "e2020"]
quali_inf = ["c1010", "c1110", "c1210", "e2010"]

## LABOUR ECONOMICS AND ECONOMIC GROWTH VARIABLES
quant_labor_econgrowth = ["c4020", "c4030", "c4031"]
quali_labor_econgrowth = ["c4010"]

## INCOME AND CONSUMPTION VARIABLES
quant_income_consumption = ["c3220", "c6020", "c6120", "c6030", "c6130"]
quali_income_consumption = ["c3210", "c6010", "c6110"]

## HOUSING AND CREDIT ACCESS VARIABLES
quant_house_credit = ["c2120", "c5111", "c5113"]
quali_house_credit = ["c2110", "c7110", "c7111", "c7120", "c7121"]

"""
PROBIN VARIABLES
"""
probin_variables = ["c1150"]

"""
ALL VARIABLES TO DOWNLOAD FROM CORE
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
    "c5111_rec": ["c5111", "c5113"],  # quant_house_credit
    "c7110_rec": ["c7110", "c7111"],  # quali_house_credit
    "c7120_rec": ["c7120", "c7121"],  # quali_house_credit
}


def main():
    # 1 DOWNLOADING DATA
    ## 1.1 CORE VARIABLES
    df_core = download_core_superview(varlist=all_variables, wave=None)
    df_core = df_core[~df_core["a0010"].isna()]
    df_core = df_core[df_core["survey_status"] == 1]

    ## 1.2 PROBIN VARIABLES
    df_prob = get_latest_probin_table()
    probin_vars = []
    for var in probin_variables:
        probin_vars.append(f"{var}_imean_v2")
        probin_vars.append(f"{var}_iqr_v2")
    probin_vars.append("a0010")
    probin_vars.append("wave_ces")
    df_prob = df_prob[probin_vars]
    df_prob["a0010"] = df_prob["a0010"].astype(str)
    df_prob.rename(columns={"wave_ces": "wave"}, inplace=True)

    ## 1.3 MERGING
    df_raw = pd.merge(df_core, df_prob, how="left", on=["a0010", "wave"])

    # 2 DATA TRANSFORMATION
    logger.info("Transforming variables for 'core_super_view_agg'")
    ## 2.1 MERGING DIFERENT VERSIONS INTO 1
    df_raw = merge_variable_versions(df_raw, variables_several_versions)
    df_raw = drop_old_versions(df_raw, variables_several_versions)

    ## 2.2 Editing consumption variables
    # perceptions
    df_raw = calculate_c6020_derived(df_raw)
    # expectations
    df_raw = calculate_c6120_derived(df_raw)

    # 3 RENAMING: SO THAT AGGREGATES PIPELINES READS CORRECTLY
    df_raw_final = df_raw.rename(
        columns={
            "c5111_rec": "c5111",
            "c7110_rec": "c7110",
            "c7120_rec": "c7120",
            "c6020_rec": "c6020",  # already winsorised
            "c6120_rec": "c6120",  # already winsorised
        },
    )

    # 4 UPLOAD
    max_wave = df_raw_final["wave"].max()
    logger.info("Latest wave of new table is %s", max_wave)
    upload_table(df_raw_final, "prj_ces_production", "core_super_view_agg")


if __name__ == "__main__":
    main()
