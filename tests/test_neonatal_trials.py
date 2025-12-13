import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import json

import neonatal_trials as nt


def test_parse_year_handles_common_formats():
    assert nt.ClinicalTrialsClient._parse_year("2024-05-01") == 2024
    assert nt.ClinicalTrialsClient._parse_year("2019-07") == 2019
    assert nt.ClinicalTrialsClient._parse_year("2015") == 2015
    assert nt.ClinicalTrialsClient._parse_year(2010) == 2010


def test_parse_age_to_days_covers_common_units():
    assert nt.ClinicalTrialsClient._parse_age_to_days({"value": 4, "unit": "Weeks"}) == 28
    assert nt.ClinicalTrialsClient._parse_age_to_days("28 Days") == 28
    assert nt.ClinicalTrialsClient._parse_age_to_days("1 Month") == 30
    assert nt.ClinicalTrialsClient._parse_age_to_days("1 Year") == 365
    assert nt.ClinicalTrialsClient._parse_age_to_days("N/A") is None


def test_extract_trial_record_prefers_requested_fields():
    client = nt.ClinicalTrialsClient()
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Trial A"},
            "startDateStruct": {
                "startDate": "2020-01-15",
                "date": "2020-01-15",
                "startDateDay": "2020-01-15",
            },
            "statusModule": {"overallStatus": "Recruiting"},
            "conditionsModule": {"conditions": ["Condition A", "Condition B"]},
            "armsInterventionsModule": {
                "interventions": [
                    {"type": "Drug", "name": "Drug A"},
                    {"type": "Procedure", "name": "Procedure A"},
                ]
            },
            "designModule": {"studyType": "Interventional"},
        },
        "sponsorInfo": {"leadSponsorClass": "Industry"},
    }

    record = client._extract_trial_record(
        study,
        nct_field=nt.DEFAULT_NCT_FIELD,
        title_fields=nt.DEFAULT_TITLE_FIELDS,
        sponsor_field=nt.DEFAULT_SPONSOR_FIELD,
        status_field=nt.DEFAULT_STATUS_FIELD,
        condition_field=nt.DEFAULT_CONDITION_FIELD,
        intervention_field=nt.DEFAULT_INTERVENTION_FIELD,
        study_type_field=nt.DEFAULT_STUDY_TYPE_FIELD,
        date_fields=nt.DEFAULT_DATE_FIELDS,
    )

    assert record.nct_id == "NCT00000001"
    assert record.title == "Trial A"
    assert record.year == 2020
    assert record.sponsor_class == "Industry"
    assert record.status == "Recruiting"
    assert set(record.conditions) == {"Condition A", "Condition B"}
    assert set(record.intervention_types) == {"Drug", "Procedure"}
    assert record.study_type == "Interventional"


def test_is_neonatal_study_matches_keywords_and_age_filters():
    client = nt.ClinicalTrialsClient()
    study_with_keyword = {
        "protocolSection": {
            "conditionsModule": {"conditions": ["Neonatal sepsis"]},
            "eligibilityModule": {"maximumAge": "2 Months"},
        }
    }

    assert client._is_neonatal_study(
        study_with_keyword,
        condition_field=nt.DEFAULT_CONDITION_FIELD,
        title_fields=nt.DEFAULT_TITLE_FIELDS,
        min_age_field=nt.DEFAULT_MIN_AGE_FIELD,
        max_age_field=nt.DEFAULT_MAX_AGE_FIELD,
        keywords=nt.DEFAULT_NEONATAL_KEYWORDS,
    )

    adult_study = {
        "protocolSection": {
            "conditionsModule": {"conditions": ["Hypertension"]},
            "identificationModule": {"briefTitle": "Adult blood pressure study"},
            "eligibilityModule": {"minimumAge": "18 Years", "maximumAge": "65 Years"},
        }
    }

    assert not client._is_neonatal_study(
        adult_study,
        condition_field=nt.DEFAULT_CONDITION_FIELD,
        title_fields=nt.DEFAULT_TITLE_FIELDS,
        min_age_field=nt.DEFAULT_MIN_AGE_FIELD,
        max_age_field=nt.DEFAULT_MAX_AGE_FIELD,
        keywords=nt.DEFAULT_NEONATAL_KEYWORDS,
    )


def test_is_neonatal_study_allows_when_no_signal_but_rejects_clear_adults():
    client = nt.ClinicalTrialsClient()

    missing_fields = {"protocolSection": {"identificationModule": {"briefTitle": "Untitled"}}}
    assert client._is_neonatal_study(
        missing_fields,
        condition_field=nt.DEFAULT_CONDITION_FIELD,
        title_fields=nt.DEFAULT_TITLE_FIELDS,
        min_age_field=nt.DEFAULT_MIN_AGE_FIELD,
        max_age_field=nt.DEFAULT_MAX_AGE_FIELD,
        keywords=nt.DEFAULT_NEONATAL_KEYWORDS,
    )

    geriatric = {
        "protocolSection": {
            "eligibilityModule": {
                "minimumAge": "65 Years",
                "maximumAge": "99 Years",
            }
        }
    }
    assert not client._is_neonatal_study(
        geriatric,
        condition_field=nt.DEFAULT_CONDITION_FIELD,
        title_fields=nt.DEFAULT_TITLE_FIELDS,
        min_age_field=nt.DEFAULT_MIN_AGE_FIELD,
        max_age_field=nt.DEFAULT_MAX_AGE_FIELD,
        keywords=nt.DEFAULT_NEONATAL_KEYWORDS,
    )


def test_summarize_and_rows_shape():
    records = [
        nt.TrialRecord(
            nct_id="NCT1",
            title="Title 1",
            year=2020,
            sponsor_class="Industry",
            status="Recruiting",
            conditions=["Condition A"],
            intervention_types=["Drug"],
            study_type="Interventional",
        ),
        nt.TrialRecord(
            nct_id="NCT2",
            title="Title 2",
            year=2020,
            sponsor_class="Other",
            status="Completed",
            conditions=["Condition B"],
            intervention_types=["Procedure"],
            study_type="Interventional",
        ),
        nt.TrialRecord(
            nct_id="NCT3",
            title="Title 1",
            year=2021,
            sponsor_class="Industry",
            status="Recruiting",
            conditions=["Condition A"],
            intervention_types=["Drug"],
            study_type="Interventional",
        ),
        nt.TrialRecord(
            nct_id="NCTX",
            title="",
            year=None,
            sponsor_class="Unknown",
            status="Unknown",
            conditions=[],
            intervention_types=[],
            study_type="Unknown",
        ),
    ]

    summary = nt.summarize_trials(records, start_year=2020, end_year=2021)
    rows = nt.summary_to_rows(summary)

    assert rows[0]["year"] == 2020
    assert rows[0]["sponsor_class"] == "Industry"
    assert rows[0]["status"] == "Recruiting"
    assert rows[0]["intervention_type"] == "Drug"
    assert rows[0]["conditions"] == "Condition A"
    assert rows[0]["nct_ids"] == "NCT1"
    assert rows[0]["titles"] == "Title 1"
    assert rows[0]["count"] == 1

    assert rows[1]["year"] == 2020
    assert rows[1]["sponsor_class"] == "Other"
    assert rows[1]["status"] == "Completed"
    assert rows[1]["intervention_type"] == "Procedure"
    assert rows[1]["conditions"] == "Condition B"

    assert rows[2]["year"] == 2021
    assert rows[2]["sponsor_class"] == "Industry"
    assert rows[2]["count"] == 1


def test_records_to_rows_returns_flat_trials():
    records = [
        nt.TrialRecord(
            nct_id="NCT1",
            title="Title 1",
            year=2020,
            sponsor_class="Industry",
            status="Recruiting",
            conditions=["Condition A"],
            intervention_types=["Drug"],
            study_type="Interventional",
        ),
        nt.TrialRecord(
            nct_id="NCT2",
            title="Title 2",
            year=None,
            sponsor_class="Other",
            status="Completed",
            conditions=[],
            intervention_types=[],
            study_type="Observational",
        ),
    ]

    rows = nt.records_to_rows(records, start_year=2020, end_year=2020)
    assert len(rows) == 1
    assert rows[0]["nct_id"] == "NCT1"
    assert rows[0]["title"] == "Title 1"
    assert rows[0]["year"] == 2020


def test_fetch_trials_deduplicates_by_nct_and_filters_by_default():
    payload_calls = []

    class FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload
            self.headers = {"Content-Type": "application/json"}
            self.status_code = 200
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    def fake_request(self, http, params):
        payload_calls.append(params)
        payload = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCTDUPE",
                            "briefTitle": "Neonatal sepsis study",
                        },
                        "conditionsModule": {"conditions": ["Neonatal sepsis"]},
                        "designModule": {"studyType": "Interventional"},
                        "statusModule": {"overallStatus": "Recruiting"},
                        "startDateStruct": {"startDate": "2020-01-01"},
                        "armsInterventionsModule": {
                            "interventions": [{"type": "Drug", "name": "Drug A"}]
                        },
                        "eligibilityModule": {"maximumAge": "1 Month"},
                    },
                    "sponsorInfo": {"leadSponsorClass": "Industry"},
                },
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCTDUPE",
                            "briefTitle": "Neonatal sepsis study duplicate",
                        },
                        "conditionsModule": {"conditions": ["Neonatal sepsis"]},
                        "designModule": {"studyType": "Interventional"},
                        "statusModule": {"overallStatus": "Recruiting"},
                        "startDateStruct": {"startDate": "2020-01-01"},
                        "armsInterventionsModule": {
                            "interventions": [{"type": "Drug", "name": "Drug A"}]
                        },
                        "eligibilityModule": {"maximumAge": "1 Month"},
                    },
                    "sponsorInfo": {"leadSponsorClass": "Industry"},
                },
                {
                    "protocolSection": {
                        "identificationModule": {"nctId": "NCTADULT"},
                        "conditionsModule": {"conditions": ["Hypertension"]},
                        "eligibilityModule": {"minimumAge": "18 Years"},
                    }
                },
            ]
        }
        return FakeResponse(payload), "https://example.com"

    client = nt.ClinicalTrialsClient(base_url=["https://example.com"])
    original = nt.ClinicalTrialsClient._request_with_fallback
    nt.ClinicalTrialsClient._request_with_fallback = fake_request
    try:
        records = client.fetch_trials(max_pages=1)
    finally:
        nt.ClinicalTrialsClient._request_with_fallback = original

    assert len(records) == 1
    assert records[0].nct_id == "NCTDUPE"
    assert records[0].title.startswith("Neonatal sepsis")
