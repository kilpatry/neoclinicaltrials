# Neonatal Clinical Trials Explorer

This repository contains a small Python tool for exploring the number of
neonatal clinical trials reported on ClinicalTrials.gov by year and lead
sponsor type. It queries the ClinicalTrials.gov Data API and aggregates
results into a year-by-sponsor summary table that can be exported as JSON
or CSV.

## Features

- Fetch neonatal-focused trials (default search term `neonatal`) from the
  ClinicalTrials.gov Data API.
- Aggregate trials by start year (or first posted year) and lead sponsor
  class (e.g., Industry, NIH, Other).
- Export the aggregated counts as CSV or JSON for further analysis or
  visualization.

## Requirements

- Python 3.9+
- `requests` for HTTP calls
- `pandas` only if you want pretty data-frame style output (optional)

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Usage

Run the CLI with default parameters:

```bash
python neonatal_trials.py
```

Key options:

- `--start-year` / `--end-year`: limit the year range for aggregation.
- `--sponsor-field`: override the sponsor classification field if the API
  evolves (defaults to `sponsor_info.lead_sponsor_class`).
- `--output csv|json`: format of the summary output (printed to stdout).
- `--max-pages`: safety bound on how many pages to pull from the API
  (defaults to 30).

Example fetching studies first posted since 2010 and printing JSON:

```bash
python neonatal_trials.py --start-year 2010 --output json
```

If you prefer a CSV that can be saved to disk:

```bash
python neonatal_trials.py --output csv > neonatal_counts.csv
```

### API Notes

The script targets the ClinicalTrials.gov Data API documented at
<https://clinicaltrials.gov/data-api/api/>. If the API changes field names
or pagination tokens, adjust the constants at the top of
`neonatal_trials.py`. The defaults assume the following field paths exist
in the API response:

- `protocolSection.startDateStruct.startDate` (or
  `protocolSection.startDateStruct.date`)
- `protocolSection.firstPostDateStruct.firstPostDate`
- `sponsorInfo.leadSponsorClass`

The tool will fall back to alternate fields if these are missing.

## Development

To run the unit tests that validate aggregation logic:

```bash
pytest
```

Because outbound network access may be restricted in some environments,
the tests use synthetic API responses.
