EA_MAP = {"EA6": "Z17", "EA": "Z18", "EL": "GR"}

AGE_MAP = {
    1: "AGE_18_34",
    2: "AGE_35_54",
    3: "AGE_55_70",
    4: "AGE_70+",
}
INCOME_MAP = {
    1: "INC_Q_1",
    2: "INC_Q_2",
    3: "INC_Q_3",
    4: "INC_Q_4",
    5: "INC_Q_5",
}

QUALITATIVE_MAP = {
    "down": "DEC",
    "shrink": "DEC",
    "easier": "DEC",
    "up": "INC",
    "grow": "INC",
    "harder": "INC",
    "same": "UNCH",
    "netdiff": "NB",
    "no": "NO",
    "yes": "YES",
    "notapplicable": "NA",
}

INDICATOR_MAP = {
    "mean_w": "WA",
    "median": "WM",
    "expectations_med": "WM",
    "expectations_p25": "WP25",
    "expectations_p75": "WP75",
    "uncertainty_med": "WM",
    "share": "WS",
    "sample_size": "UN",
    "population_size": "WN",
}

# Namespaces
NS = {
    "mes": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
    "str": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
    "com": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
}

# SDMX registry endpoints. Configured via the environment - see settings.py
# and .env.example - so that no host names are hard-coded in this repository.
from settings import REGISTRY_ACC, REGISTRY_PROD  # noqa: F401  (re-exported)
