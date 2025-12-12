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
        sponsor_field=nt.DEFAULT_SPONSOR_FIELD,
        status_field=nt.DEFAULT_STATUS_FIELD,
        condition_field=nt.DEFAULT_CONDITION_FIELD,
        intervention_field=nt.DEFAULT_INTERVENTION_FIELD,
        study_type_field=nt.DEFAULT_STUDY_TYPE_FIELD,
        date_fields=nt.DEFAULT_DATE_FIELDS,
    )

    assert record.year == 2020
    assert record.sponsor_class == "Industry"
    assert record.status == "Recruiting"
    assert set(record.conditions) == {"Condition A", "Condition B"}
    assert set(record.intervention_types) == {"Drug", "Procedure"}
    assert record.study_type == "Interventional"


def test_summarize_and_rows_shape():
    records = [
        nt.TrialRecord(
            year=2020,
            sponsor_class="Industry",
            status="Recruiting",
            conditions=["Condition A"],
            intervention_types=["Drug"],
            study_type="Interventional",
        ),
        nt.TrialRecord(
            year=2020,
            sponsor_class="Other",
            status="Completed",
            conditions=["Condition B"],
            intervention_types=["Procedure"],
            study_type="Interventional",
        ),
        nt.TrialRecord(
            year=2021,
            sponsor_class="Industry",
            status="Recruiting",
            conditions=["Condition A"],
            intervention_types=["Drug"],
            study_type="Interventional",
        ),
        nt.TrialRecord(
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
    assert rows[0]["count"] == 1

    assert rows[1]["year"] == 2020
    assert rows[1]["sponsor_class"] == "Other"
    assert rows[1]["status"] == "Completed"
    assert rows[1]["intervention_type"] == "Procedure"
    assert rows[1]["conditions"] == "Condition B"

    assert rows[2]["year"] == 2021
    assert rows[2]["sponsor_class"] == "Industry"
    assert rows[2]["count"] == 1
