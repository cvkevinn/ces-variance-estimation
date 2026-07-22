# Sample data

These files are **50-row extracts** kept only so the SDMX/EDP code in `ces_edp/`
can be read and understood without access to the source systems. They are not
used by the production pipeline.

Every row is aggregate-level, carries `CONF_STATUS = F` ("free", i.e.
non-confidential in the SDMX confidentiality codelist) and corresponds to
statistics the ECB publishes openly.

## Where the full data comes from

The complete series are **not** redistributed here. Download them from the
official source:

- ECB Data Portal — <https://data.ecb.europa.eu/data/datasets>
- Consumer Expectations Survey — <https://www.ecb.europa.eu/stats/ecb_surveys/consumer_exp_survey/html/index.en.html>

`ces_edp/tags_edp.py` expects the full export saved as `ces_edp/tags_edp/data.csv`
(git-ignored). See that script's `__main__` block.

## Files

| File | Extract of |
|---|---|
| `ces_aggregates_edp.sample.csv` | EDP submission file, EA countries |
| `ces_aggregates_edp_ea6.sample.csv` | EDP submission file, EA6 historical aggregate |
| `tags_data.sample.csv` | Data Portal export used to build the EDP topic tags |
