"""Environment-specific configuration for the CES aggregates & variance pipeline.

This module is the single place where the pipeline learns about its environment:
object storage, network drives, log destinations and SDMX registry endpoints.

No infrastructure identifier is hard-coded in this repository. Every value below
is read from an environment variable at import time and falls back to a neutral
placeholder, so the code stays readable and importable outside the environment it
was written for. To run it for real, export the variables listed in
``.env.example`` (or set them in your shell profile / scheduler).

Paths inside the project are resolved relative to ``PROJECT_ROOT`` rather than to
a fixed drive letter, so the repository can be checked out anywhere.
"""

import os
from pathlib import Path

# Repository root - everything shipped with the code is located relative to this.
PROJECT_ROOT = Path(__file__).resolve().parent


def _env(name: str, default: str) -> str:
    """Read an environment variable, falling back to a placeholder."""
    return os.environ.get(name, default)


def _env_path(name: str, default: Path) -> Path:
    """Read a path from the environment, falling back to a project-relative default."""
    raw = os.environ.get(name)
    return Path(raw) if raw else default


# ---------------------------------------------------------------------------
# Object storage (external tables live as parquet under a bucket prefix)
# ---------------------------------------------------------------------------
STORAGE_BUCKET = _env("CES_STORAGE_BUCKET", "<storage-bucket>")
STORAGE_BUCKET_EDP = _env("CES_STORAGE_BUCKET_EDP", "<storage-bucket-edp>")


def table_storage_path(datalab: str, table_name: str, obj: str = "pq") -> str:
    """Return the object-store location backing an external table."""
    return f"s3a://{STORAGE_BUCKET}/{datalab}/db/{table_name}/{obj}"


# ---------------------------------------------------------------------------
# Filesystem locations (shared drives in the original deployment)
# ---------------------------------------------------------------------------
# Where the time-stamped run logs are written.
LOG_DIR = _env_path("CES_LOG_DIR", PROJECT_ROOT / "logs")

# Parquet snapshots of source tables, so a wave is downloaded only once.
CACHE_DIR = _env_path("CES_CACHE_DIR", PROJECT_ROOT / "cache")

# Root of the shared data-management folder that receives the dissemination
# outputs (internal CSV, website XLSX, dashboard CSV, SDMX files).
OUTPUT_ROOT = _env_path("CES_OUTPUT_ROOT", PROJECT_ROOT / "output")

# Folder where the MATLAB step drops the probabilistic-bin input files.
PROB_BINS_INPUT_DIR = _env_path("CES_PROB_BINS_INPUT_DIR", PROJECT_ROOT / "input" / "prob_bins")

# Archive of historical dissemination files kept outside the repository.
DISSEMINATION_ARCHIVE_DIR = _env_path(
    "CES_DISSEMINATION_ARCHIVE_DIR", PROJECT_ROOT / "input" / "archive"
)

# Cached copy of the CES SDMX codelist.
CES_CODELIST_PATH = _env_path(
    "CES_CODELIST_PATH", PROJECT_ROOT / "ces_edp" / "ces_codelist" / "ces_codelist.xml"
)

# Working folder for the EDP/SDMX transformation step.
EDP_WORK_DIR = _env_path("CES_EDP_WORK_DIR", PROJECT_ROOT / "output" / "edp")

# Reference data shipped with the repository.
TAGS_DIR = PROJECT_ROOT / "ces_edp" / "tags_edp"
CONFIG_PATH = PROJECT_ROOT / "scripts" / "config.yaml"


# ---------------------------------------------------------------------------
# SDMX registry & dissemination endpoints
# ---------------------------------------------------------------------------
# "acc" is the acceptance (pre-production) environment, "prod" the live one.
REGISTRY_ACC = _env("CES_REGISTRY_ACC", "https://<sdmx-registry-acc>/ws/public/sdmxapi/rest/")
REGISTRY_PROD = _env("CES_REGISTRY_PROD", "https://<sdmx-registry-prod>/ws/public/sdmxapi/rest/")

REGISTRY_HOST_ACC = _env("CES_REGISTRY_HOST_ACC", "https://<sdmx-registry-acc>")
REGISTRY_HOST_PROD = _env("CES_REGISTRY_HOST_PROD", "https://<sdmx-registry-prod>")


def registry(env: str) -> str:
    """Return the registry base URL for ``env`` ("acc" or "prod")."""
    return REGISTRY_HOST_ACC if env == "acc" else REGISTRY_HOST_PROD
