# Neonatal Clinical Trials Explorer

This repository contains a small Python tool for exploring neonatal clinical
trials reported on ClinicalTrials.gov with yearly counts that factor in lead
sponsor type, overall status, conditions, intervention types, and study type
intervention/observational. It queries the ClinicalTrials.gov Data API and
aggregates results into a tidy summary table that can be exported as JSON or
CSV.

## Features

- Fetch neonatal-focused trials (default search term `neonatal`) from the
  ClinicalTrials.gov Data API.
- Aggregate trials by start year (or first posted year), lead sponsor class,
  overall status, conditions, intervention types (Drug, Procedure, etc.), and
  study type (Interventional vs. Observational).
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

## Use from R / RStudio

An R companion script (`neonatal_trials.R`) is included for users who prefer
RStudio. It mirrors the Python CLI behavior, returning a data frame of yearly
counts by sponsor class, status, condition grouping, intervention type, and
study type, or writing the summary to CSV.

Install the required R packages:

```r
install.packages(c("httr", "jsonlite"))
```

Load and run in RStudio:

```r
source("neonatal_trials.R")

# Fetch a data frame
summary_df <- summarize_neonatal_trials(start_year = 2010, end_year = 2024)
print(summary_df)

# Or write CSV output directly
summarize_neonatal_trials(start_year = 2010, end_year = 2024, output = "csv", file = "neonatal_counts.csv")
```

You can also run it non-interactively:

```bash
Rscript neonatal_trials.R --start-year 2010 --end-year 2024 --output csv --file neonatal_counts.csv
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

The output table includes these columns:

- `year`: parsed start/posting year
- `sponsor_class`: lead sponsor class (Industry, NIH, Other, Unknown)
- `status`: overall study status
- `study_type`: Interventional, Observational, etc.
- `intervention_type`: intervention category for the record (one row per type)
- `conditions`: semicolon-delimited condition list for the grouped row
- `count`: number of studies matching the combination

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
- `protocolSection.statusModule.overallStatus`
- `protocolSection.conditionsModule.conditions`
- `protocolSection.armsInterventionsModule.interventions`
- `protocolSection.designModule.studyType`

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
