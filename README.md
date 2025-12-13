# Neonatal Clinical Trials Explorer

This repository contains a small Python tool for exploring neonatal clinical
trials reported on ClinicalTrials.gov with the choice of returning individual
study rows or yearly counts that factor in lead sponsor type, overall status,
conditions, intervention types, and study type (intervention/observational).
It queries the ClinicalTrials.gov Data API and either returns a per-study data
frame or aggregates results into a tidy summary table that can be exported as
JSON or CSV. Trials are filtered client-side to stay neonatal-focused using a
broader set of search terms (neonate, newborn, preterm, etc.), study titles,
condition keywords, and age eligibility (preferring maximum age ≤ 90 days).
Client-side filtering is enabled by default to keep results neonatal-focused;
pass `--no-filter` (or `strict_filter = FALSE` in R) if you need to inspect the
broader set of studies returned by the API term alone.

## Features

- Fetch neonatal-focused trials (default search expression
  `neonatal OR neonate OR newborn OR preterm OR premature infant`) from the
  ClinicalTrials.gov Data API.
- Return a per-study data frame with NCT ID, title, year, sponsor class,
  status, study type, intervention types, and conditions.
- Aggregate trials by start year (or first posted year), lead sponsor class,
  overall status, conditions, intervention types (Drug, Procedure, etc.), and
  study type (Interventional vs. Observational) when you need grouped counts.
- Export either per-study rows or aggregated counts as CSV or JSON for further
  analysis or visualization.
- Deduplicate trials by NCT ID across pages to avoid repeated rows in the
  record-level output.

## Requirements

- Python 3.9+
- `requests` for HTTP calls
- `pandas` only if you want pretty data-frame style output (optional)

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Use from R / RStudio

An R companion script (`neonatal_trials.R`) is included for users who prefer
RStudio. It mirrors the Python CLI behavior, returning either per-study rows or
yearly counts by sponsor class, status, condition grouping, intervention type,
and study type, or writing the output to CSV.

Install the required R packages:

```r
install.packages(c("httr", "jsonlite"))
```

Load and run in RStudio:

```r
source("neonatal_trials.R")

# Fetch a per-study data frame (default)
records_df <- summarize_neonatal_trials(start_year = 2010, end_year = 2024)
print(records_df)

# Fetch the grouped summary instead
summary_df <- summarize_neonatal_trials(start_year = 2010, end_year = 2024, mode = "summary")
print(summary_df)

# Or write CSV output directly
summarize_neonatal_trials(start_year = 2010, end_year = 2024, output = "csv", file = "neonatal_counts.csv")
```

You can also run it non-interactively:

```bash
Rscript neonatal_trials.R --start-year 2010 --end-year 2024 --mode summary --output csv --file neonatal_counts.csv
```

## Usage

Run the CLI with default parameters:

```bash
python neonatal_trials.py
```

Key options:

- `--start-year` / `--end-year`: limit the year range for aggregation or
  filtering.
- `--sponsor-field`: override the sponsor classification field if the API
  evolves (defaults to `sponsor_info.lead_sponsor_class`).
- `--mode records|summary`: choose per-study rows (`records`, default) or
  grouped counts (`summary`).
- `--output csv|json`: format of the output (printed to stdout).
- `--max-pages`: safety bound on how many pages to pull from the API
  (defaults to 30).
- `--no-filter`: disable client-side keyword/age neonatal filtering (on by
  default to keep results neonatal-focused).

Example fetching per-study rows first posted since 2010 and printing JSON:

```bash
python neonatal_trials.py --start-year 2010 --output json --mode records
```

If you prefer a CSV that can be saved to disk:

```bash
python neonatal_trials.py --output csv --mode records > neonatal_records.csv
```

When `--mode summary` is used, the grouped output table includes these columns:

- `year`: parsed start/posting year
- `sponsor_class`: lead sponsor class (Industry, NIH, Other, Unknown)
- `status`: overall study status
- `study_type`: Interventional, Observational, etc.
- `intervention_type`: intervention category for the record (one row per type)
- `conditions`: semicolon-delimited condition list for the grouped row
- `nct_ids`: NCT identifiers represented in the grouped bucket
- `titles`: Study titles represented in the grouped bucket
- `count`: number of studies matching the combination

When `--mode records` is used (default), each row represents a single trial:

- `nct_id`: NCT number
- `title`: study title
- `year`: parsed start/posting year (if available)
- `sponsor_class`: lead sponsor class (Industry, NIH, Other, Unknown)
- `status`: overall study status
- `study_type`: Interventional, Observational, etc.
- `intervention_types`: semicolon-delimited intervention categories (if any)
- `conditions`: semicolon-delimited condition list

### API Notes

The script targets the ClinicalTrials.gov Data API documented at
<https://clinicaltrials.gov/data-api/api/>. If the API changes field names
or pagination tokens, adjust the constants at the top of
`neonatal_trials.py`. The defaults assume the following field paths exist
in the API response:

- `protocolSection.startModule.startDateStruct.date` (with fallbacks to
  `protocolSection.startDateStruct.startDate` and related fields)
- `protocolSection.statusModule.studyFirstPostDateStruct.date` (and legacy
  `protocolSection.firstPostDateStruct.firstPostDate`)
- `sponsorInfo.leadSponsorClass`
- `protocolSection.statusModule.overallStatus`
- `protocolSection.conditionsModule.conditions`
- `protocolSection.armsInterventionsModule.interventions`
- `protocolSection.designModule.studyType`
- `protocolSection.identificationModule.nctId`
- `protocolSection.identificationModule.briefTitle` (for neonatal keyword
  filtering)
- `protocolSection.eligibilityModule.minimumAge` / `.maximumAge` (for neonatal
  age filtering)

The tool will fall back to alternate fields if these are missing.

If you encounter an HTML response instead of JSON (common behind some
proxies), both the Python and R clients will automatically retry against
several base URLs (`https://clinicaltrials.gov/api/v2/studies`,
`https://classic.clinicaltrials.gov/api/v2/studies`, and legacy
`data-api` paths). Requests to the v2 endpoints use POST with explicit
JSON bodies to avoid HTTP 400 errors caused by malformed query strings.
You can supply your own base URLs to override this behavior:

```bash
python neonatal_trials.py --base-url https://your-proxy.example/api/studies
```

For R, pass a comma-delimited list if needed:

```r
summarize_neonatal_trials(base_urls = c(
  "https://clinicaltrials.gov/api/v2/studies",
  "https://classic.clinicaltrials.gov/api/v2/studies"
))
```

## Development

To run the unit tests that validate aggregation logic:

```bash
pytest
```

Because outbound network access may be restricted in some environments,
the tests use synthetic API responses.
