from __future__ import annotations
import os
import requests
import xml.etree.ElementTree as ET
from typing import Dict, Mapping, Optional, Literal
from ces_edp._constants import REGISTRY_ACC, REGISTRY_PROD, NS


# def fetch_dataflow_xml(
#     registry: str = REGISTRY_ACC,
#     survey: str = "CES",
#     version: str = "1.0",
#     references: str = "all",
#     cache_path: Optional[str] = None,
#     **request_kwargs,
# ) -> ET.Element:
#     """
#     Fetch SDMX Dataflow XML and return the XML root element.
#     - Minimal: no retries, no logging. One job: fetch (and optionally cache).
#     - Extra requests options (verify, headers, timeout, proxies...) via **request_kwargs.
#     """
#     # Load from cache if available
#     if cache_path and os.path.exists(cache_path):
#         with open(cache_path, "rb") as f:
#             return ET.fromstring(f.read())

#     url = f"{registry.rstrip('/')}/dataflow/ECB/{survey}/{version}?references={references}"
#     # Sensible default timeout unless caller overrides
#     request_kwargs.setdefault("timeout", 20)
#     resp = requests.get(url, **request_kwargs)
#     resp.raise_for_status()

#     if cache_path:
#         with open(cache_path, "wb") as f:
#             f.write(resp.content)

#     return ET.fromstring(resp.content)


def fetch_dataflow_xml(
    registry: str,
    survey: str = "CES",
    version: str = "1.0",
    references: str = "all",
    cache_path: Optional[str] = None,
    cache_mode: Literal["prefer", "refresh", "ignore", "only"] = "prefer",
    **request_kwargs,
) -> ET.Element:
    """Fetch SDMX Dataflow XML (optionally cached) and return the XML root.

    The function supports four cache policies via `cache_mode`:

      * "prefer" (default): read from `cache_path` if it exists; otherwise fetch
        from the network and write the response to `cache_path`.
      * "refresh": always fetch from the network and overwrite `cache_path`.
      * "ignore": always fetch from the network; do not read or write `cache_path`.
      * "only": read from `cache_path` only; raise FileNotFoundError if missing.

    Extra keyword arguments are forwarded to `requests.get`, e.g. `timeout=30`,
    `verify=...`, `headers={...}`, `proxies={...}`.

    Args:
      registry: Base SDMX registry URL (e.g., REGISTRY_ACC / REGISTRY_PROD).
      survey: SDMX survey identifier segment in the path.
      version: SDMX artefact version.
      references: SDMX `references` query parameter (e.g., "all").
      cache_path: Path to the on-disk XML cache file, or None.
      cache_mode: Cache policy: "prefer" | "refresh" | "ignore" | "only".
      **request_kwargs: Extra keyword args forwarded to `requests.get`.

    Returns:
      XML root element (`xml.etree.ElementTree.Element`).

    Raises:
      FileNotFoundError: If `cache_mode="only"` and `cache_path` is missing.
      requests.HTTPError: If the HTTP response is not 2xx.
      xml.etree.ElementTree.ParseError: If the XML cannot be parsed.
    """
    url = f"{registry.rstrip('/')}/dataflow/ECB/{survey}/{version}?references={references}"
    request_kwargs.setdefault("timeout", 20)

    # Read cache if allowed
    if cache_mode in ("prefer", "only") and cache_path and os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return ET.fromstring(f.read())

    if cache_mode == "only":
        raise FileNotFoundError(f"Cache not found: {cache_path}")

    # Fetch
    resp = requests.get(url, **request_kwargs)
    resp.raise_for_status()

    # Write cache if allowed
    if cache_path and cache_mode in ("prefer", "refresh"):
        with open(cache_path, "wb") as f:
            f.write(resp.content)

    return ET.fromstring(resp.content)


def parse_codelists_from_xml(
    xml_root: ET.Element, ns: Mapping[str, str] = NS
) -> Dict[str, Dict[str, str]]:
    """
    Parse codelists from SDMX XML Element → {codelist_id: {code_id: code_name}}.
    """
    codelists: Dict[str, Dict[str, str]] = {}
    for codelist_elem in xml_root.findall(".//str:Codelist", ns):
        cl_id = codelist_elem.get("id")
        if not cl_id:
            continue
        codes: Dict[str, str] = {}
        for code_elem in codelist_elem.findall(".//str:Code", ns):
            code_id = code_elem.get("id")
            if not code_id:
                continue
            name_elem = code_elem.find("com:Name", ns)
            codes[code_id] = (
                (name_elem.text or "").strip() if name_elem is not None else ""
            )
        codelists[cl_id] = codes
    return codelists


# def get_codelists(
#     registry: str = REGISTRY_ACC,
#     survey: str = "CES",
#     version: str = "1.0",
#     cache_xml: Optional[str] = None,
#     **request_kwargs,
# ) -> Dict[str, Dict[str, str]]:
#     """
#     Orchestrator: fetch XML → parse codelists. Still minimal.
#     Extra requests options via **request_kwargs (e.g., verify=ecb_certifi.where()).
#     """
#     xml_root = fetch_dataflow_xml(
#         registry=registry,
#         survey=survey,
#         version=version,
#         cache_path=cache_xml,
#         **request_kwargs,
#     )
#     return parse_codelists_from_xml(xml_root)


def get_codelists(
    registry: str = REGISTRY_ACC,
    survey: str = "CES",
    version: str = "1.0",
    cache_xml: Optional[str] = None,
    cache_mode: Literal["prefer", "refresh", "ignore", "only"] = "prefer",
    **request_kwargs,
) -> Dict[str, Dict[str, str]]:
    """Retrieve SDMX codelists as a nested dict (via XML fetch + parse).

    This orchestrates fetching the SDMX Structure XML (with caching) and parsing
    it into `{codelist_id: {code_id: code_name}}`.

    Args:
      registry: Base SDMX registry URL (e.g., REGISTRY_ACC / REGISTRY_PROD).
      survey: SDMX survey identifier segment in the path.
      version: SDMX artefact version.
      cache_xml: Optional path to the XML cache file.
      cache_mode: Cache policy for XML fetch: "prefer" | "refresh" | "ignore" | "only".
      **request_kwargs: Extra keyword args forwarded to `requests.get`.

    Returns:
      Dict mapping codelist IDs to dicts of `{code_id: code_name}`.

    Raises:
      FileNotFoundError: If `cache_mode="only"` and `cache_xml` is missing.
      requests.HTTPError: If the HTTP response is not 2xx (when fetching).
      xml.etree.ElementTree.ParseError: If the XML cannot be parsed.
    """

    xml_root = fetch_dataflow_xml(
        registry=registry,
        survey=survey,
        version=version,
        cache_path=cache_xml,
        cache_mode=cache_mode,
        **request_kwargs,
    )
    return parse_codelists_from_xml(xml_root)
