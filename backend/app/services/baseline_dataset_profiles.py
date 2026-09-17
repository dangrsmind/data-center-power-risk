"""Local-file profiles for the existing CSV audit/candidate workflow. No network IO."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlsplit

from app.services.csv_dataset_importer import (
    NormalizedCsvRow, canonical_column, clean_text, normalize_epoch_row,
    normalize_fractracker_row, normalize_state, urls_from_values,
)


@dataclass(frozen=True)
class BaselineProfile:
    display_name: str
    filenames: tuple[str, ...]
    source_url: str | None
    citation: str
    license_note: str
    required_fields: tuple[str, ...] = ("name and at least one location field (facility rows only)",)
    optional_fields: tuple[str, ...] = ("operator", "owner", "developer", "city", "county", "state", "country", "address", "latitude", "longitude", "external_dataset_id", "lifecycle_state", "announced_date", "opening_date", "event_date", "load_mw", "it_power_mw", "water_use_mgd", "cooling", "cooling_type", "source_urls", "citation", "license_note", "notes")
    identity_fields: tuple[str, ...] = ("external_dataset_id", "name + state/country", "name + coordinates", "source_urls")
    candidate_rule: str = "Facility row, name and location, dataset provenance, no errors or duplicate ambiguity; needs_review only."
    provenance_rule: str = "Retain original row, source file/line, run UUID, dataset, citation, license note and normalized fields."


PROFILES = {
    "epoch_ai_data_centers": BaselineProfile(
        "Epoch AI — Frontier Data Centers",
        ("data_centers*.csv", "data_center_timelines*.csv", "data_center_chillers*.csv", "data_center_cooling_towers*.csv"),
        "https://epoch.ai/data/data-centers",
        "Epoch AI, ‘Frontier Data Centers’. Published online at epoch.ai. https://epoch.ai/data/data-centers",
        "CC BY 4.0; credit source and authors. Based on the manually supplied Epoch README; confirm terms for the imported version.",
    ),
    "fractracker_us_data_centers": BaselineProfile(
        "FracTracker — U.S. Data Centers Tracker", ("fractracker*.csv",), None,
        "FracTracker Alliance, U.S. Data Centers Tracker; manually supplied CSV export.",
        "License not supplied with this CSV. Confirm FracTracker usage and attribution terms before redistribution; no license inferred.",
    ),
}
# Ordered aliases; no geocoding, country inference, unit conversion or date inference.
FIELD_MAPPINGS = {
    "name": ("Name", "facility_name", "project name", "Data center"),
    "developer": ("Owner", "operator_name", "operator", "developer", "company"),
    "operator": ("operator_name", "operator"), "owner": ("Owner",),
    "city": ("city", "municipality"), "county": ("county",), "state": ("state",),
    "country": ("country",), "address": ("address", "street address"),
    "latitude": ("latitude", "lat"), "longitude": ("longitude", "long", "lon", "lng"),
    "external_dataset_id": ("id", "objectid", "dataset id", "facility id"),
    "lifecycle_state": ("status", "stage", "construction status"),
    "announced_date": ("announced date", "announcement date"),
    "opening_date": ("expected_date_online", "opening date", "online date"),
    "event_date": ("Date",),
    "load_mw": ("Current power (MW)", "Power (MW)", "mw", "load mw", "capacity mw"),
    "it_power_mw": ("IT power (MW)",), "water_use_mgd": ("Water use (MGD)",),
    "cooling": ("cooling_source", "cooling", "cooling type"),
    "cooling_type": ("cooling_type",), "notes": ("Notes", "other_info", "purpose"),
    "citation": ("citation",), "license_note": ("license", "license_note", "usage note"),
}


def row_kind(path: str) -> str:
    filename = Path(path).name.lower()
    if filename.startswith("data_center_timelines"):
        return "timeline"
    if filename.startswith(("data_center_chillers", "data_center_cooling_towers")):
        return "equipment_reference"
    return "data_center"


def public_url(value: str) -> bool:
    """Syntactic public HTTP reference check only; never resolve or fetch a URL."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"} or parsed.username or "." not in host:
            return False
        if host.endswith((".local", ".localhost", ".internal")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except ValueError:
        return False


def normalize_baseline_row(dataset: str, raw: dict, *, source_file: str,
                           import_run_id: str, source_url: str | None = None,
                           citation: str | None = None, license_note: str | None = None) -> NormalizedCsvRow:
    profile = PROFILES[dataset]
    # Reuse the existing CSV normalizers, then apply explicit baseline rules.
    normalize = normalize_epoch_row if dataset == "epoch_ai_data_centers" else normalize_fractracker_row
    row = normalize(raw, source_file=source_file, dataset_source=None)
    mapped = row.normalized
    lookup = {canonical_column(key): value for key, value in raw.items() if isinstance(key, str)}
    for field, aliases in FIELD_MAPPINGS.items():
        mapped[field] = next((clean_text(lookup.get(canonical_column(alias))) for alias in aliases if clean_text(lookup.get(canonical_column(alias)))), None)
    for field in ("latitude", "longitude", "load_mw", "it_power_mw", "water_use_mgd"):
        value = mapped[field]
        mapped[field] = None
        if value is None:
            continue
        text = value.replace(",", "")
        # Explicit units are accepted, ranges/annotations retained only in raw data.
        unit = "MW" if field in {"load_mw", "it_power_mw"} else "MGD" if field == "water_use_mgd" else ""
        suffix = rf"\s*(?:{unit})?" if unit else ""
        match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)" + suffix, text, re.IGNORECASE)
        number = float(match.group(1)) if match else None
        if number is None or not math.isfinite(number):
            row.warnings.append(f"unparsed_{field}: retained in original row")
        elif (field == "latitude" and abs(number) > 90) or (field == "longitude" and abs(number) > 180) or (field not in {"latitude", "longitude"} and number < 0):
            row.errors.append(f"invalid_{field}")
        else:
            mapped[field] = number
    mapped["state"] = normalize_state(mapped["state"])
    if (mapped["country"] or "").casefold() in {"usa", "us", "united states", "united states of america"}:
        mapped["country"] = "US"
    mapped["dataset_row_type"] = row_kind(source_file)
    # A dataset landing URL is provenance, never project-specific evidence.
    dataset_source = source_url or profile.source_url
    source_values = [value for key, value in raw.items() if isinstance(key, str) and any(token in canonical_column(key) for token in ("source", "url", "citation", "link", "website"))]
    row.source_urls = [url for url in urls_from_values(source_values) if public_url(url) and url.rstrip("/") != (dataset_source or "").rstrip("/")]
    row.dataset_name = dataset
    row.dataset_source = dataset_source
    mapped.update(dataset_name=dataset, dataset_source=dataset_source, dataset_display_name=profile.display_name,
                  import_run_id=import_run_id, import_kind="baseline_dataset_import", source_urls=row.source_urls,
                  citation=citation or mapped["citation"] or profile.citation,
                  license_note=license_note or mapped["license_note"] or profile.license_note)
    row.warnings = [warning for warning in row.warnings if warning not in {"missing_name", "missing_location", "missing_public_source_url"}]
    if not baseline_identity(mapped) and mapped["dataset_row_type"] == "data_center":
        row.errors.append("missing_identity: facility name and location required for candidates")
    if mapped["latitude"] is None or mapped["longitude"] is None:
        row.warnings.append("missing_coordinates")
    if not row.source_urls:
        row.warnings.append("missing_public_source_url: dataset provenance is not project evidence")
    if mapped["dataset_row_type"] != "data_center":
        row.warnings.append("supporting_row_audit_only_no_candidate")
    row.warnings.append("baseline_dataset_import_requires_analyst_review")
    mapped["row_fingerprint"] = fingerprint({"dataset": dataset, "kind": mapped["dataset_row_type"], "row": row.raw_row})
    return row


def baseline_identity(mapped: dict) -> bool:
    return bool(mapped.get("name") and (any(mapped.get(key) for key in ("state", "country", "address", "city", "county")) or (mapped.get("latitude") is not None and mapped.get("longitude") is not None)))


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def filename_warning(dataset: str, path: str) -> list[str]:
    return [] if any(fnmatch(Path(path).name.lower(), pattern) for pattern in PROFILES[dataset].filenames) else ["unexpected_filename: using selected dataset profile; inspect mappings before confirming"]
