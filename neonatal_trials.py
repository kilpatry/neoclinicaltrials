"""
CLI tool for summarizing neonatal clinical trials by year and lead sponsor class
using the ClinicalTrials.gov Data API.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

if TYPE_CHECKING:
    import requests

API_BASE_URL = "https://clinicaltrials.gov/data-api/api/studies"
DEFAULT_TERM = "neonatal"
DEFAULT_SPONSOR_FIELD = "sponsorInfo.leadSponsorClass"
DEFAULT_DATE_FIELDS = (
    "protocolSection.startDateStruct.startDate",
    "protocolSection.startDateStruct.date",
    "protocolSection.startDateStruct.startDateDay",
    "protocolSection.firstPostDateStruct.firstPostDate",
)
DEFAULT_PAGE_SIZE = 100


@dataclass
class TrialRecord:
    year: Optional[int]
    sponsor_class: str


class ClinicalTrialsClient:
    """Minimal client for the ClinicalTrials.gov Data API."""

    def __init__(self, base_url: str = API_BASE_URL, session: Optional["requests.Session"] = None):
        self.base_url = base_url.rstrip("/")
        self.session = session

    def fetch_trials(
        self,
        term: str = DEFAULT_TERM,
        sponsor_field: str = DEFAULT_SPONSOR_FIELD,
        date_fields: Iterable[str] = DEFAULT_DATE_FIELDS,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = 30,
    ) -> List[TrialRecord]:
        """Fetch trials matching the term and return simplified records."""

        import requests

        http = self.session or requests.Session()

        params: Dict[str, Any] = {
            "query.term": term,
            "fields": f"{','.join(date_fields)},{sponsor_field}",
            "pageSize": page_size,
        }

        records: List[TrialRecord] = []
        page_token: Optional[str] = None

        for _ in range(max_pages):
            paged_params = dict(params)
            if page_token:
                paged_params["pageToken"] = page_token

            response = http.get(self.base_url, params=paged_params, timeout=30)
            response.raise_for_status()
            payload = response.json()

            studies = payload.get("studies") or payload.get("results") or []
            for study in studies:
                records.append(
                    self._extract_trial_record(study, sponsor_field=sponsor_field, date_fields=date_fields)
                )

            page_token = payload.get("nextPageToken") or payload.get("next_page_token")
            if not page_token:
                break

        return records

    def _extract_trial_record(
        self, study: Dict[str, Any], sponsor_field: str, date_fields: Iterable[str]
    ) -> TrialRecord:
        sponsor_class = (
            self._get_nested_field(study, sponsor_field)
            or self._get_nested_field(study, "sponsorInfo.leadSponsorClass")
            or self._get_nested_field(study, "sponsors.lead_sponsor_class")
            or "Unknown"
        )

        year_value = None
        for field in date_fields:
            value = self._get_nested_field(study, field)
            if value:
                year_value = self._parse_year(value)
                if year_value:
                    break

        return TrialRecord(year=year_value, sponsor_class=str(sponsor_class))

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
    def _get_nested_field(data: Dict[str, Any], dotted_path: str) -> Any:
        value = data
        for part in dotted_path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value


def summarize_by_year_and_sponsor(
    records: Iterable[TrialRecord], start_year: Optional[int] = None, end_year: Optional[int] = None
) -> Dict[int, Dict[str, int]]:
    summary: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for record in records:
        if record.year is None:
            continue
        if start_year and record.year < start_year:
            continue
        if end_year and record.year > end_year:
            continue
        summary[record.year][record.sponsor_class] += 1

    return summary


def summary_to_rows(summary: Dict[int, Dict[str, int]]) -> List[Dict[str, Any]]:
    if not summary:
        return []

    sponsors = sorted({sponsor for year_counts in summary.values() for sponsor in year_counts})
    rows: List[Dict[str, Any]] = []
    for year in sorted(summary):
        base = {"year": year}
        for sponsor in sponsors:
            base[sponsor] = summary[year].get(sponsor, 0)
        rows.append(base)
    return rows


def write_csv(rows: List[Dict[str, Any]], output_file) -> None:
    if not rows:
        output_file.write("year\n")
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
    parser = argparse.ArgumentParser(description="Summarize neonatal clinical trials by year and sponsor class")
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
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Page size for API pagination")
    parser.add_argument("--max-pages", type=int, default=30, help="Maximum number of pages to fetch")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = ClinicalTrialsClient()
    records = client.fetch_trials(
        term=args.term,
        sponsor_field=args.sponsor_field,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )

    summary = summarize_by_year_and_sponsor(records, start_year=args.start_year, end_year=args.end_year)
    rows = summary_to_rows(summary)

    if args.output == "json":
        write_json(rows, output_file=sys.stdout)
    else:
        write_csv(rows, output_file=sys.stdout)


if __name__ == "__main__":
    main()
