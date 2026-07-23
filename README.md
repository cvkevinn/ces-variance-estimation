# CES Aggregates & Variance Pipeline

> ⚠️ **Data protection.** Code I developed at the **European Central Bank** on the
> Consumer Expectations Survey, published as a portfolio sample of my own work - not
> an official ECB product, not endorsed by the ECB. It contains **no microdata**, no
> credentials and no internal infrastructure details.
> [What exactly was removed, and what remains ↓](#data-protection)

This project calculates CES aggregates, their variance estimation and significance tests of changes, using the Rao-Wu bootstrap methodology.

This repository contains the Python code that:
1. computes monthly/quarterly CES indicators (quantitative, qualitative, prob-bin),
2. estimates variance and significance of indicator changes (with configurable correlation),
3. standardises the output layout for dissemination (internal CSV, website XLSX and dashboard),
4. prepares and validates SDMX files for EDP upload,
5. logs all steps to a central path.

The whole pipeline is **config-driven** via `scripts/config.yaml` and **orchestrated** via `main.py`.

---

## 1. Repository layout

```text
.
│   main.py                 # production orchestrator (run this)
│   settings.py             # environment config (paths, storage, endpoints)
│   .env.example            # environment variables to set, with placeholders
│   README.md
│   requirements.txt
│
├── cache/                  # parquet cache for downloaded source tables (git-ignored)
│
├── ces_edp/                # EDP/SDMX preparation layer
│   preparing_data.py
│   transform_sdmx_file.py
│   validate_file_with_fr.py
│   tags_edp.py
│   _constants.py
│   _get_codelists.py
│   _tools.py
│   sample_data/            # 50-row public extracts (see its README)
│
├── data_preparations/      # monthly/quarterly data preparation before running aggregates
│   monthly_data_prep.py
│   quarterly_data_prep.py
│   _tools_data_prep.py
│
├── others/                 # formats for other outputs: internal CSV, website XLSX, dashboard CSV
│   ces_dashboard.py
│   ces_internal.py
│   ces_website.py
│   _constants_mapping.py
│   _tools_others.py
│
└── scripts/                # core CES calculations
    calculations_1.py       
    calculations_2_fd.py    
    calculations_production.py
    config.yaml             # <-- main config for variables/breakdowns
    _adjust.py
    _boots.py
    _input.py
    _stats.py
    _stats_fd.py
    _tools.py              
    _upload.py
    _winsor.py
    __init__.py

```

---

## 2. Environment setup

Two layers of configuration:

* **`settings.py` + `.env.example`** — *where things live*: storage bucket, log and
  output directories, SDMX registry endpoints. All read from environment variables,
  all shipped as placeholders. Nothing is resolved against a fixed drive letter, so
  the repository can be checked out anywhere.
* **`scripts/config.yaml`** — *what gets computed* (see next section).

```bash
cp .env.example .env   # then fill in the values for your environment
```

## 3. Configuration (what gets computed)
The pipeline is driven by a single YAML:

```yaml
defaults:
  rep: 2
  fd_correlation: 0.8
``` 
* `rep` = number of bootstrap / replicate runs (used downstream in the variance calculation).

* `fd_correlation` = correlation to use in FD variance combination (0.8 by default).

Then the config is split by type of variable:

1. __quantitative__ – numeric variables (inflation expectations in % changes, income, housing, credit amounts…)

2. __qualitative__ – categorical questions that become shares (`up`, `down`, `same`, etc.)

3. __prob_bin__ – probabilistic bin expectations, derived from a base var (c1150) with suffixes such as `_imean_v2`, `_iqr_v2`.

Each block defines:

* a __default frequency__ (`M` or `Q`),

* a __default lag__ (usually `1` for M, `3` for Q),

* __default winsorisation__ behaviour,

* a list of __breakdowns__ (the pipeline computes each variable for each breakdown),

Example:
```yaml
quantitative: 
  frequency: "M"
  lag: 1
  winsorize_default: true
  breakdowns:
    - ["wave"]
    - ["wave", "a0020"]
    - ["wave", "a1110_calib_rec"]
    - ["wave", "b7040_imp_quintiles"]
  variables:
    - name: c1020
      topic: inflation
    - name: c6020
      topic: income_consumption
      winsorize: false

```

## 4. Core calculation flow
The heart of the repo is `scripts/calculations_production.py`. Pay attention to function `main()`:

1. **Read YAML** (`config_path`)

2. **Pre-warm cache**: figure out which columns (variables) we need per frequency/lag and download them once

3. **For each block** (`quantitative`, `qualitative`, `prob_bin`):

* download needed waves (also the lagged wave to compute FD)

* loop over **breakdowns**

* loop over **variables**

* call `calculations_1.main_calculations(...)` (aggregates)

* call `calculations_2_fd.main_calculations_fd(...)` (first differences statistics)

* merge both and **normalise layout** (add `country`, `breakdown_other`, `breakdown_other_categ`)

4. **Concatenate** all blocks into one final DataFrame

5. **Final cleanups**:

* add `flag_n` based on `sample_size` (`d` for <20, `u` for <50)

* add `n_replicates`

* ensure `date` column exists (from `wave_to_date`)

* drop temporary/unwanted indicators

* map indicators to final nomenclature (e.g. `mean` → `mean_w`)

That final DataFrame is what `main.py` later **compares** against the existing table, appends and uploads.

## 5. Orchestration (`main.py`)

Production script doing the following:

1. **Configure logging** to the directory given by `CES_LOG_DIR`:
```python
LOG_FILE = f"Aggregates_Variance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
configure_logging(str(LOG_DIR / LOG_FILE), overwrite=True)
logger = logging.getLogger(__name__)
```

So everything is written to a time-stamped log in the configured folder.

2. **Check latest wave** in source tables (`monthly_super_view_agg` & `quarterly_super_views`).

3. **Run data preparations** i.e., update source tables in 2. This ensures source tables contain newest wave:

```python 
run_data_preparatations_monthly()
run_data_preparations_quarterly()
```

4. **Run the pipeline** for one wave, multiple waves, or all waves:
```python
CONFIG_PATH = "scripts/config.yaml"
WAVE = 69
WAVES = None
df_existing, df_new = run_pipeline(CONFIG_PATH, WAVE, WAVES)

```

5. **Summarise upload plan** and **append safely**:

```python
plan = summarize_upload_plan(df_existing, df_new, OVERWRITE)
df_out = append_with_overwrite_safe(df_existing, df_new, OVERWRITE)
upload_table(df_out, "prj_ces_production", DST_TABLE)
```
6. **Produce dissemination formats**:

* Internal CSV: `Aggregate_indicators_CES.csv`

* Website XLSX: `Aggregate_indicators_dissemination.xlsx `

* Dashboard CSV (combining EA6 historical and EA11): `aggregate_indicators_db_long.csv`

* SDMX generation and validation for EDP Tool: `ces_aggregates_edp.csv.xml` 

## Important notes:

* `cache/` is used by `calculations_production.py` to store parquet snapshots of source tables so the same wave is not repeatedly downloaded. Hence, in case you want to download the same wave/waves (e.g., because of an update), delete the underlying cache file.

* When adding **new share indicators** (qualitative variables): add this calculations in `scripts/_input.py`. Additionally, you must specified their `suffix_schema` in `config.yaml`.

* For any other data derivation, add functions in `data_preparations/_tools_data_prep.py`.

* In case **tags file** needs to be updated, check code in `ces_edp/tags_edp.py`. Remember tags are needed for the EDP so that variables can be grouped by `Economics Topic`.

## Data protection

I developed this code while working in the European Central Bank, on the Consumer
Expectations Survey team. It is published here as a portfolio sample of my own work.
It is not an official ECB product, is not endorsed by the ECB, and any views it
reflects are my own.

Before publishing, the repository was deliberately sanitised. Concretely:

* **No microdata.** The pipeline operates only on aggregated statistics. No individual
  respondent record, identifier or response is present anywhere in this repository,
  and none can be reconstructed from it.
* **No confidential statistics.** The only data files included are three 50-row
  extracts under [`ces_edp/sample_data/`](ces_edp/sample_data/), kept so the SDMX code
  is readable. Every row carries `CONF_STATUS = F` ("free" in the SDMX confidentiality
  codelist) and corresponds to figures the ECB publishes openly on the
  [ECB Data Portal](https://data.ecb.europa.eu/data/datasets). The full series are
  **not** redistributed here - they are linked to at source.
* **No internal infrastructure details.** Object-store buckets, server and host names,
  network drives and mapped-drive paths have been removed and replaced by environment
  variables. See [`settings.py`](settings.py) and [`.env.example`](.env.example):
  every such value is a placeholder.
* **No credentials and no personal data.** There are no passwords, keys or tokens in
  the code (the original deployment authenticated via Kerberos/SSO), and no user
  names, e-mail addresses or personal paths.
* **Disclosure control is part of the pipeline itself.** Aggregates based on fewer
  than 20 observations are dropped before any output is produced, and a `flag_n`
  reliability marker is attached to small cells.

The pipeline cannot be executed outside the ECB environment: it depends on internal
connector libraries (`connectors`, `datalabtools`, `ecb-connectors`) and on source
tables that are not public. The code is published to be read, not run.

## Related links

- Original [paper on the Rao-Wu bootstrap methodology](https://www150.statcan.gc.ca/n1/en/catalogue/12-001-X199200214486)
- [ECB Consumer Expectations Survey](https://www.ecb.europa.eu/stats/ecb_surveys/consumer_exp_survey/html/index.en.html) — survey overview and methodology
- [ECB Data Portal](https://data.ecb.europa.eu/data/datasets) — the published aggregates this pipeline produces

The internal ECB methodological note on variance estimation is not linked here, as
it is not publicly accessible.
