"""
CLI tool for summarizing neonatal clinical trials by year, lead sponsor class,
overall status, conditions, intervention types, and study type using the
ClinicalTrials.gov Data API.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Sequence

if TYPE_CHECKING:
    import requests

API_BASE_URLS = [
    # Primary v2 endpoint
    "https://clinicaltrials.gov/api/v2/studies",
    # Classic hostname mirrors the same API
    "https://classic.clinicaltrials.gov/api/v2/studies",
    # Legacy data-api paths retained for compatibility
    "https://clinicaltrials.gov/data-api/api/studies",
    "https://clinicaltrials.gov/data-api/v2/studies",
]
DEFAULT_TERM = "neonatal OR neonate OR newborn OR preterm OR premature infant"
DEFAULT_NEONATAL_KEYWORDS = (
    "neonatal",
    "neonate",
    "newborn",
    "nicu",
    "preterm",
    "premature",
    "very low birth weight",
    "infant",
)
DEFAULT_SPONSOR_FIELD = "sponsorInfo.leadSponsorClass"
DEFAULT_STATUS_FIELD = "protocolSection.statusModule.overallStatus"
DEFAULT_CONDITION_FIELD = "protocolSection.conditionsModule.conditions"
DEFAULT_INTERVENTION_FIELD = "protocolSection.armsInterventionsModule.interventions"
DEFAULT_STUDY_TYPE_FIELD = "protocolSection.designModule.studyType"
DEFAULT_NCT_FIELD = "protocolSection.identificationModule.nctId"
DEFAULT_TITLE_FIELDS = (
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.identificationModule.officialTitle",
    "protocolSection.descriptionModule.briefSummary",
)
DEFAULT_MIN_AGE_FIELD = "protocolSection.eligibilityModule.minimumAge"
DEFAULT_MAX_AGE_FIELD = "protocolSection.eligibilityModule.maximumAge"
DEFAULT_DATE_FIELDS = (
    # Common v2 start date locations
    "protocolSection.startModule.startDateStruct.date",
    "protocolSection.startModule.startDateStruct.startDate",
    "protocolSection.startModule.startDateStruct.startDateDay",
    # Historic or alternative placements kept for compatibility
    "protocolSection.startDateStruct.startDate",
    "protocolSection.startDateStruct.date",
    "protocolSection.startDateStruct.startDateDay",
    # Posted/first-post fallbacks
    "protocolSection.statusModule.studyFirstPostDateStruct.date",
    "protocolSection.statusModule.studyFirstPostDateStruct.studyFirstPostDate",
    "protocolSection.firstPostDateStruct.firstPostDate",
)
MAX_NEONATAL_AGE_DAYS = 90
DEFAULT_PAGE_SIZE = 100


@dataclass
class TrialRecord:
    nct_id: str
    title: str
    year: Optional[int]
    sponsor_class: str
    status: str
    conditions: List[str]
    intervention_types: List[str]
    study_type: str


class ClinicalTrialsClient:
    """Minimal client for the ClinicalTrials.gov Data API."""

    def __init__(
        self,
        base_url: str | Sequence[str] = API_BASE_URLS,
        session: Optional["requests.Session"] = None,
    ):
        self.base_urls: List[str] = list(base_url) if isinstance(base_url, Sequence) else [base_url]
        self.base_urls = [url.rstrip("/") for url in self.base_urls]
        self._active_base: Optional[str] = None
        self.session = session

    def fetch_trials(
        self,
        term: str = DEFAULT_TERM,
        sponsor_field: str = DEFAULT_SPONSOR_FIELD,
        status_field: str = DEFAULT_STATUS_FIELD,
        condition_field: str = DEFAULT_CONDITION_FIELD,
        intervention_field: str = DEFAULT_INTERVENTION_FIELD,
        study_type_field: str = DEFAULT_STUDY_TYPE_FIELD,
        date_fields: Iterable[str] = DEFAULT_DATE_FIELDS,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: Optional[int] = None,
        title_fields: Iterable[str] = DEFAULT_TITLE_FIELDS,
        nct_field: str = DEFAULT_NCT_FIELD,
        min_age_field: str = DEFAULT_MIN_AGE_FIELD,
        max_age_field: str = DEFAULT_MAX_AGE_FIELD,
        neonatal_keywords: Iterable[str] = DEFAULT_NEONATAL_KEYWORDS,
        apply_filter: bool = True,
    ) -> List[TrialRecord]:
        """Fetch trials matching the term and return simplified records."""

        http = self.session
        if http is None:
            import requests

            http = requests.Session()

        field_list = [
            *date_fields,
            sponsor_field,
            status_field,
            condition_field,
            intervention_field,
            study_type_field,
            nct_field,
            *title_fields,
            min_age_field,
            max_age_field,
        ]

        params_v2: Dict[str, Any] = {
            "query.term": term,
            "fields": ",".join(field_list),
            "pageSize": page_size,
            "format": "json",
        }
        params_legacy: Dict[str, Any] = {
            "expr": term,
            "fields": ",".join(field_list),
            "pageSize": page_size,
            "format": "json",
        }

        json_payload: Dict[str, Any] = {
            "query": {"term": term},
            "fields": field_list,
            "pageSize": page_size,
            "format": "json",
        }

        records: List[TrialRecord] = []
        seen_ids: set[str] = set()
        page_token: Optional[str] = None
        seen_tokens: set[str] = set()

        pages_fetched = 0
        while True:
            paged_params_v2 = dict(params_v2)
            paged_params_legacy = dict(params_legacy)
            paged_json = dict(json_payload)
            paged_json["query"] = dict(json_payload.get("query", {}))
            if page_token:
                paged_params_v2["pageToken"] = page_token
                paged_params_legacy["pageToken"] = page_token
                paged_json["pageToken"] = page_token

            response, base_used = self._request_with_fallback(
                http, paged_params_v2, paged_params_legacy, paged_json
            )
            self._active_base = base_used

            content_type = response.headers.get("Content-Type", "")
            text_payload = response.text

            try:
                payload = response.json()
            except ValueError as exc:  # JSONDecodeError is a subclass
                preview = text_payload[:200]
                raise ValueError(
                    f"Unable to parse ClinicalTrials.gov response as JSON (status: {response.status_code}). First 200 characters: {preview}"
                ) from exc

            studies = payload.get("studies") or payload.get("results") or []
            for study in studies:
                if apply_filter:
                    if not self._is_neonatal_study(
                        study,
                        condition_field=condition_field,
                        title_fields=title_fields,
                        min_age_field=min_age_field,
                        max_age_field=max_age_field,
                        keywords=neonatal_keywords,
                    ):
                        continue

                record = self._extract_trial_record(
                    study,
                    nct_field=nct_field,
                    title_fields=title_fields,
                    sponsor_field=sponsor_field,
                    status_field=status_field,
                    condition_field=condition_field,
                    intervention_field=intervention_field,
                    study_type_field=study_type_field,
                    date_fields=date_fields,
                )

                record_id = record.nct_id
                if record_id and record_id != "Unknown":
                    if record_id in seen_ids:
                        continue
                    seen_ids.add(record_id)

                records.append(record)

            page_token = payload.get("nextPageToken") or payload.get("next_page_token")
            if page_token:
                if page_token in seen_tokens:
                    break
                seen_tokens.add(page_token)
            pages_fetched += 1
            if not page_token:
                break
            if max_pages is not None and pages_fetched >= max_pages:
                break

        return records

    def _request_with_fallback(
        self,
        http: "requests.Session",
        params_v2: Dict[str, Any],
        params_legacy: Dict[str, Any],
        json_payload: Dict[str, Any],
    ) -> tuple["requests.Response", str]:
        errors: List[str] = []
        base_candidates = []
        if self._active_base:
            base_candidates.append(self._active_base)
        base_candidates.extend([url for url in self.base_urls if url != self._active_base])

        for base in base_candidates:
            if base is None:
                continue
            methods: List[str] = []
            is_v2 = "/api/v2/" in base
            if is_v2:
                methods.append("POST")
            methods.append("GET")

            for method in methods:
                try:
                    headers = {
                        "Accept": "application/json",
                        "User-Agent": "neonatal-trials-py/1.0",
                    }

                    if method == "POST":
                        response = http.post(
                            base,
                            json=json_payload,
                            timeout=30,
                            headers=headers,
                        )
                    else:
                        params = params_v2 if is_v2 else params_legacy
                        response = http.get(
                            base,
                            params=params,
                            timeout=30,
                            headers=headers,
                        )

                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "")
                    if "json" not in content_type.lower():
                        preview = response.text[:200]
                        raise ValueError(
                            "ClinicalTrials.gov API returned non-JSON content "
                            f"(type: {content_type}, status: {response.status_code}). "
                            f"Response preview: {preview}"
                        )
                    return response, base
                except Exception as exc:  # noqa: BLE001
                    preview = ""
                    if hasattr(exc, "response") and getattr(exc, "response") is not None:
                        preview = getattr(exc.response, "text", "")[:200]
                        status = exc.response.status_code
                        errors.append(f"{base} ({method}): {exc} (status {status}). {preview}")
                    else:
                        errors.append(f"{base} ({method}): {exc}")

        details = "; ".join(errors)
        raise RuntimeError(
            "Unable to retrieve JSON from ClinicalTrials.gov API after trying all base URLs. "
            f"Checked: {details}. If you are behind a corporate proxy or network filter, try a VPN "
            "or adjust the base URL with the --base-url flag."
        )

    def _extract_trial_record(
        self,
        study: Dict[str, Any],
        nct_field: str,
        title_fields: Iterable[str],
        sponsor_field: str,
        status_field: str,
        condition_field: str,
        intervention_field: str,
        study_type_field: str,
        date_fields: Iterable[str],
    ) -> TrialRecord:
        nct_id = str(
            self._get_nested_field(study, nct_field)
            or self._get_nested_field(study, "protocolSection.identificationModule.nctId")
            or self._get_nested_field(study, "protocolSection.identificationModule.nctIdNumber")
            or "Unknown"
        )

        title_value = None
        for field in title_fields:
            title_value = self._get_nested_field(study, field)
            if title_value:
                break

        sponsor_class = (
            self._get_nested_field(study, sponsor_field)
            or self._get_nested_field(study, "sponsorInfo.leadSponsorClass")
            or self._get_nested_field(study, "sponsors.lead_sponsor_class")
            or "Unknown"
        )

        status = (
            self._get_nested_field(study, status_field)
            or self._get_nested_field(study, "status.overallStatus")
            or "Unknown"
        )

        conditions = self._normalize_to_list(
            self._get_nested_field(study, condition_field)
            or self._get_nested_field(study, "conditions")
            or []
        )

        intervention_entries = self._get_nested_field(study, intervention_field) or []
        if isinstance(intervention_entries, list):
            intervention_types = [
                str(item.get("type", item)) for item in intervention_entries if item
            ]
        elif isinstance(intervention_entries, dict):
            intervention_types = [str(intervention_entries.get("type"))]
        else:
            intervention_types = []

        study_type = (
            self._get_nested_field(study, study_type_field)
            or self._get_nested_field(study, "studyType")
            or "Unknown"
        )

        year_value = None
        for field in date_fields:
            value = self._get_nested_field(study, field)
            if value:
                year_value = self._parse_year(value)
                if year_value:
                    break

        return TrialRecord(
            nct_id=nct_id,
            title=str(title_value or ""),
            year=year_value,
            sponsor_class=str(sponsor_class),
            status=str(status),
            conditions=[str(c) for c in conditions if c],
            intervention_types=[str(t) for t in intervention_types if t],
            study_type=str(study_type),
        )

    @staticmethod
    def _parse_year(value: Any) -> Optional[int]:
        if isinstance(value, int):
            return value
        if not value:
            return None

        text = str(value)
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(text[: len(fmt)], fmt).year
            except ValueError:
                continue

        # Fallback: grab first four digits
        for token in text.split("-"):
            if token.isdigit() and len(token) == 4:
                return int(token)
        return None

    @staticmethod
    def _parse_age_to_days(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, dict):
            number = value.get("value")
            unit = value.get("unit")
            if number is None or unit is None:
                return None
            return ClinicalTrialsClient._age_to_days(str(number), str(unit))

        text = str(value).strip().lower()
        if not text or text in {"n/a", "none"}:
            return None

        parts = text.split()
        if not parts:
            return None
        number = parts[0].rstrip("+")
        unit = parts[1] if len(parts) > 1 else "days"
        return ClinicalTrialsClient._age_to_days(number, unit)

    @staticmethod
    def _age_to_days(number_text: str, unit: str) -> Optional[int]:
        try:
            number = float(number_text)
        except ValueError:
            return None

        unit = unit.lower()
        if unit.startswith("day"):
            return int(number)
        if unit.startswith("week"):
            return int(number * 7)
        if unit.startswith("month"):
            return int(number * 30.44)
        if unit.startswith("year"):
            return int(number * 365)
        return None

    def _is_neonatal_study(
        self,
        study: Dict[str, Any],
        *,
        condition_field: str,
        title_fields: Iterable[str],
        min_age_field: str,
        max_age_field: str,
        keywords: Iterable[str],
    ) -> bool:
        keywords_lc = [k.lower() for k in keywords]

        text_candidates: List[str] = []
        conditions = self._normalize_to_list(self._get_nested_field(study, condition_field) or [])
        text_candidates.extend([str(c).lower() for c in conditions])

        for field in title_fields:
            title = self._get_nested_field(study, field)
            if title:
                text_candidates.append(str(title).lower())

        if any(any(keyword in text for keyword in keywords_lc) for text in text_candidates):
            return True

        min_age_days = self._parse_age_to_days(self._get_nested_field(study, min_age_field))
        max_age_days = self._parse_age_to_days(self._get_nested_field(study, max_age_field))

        if max_age_days is not None and max_age_days <= MAX_NEONATAL_AGE_DAYS:
            return True
        if min_age_days is not None and min_age_days <= MAX_NEONATAL_AGE_DAYS:
            return True

        if min_age_days is not None and min_age_days > MAX_NEONATAL_AGE_DAYS * 4:
            return False
        if max_age_days is not None and max_age_days > MAX_NEONATAL_AGE_DAYS * 12 and (
            min_age_days is None or min_age_days > MAX_NEONATAL_AGE_DAYS * 2
        ):
            return False

        return True

    @staticmethod
    def _get_nested_field(data: Dict[str, Any], dotted_path: str) -> Any:
        value = data
        for part in dotted_path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value

    @staticmethod
    def _normalize_to_list(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]


def summarize_trials(
    records: Iterable[TrialRecord], start_year: Optional[int] = None, end_year: Optional[int] = None
) -> Dict[tuple, Dict[str, Any]]:
    """Aggregate trials by year, sponsor, status, intervention type, and study type."""

    summary: Dict[tuple, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "nct_ids": set(), "titles": set()}
    )

    for record in records:
        if record.year is None:
            continue
        if start_year and record.year < start_year:
            continue
        if end_year and record.year > end_year:
            continue

        intervention_types = record.intervention_types or ["None specified"]
        conditions_key = "; ".join(sorted(set(record.conditions))) if record.conditions else "Unspecified"

        for intervention_type in intervention_types:
            key = (
                record.year,
                record.sponsor_class,
                record.status,
                record.study_type,
                intervention_type,
                conditions_key,
            )
            summary[key]["count"] += 1
            summary[key]["nct_ids"].add(record.nct_id)
            if record.title:
                summary[key]["titles"].add(record.title)

    return summary


def records_to_rows(
    records: Iterable[TrialRecord],
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Convert trial records to a flat list of per-study rows."""

    rows: List[Dict[str, Any]] = []
    for record in records:
        if (start_year or end_year) and record.year is None:
            continue
        if record.year is not None:
            if start_year and record.year < start_year:
                continue
            if end_year and record.year > end_year:
                continue

        rows.append(
            {
                "nct_id": record.nct_id,
                "title": record.title,
                "year": record.year,
                "sponsor_class": record.sponsor_class,
                "status": record.status,
                "study_type": record.study_type,
                "intervention_types": "; ".join(sorted(set(record.intervention_types)))
                if record.intervention_types
                else "",
                "conditions": "; ".join(sorted(set(record.conditions))) if record.conditions else "",
            }
        )

    rows.sort(
        key=lambda r: (
            r.get("year") if r.get("year") is not None else 0,
            r.get("sponsor_class", ""),
            r.get("status", ""),
            r.get("nct_id", ""),
        )
    )
    return rows


def summary_to_rows(summary: Dict[tuple, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for key, payload in summary.items():
        year, sponsor, status, study_type, intervention_type, conditions = key
        rows.append(
            {
                "year": year,
                "sponsor_class": sponsor,
                "status": status,
                "study_type": study_type,
                "intervention_type": intervention_type,
                "conditions": conditions,
                "nct_ids": "; ".join(sorted(payload["nct_ids"])) if payload["nct_ids"] else "",
                "titles": "; ".join(sorted(payload["titles"])) if payload["titles"] else "",
                "count": payload["count"],
            }
        )

    rows.sort(
        key=lambda r: (
            r["year"],
            r["sponsor_class"],
            r["status"],
            r["study_type"],
            r["intervention_type"],
            r["conditions"],
        )
    )
    return rows


def write_csv(rows: List[Dict[str, Any]], output_file) -> None:
    if not rows:
        return

    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(output_file, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


def write_json(rows: List[Dict[str, Any]], output_file) -> None:
    json.dump(rows, output_file, indent=2)
    output_file.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize neonatal clinical trials with sponsor, status, condition, intervention type, and study type"
    )
    parser.add_argument("--term", default=DEFAULT_TERM, help="Search term for the API query (default: neonatal)")
    parser.add_argument("--start-year", type=int, help="Earliest year to include")
    parser.add_argument("--end-year", type=int, help="Latest year to include")
    parser.add_argument(
        "--sponsor-field",
        default=DEFAULT_SPONSOR_FIELD,
        help="Field path for sponsor class within the API response",
    )
    parser.add_argument(
        "--output",
        choices=["csv", "json"],
        default="csv",
        help="Output format printed to stdout",
    )
    parser.add_argument(
        "--mode",
        choices=["records", "summary"],
        default="records",
        help="Return individual trial rows (records) or aggregated counts (summary)",
    )
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Page size for API pagination")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Maximum number of pages to fetch (0 = fetch all pages until exhausted)",
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help=(
            "Disable neonatal keyword/age filtering. Enabled by default to keep the results neonatal-focused."
        ),
    )
    parser.add_argument(
        "--base-url",
        action="append",
        help=(
            "Override the ClinicalTrials.gov API base URL. Can be passed multiple times to define an ordered fallback list."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = ClinicalTrialsClient(base_url=args.base_url or API_BASE_URLS)
    records = client.fetch_trials(
        term=args.term,
        sponsor_field=args.sponsor_field,
        page_size=args.page_size,
        max_pages=args.max_pages or None,
        apply_filter=not args.no_filter,
    )

    if args.mode == "summary":
        summary = summarize_trials(records, start_year=args.start_year, end_year=args.end_year)
        rows = summary_to_rows(summary)
    else:
        rows = records_to_rows(records, start_year=args.start_year, end_year=args.end_year)

    if args.output == "json":
        write_json(rows, output_file=sys.stdout)
    else:
        write_csv(rows, output_file=sys.stdout)


if __name__ == "__main__":
    main()
