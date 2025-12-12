import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import neonatal_trials as nt


def test_parse_year_handles_common_formats():
    assert nt.ClinicalTrialsClient._parse_year("2024-05-01") == 2024
    assert nt.ClinicalTrialsClient._parse_year("2019-07") == 2019
    assert nt.ClinicalTrialsClient._parse_year("2015") == 2015
    assert nt.ClinicalTrialsClient._parse_year(2010) == 2010


def test_extract_trial_record_prefers_requested_fields():
    client = nt.ClinicalTrialsClient()
    study = {
        "protocolSection": {
            "startDateStruct": {
                "startDate": "2020-01-15",
                "date": "2020-01-15",
                "startDateDay": "2020-01-15",
            }
        },
        "sponsorInfo": {"leadSponsorClass": "Industry"},
    }

    record = client._extract_trial_record(
        study,
        sponsor_field="sponsorInfo.leadSponsorClass",
        date_fields=nt.DEFAULT_DATE_FIELDS,
    )

    assert record.year == 2020
    assert record.sponsor_class == "Industry"


def test_summarize_and_rows_shape():
    records = [
        nt.TrialRecord(year=2020, sponsor_class="Industry"),
        nt.TrialRecord(year=2020, sponsor_class="Other"),
        nt.TrialRecord(year=2021, sponsor_class="Industry"),
        nt.TrialRecord(year=None, sponsor_class="Unknown"),
    ]

    summary = nt.summarize_by_year_and_sponsor(records, start_year=2020, end_year=2021)
    rows = nt.summary_to_rows(summary)

    assert rows[0]["year"] == 2020
    assert rows[0]["Industry"] == 1
    assert rows[0]["Other"] == 1
    assert rows[1]["year"] == 2021
    assert rows[1]["Industry"] == 1
    assert rows[1]["Other"] == 0
    assert all("Unknown" not in row for row in rows)
