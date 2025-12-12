# Neonatal clinical trials summarizer for R / RStudio
#
# This script mirrors the behavior of `neonatal_trials.py` in base R, using
# `httr` and `jsonlite` for HTTP and JSON handling. Load this file in RStudio
# and call `summarize_neonatal_trials()` to retrieve a data frame of yearly
# counts grouped by lead sponsor class.

API_BASE_URLS <- c(
  # Primary v2 endpoint
  "https://clinicaltrials.gov/api/v2/studies",
  # Classic hostname mirrors the same API
  "https://classic.clinicaltrials.gov/api/v2/studies",
  # Legacy data-api paths retained for compatibility
  "https://clinicaltrials.gov/data-api/api/studies",
  "https://clinicaltrials.gov/data-api/v2/studies"
)
DEFAULT_TERM <- "neonatal"
DEFAULT_SPONSOR_FIELD <- "sponsorInfo.leadSponsorClass"
DEFAULT_STATUS_FIELD <- "protocolSection.statusModule.overallStatus"
DEFAULT_CONDITION_FIELD <- "protocolSection.conditionsModule.conditions"
DEFAULT_INTERVENTION_FIELD <- "protocolSection.armsInterventionsModule.interventions"
DEFAULT_STUDY_TYPE_FIELD <- "protocolSection.designModule.studyType"
DEFAULT_DATE_FIELDS <- c(
  "protocolSection.startDateStruct.startDate",
  "protocolSection.startDateStruct.date",
  "protocolSection.startDateStruct.startDateDay",
  "protocolSection.firstPostDateStruct.firstPostDate"
)
DEFAULT_PAGE_SIZE <- 100

`%||%` <- function(lhs, rhs) {
  if (!is.null(lhs)) lhs else rhs
}

get_nested_field <- function(x, dotted_path) {
  parts <- strsplit(dotted_path, "\\.")[[1]]
  value <- x
  for (part in parts) {
    if (is.list(value) && !is.null(value[[part]])) {
      value <- value[[part]]
    } else {
      return(NULL)
    }
  }
  value
}

parse_year <- function(value) {
  if (is.null(value) || identical(value, NA)) return(NA_integer_)
  if (is.numeric(value)) return(as.integer(value))

  text <- as.character(value)
  formats <- c("%Y-%m-%d", "%Y-%m", "%Y")
  for (fmt in formats) {
    parsed <- try(as.integer(format(as.POSIXct(text, format = fmt), "%Y")), silent = TRUE)
    if (!inherits(parsed, "try-error") && !is.na(parsed)) {
      return(parsed)
    }
  }

  tokens <- strsplit(text, "-")[[1]]
  for (token in tokens) {
    if (nzchar(token) && nchar(token) == 4 && grepl("^\\d{4}$", token)) {
      return(as.integer(token))
    }
  }

  NA_integer_
}

extract_trial_record <- function(study,
                                sponsor_field,
                                status_field,
                                condition_field,
                                intervention_field,
                                study_type_field,
                                date_fields) {
  sponsor_class <- get_nested_field(study, sponsor_field) %||%
    get_nested_field(study, "sponsorInfo.leadSponsorClass") %||%
    get_nested_field(study, "sponsors.lead_sponsor_class") %||% "Unknown"

  status <- get_nested_field(study, status_field) %||%
    get_nested_field(study, "status.overallStatus") %||% "Unknown"

  conditions <- get_nested_field(study, condition_field) %||%
    get_nested_field(study, "conditions") %||% list()
  conditions <- as.character(unlist(conditions))

  interventions <- get_nested_field(study, intervention_field) %||% list()
  if (is.list(interventions) && length(interventions)) {
    intervention_types <- vapply(interventions, function(x) x[["type"]] %||% x, character(1))
  } else {
    intervention_types <- character()
  }

  study_type <- get_nested_field(study, study_type_field) %||%
    get_nested_field(study, "studyType") %||% "Unknown"

  year_value <- NA_integer_
  for (field in date_fields) {
    value <- get_nested_field(study, field)
    if (!is.null(value)) {
      candidate <- parse_year(value)
      if (!is.na(candidate)) {
        year_value <- candidate
        break
      }
    }
  }

  list(
    year = year_value,
    sponsor_class = as.character(sponsor_class),
    status = as.character(status),
    conditions = conditions[conditions != ""],
    intervention_types = as.character(intervention_types[intervention_types != ""]),
    study_type = as.character(study_type)
  )
}

fetch_trials <- function(term = DEFAULT_TERM,
                         sponsor_field = DEFAULT_SPONSOR_FIELD,
                         status_field = DEFAULT_STATUS_FIELD,
                         condition_field = DEFAULT_CONDITION_FIELD,
                         intervention_field = DEFAULT_INTERVENTION_FIELD,
                         study_type_field = DEFAULT_STUDY_TYPE_FIELD,
                         date_fields = DEFAULT_DATE_FIELDS,
                         base_urls = API_BASE_URLS,
                         page_size = DEFAULT_PAGE_SIZE,
                         max_pages = 30) {
  requireNamespace("httr", quietly = TRUE)
  requireNamespace("jsonlite", quietly = TRUE)

  params <- list(
    "query.term" = term,
    fields = paste(c(date_fields, sponsor_field, status_field, condition_field,
                     intervention_field, study_type_field), collapse = ","),
    pageSize = page_size,
    format = "json"
  )

  records <- list()
  page_token <- NULL
  base_candidates <- base_urls
  active_base <- NULL
  errors <- character()

  for (i in seq_len(max_pages)) {
    paged_params <- params
    if (!is.null(page_token)) {
      paged_params$pageToken <- page_token
    }

    resp <- NULL
    parsed <- NULL

    for (base in base_candidates) {
      attempt <- tryCatch({
        candidate_resp <- httr::GET(
          base,
          query = paged_params,
          httr::timeout(30),
          httr::accept_json(),
          httr::user_agent("neonatal-trials-r/1.0")
        )
        httr::stop_for_status(candidate_resp)

        content_type <- httr::http_type(candidate_resp)
        payload <- httr::content(candidate_resp, as = "text", encoding = "UTF-8")
        if (!grepl("json", content_type, ignore.case = TRUE)) {
          preview <- substr(payload, 1, 200)
          stop(sprintf(
            "ClinicalTrials.gov API returned non-JSON content (type: %s, status: %s). Response preview: %s",
            content_type,
            httr::status_code(candidate_resp),
            preview
          ))
        }

        candidate_parsed <- tryCatch(
          jsonlite::fromJSON(payload, simplifyVector = FALSE),
          error = function(e) {
            stop(sprintf(
              "Unable to parse ClinicalTrials.gov response as JSON (status: %s). First 200 characters: %s",
              httr::status_code(candidate_resp),
              substr(payload, 1, 200)
            ))
          }
        )

        list(resp = candidate_resp, parsed = candidate_parsed)
      }, error = function(e) {
        errors <<- c(errors, sprintf("%s: %s", base, conditionMessage(e)))
        NULL
      })

      if (!is.null(attempt)) {
        resp <- attempt$resp
        parsed <- attempt$parsed
        active_base <- base
        break
      }
    }

    if (is.null(resp) || is.null(parsed)) {
      stop(sprintf(
        paste(
          "Unable to retrieve JSON from ClinicalTrials.gov API after trying all base URLs.",
          "Checked: %s. If you are behind a corporate proxy or network filter, try a VPN",
          "or override the base URLs passed to fetch_trials()."
        ),
        paste(errors, collapse = "; ")
      ))
    }

    if (!is.null(active_base)) {
      base_candidates <- c(active_base, setdiff(base_candidates, active_base))
    }

    studies <- parsed$studies %||% parsed$results %||% list()
    records <- c(records, lapply(studies, extract_trial_record,
                                 sponsor_field = sponsor_field,
                                 status_field = status_field,
                                 condition_field = condition_field,
                                 intervention_field = intervention_field,
                                 study_type_field = study_type_field,
                                 date_fields = date_fields))

    page_token <- parsed$nextPageToken %||% parsed$next_page_token
    if (is.null(page_token)) break
  }

  records
}

summarize_trials <- function(records, start_year = NULL, end_year = NULL) {
  if (!length(records)) return(data.frame())

  rows <- list()

  for (rec in records) {
    if (is.null(rec$year) || is.na(rec$year)) next
    if (!is.null(start_year) && rec$year < start_year) next
    if (!is.null(end_year) && rec$year > end_year) next

    intervention_types <- if (length(rec$intervention_types)) rec$intervention_types else "None specified"
    conditions_key <- if (length(rec$conditions)) paste(sort(unique(rec$conditions)), collapse = "; ") else "Unspecified"

    for (intervention in intervention_types) {
      rows[[length(rows) + 1]] <- data.frame(
        year = as.integer(rec$year),
        sponsor_class = rec$sponsor_class,
        status = rec$status,
        study_type = rec$study_type,
        intervention_type = intervention,
        conditions = conditions_key,
        count = 1,
        check.names = FALSE,
        stringsAsFactors = FALSE
      )
    }
  }

  if (!length(rows)) return(data.frame())

  df <- do.call(rbind, rows)
  aggregate(
    count ~ year + sponsor_class + status + study_type + intervention_type + conditions,
    data = df,
    FUN = sum
  )
}

summarize_neonatal_trials <- function(term = DEFAULT_TERM,
                                      sponsor_field = DEFAULT_SPONSOR_FIELD,
                                      status_field = DEFAULT_STATUS_FIELD,
                                      condition_field = DEFAULT_CONDITION_FIELD,
                                      intervention_field = DEFAULT_INTERVENTION_FIELD,
                                      study_type_field = DEFAULT_STUDY_TYPE_FIELD,
                                      start_year = NULL,
                                      end_year = NULL,
                                      base_urls = API_BASE_URLS,
                                      page_size = DEFAULT_PAGE_SIZE,
                                      max_pages = 30,
                                      output = c("data.frame", "csv"),
                                      file = "") {
  output <- match.arg(output)
  records <- fetch_trials(term = term,
                          sponsor_field = sponsor_field,
                          status_field = status_field,
                          condition_field = condition_field,
                          intervention_field = intervention_field,
                          study_type_field = study_type_field,
                          base_urls = base_urls,
                          date_fields = DEFAULT_DATE_FIELDS,
                          page_size = page_size,
                          max_pages = max_pages)

  summary <- summarize_trials(records, start_year = start_year, end_year = end_year)

  if (output == "csv") {
    utils::write.csv(summary, file = file, row.names = FALSE)
    invisible(summary)
  } else {
    summary
  }
}

if (identical(environmentName(environment()), "R_GlobalEnv") && !interactive()) {
  args <- commandArgs(trailingOnly = TRUE)
  term <- DEFAULT_TERM
  start_year <- NULL
  end_year <- NULL
  sponsor_field <- DEFAULT_SPONSOR_FIELD
  output <- "data.frame"
  outfile <- ""
  base_urls <- API_BASE_URLS

  parse_arg <- function(flag) {
    idx <- which(args == flag)
    if (length(idx) && idx < length(args)) args[[idx + 1]] else NULL
  }

  term <- parse_arg("--term") %||% term
  sponsor_field <- parse_arg("--sponsor-field") %||% sponsor_field
  base_urls_arg <- parse_arg("--base-url")
  if (!is.null(base_urls_arg)) {
    base_urls <- strsplit(base_urls_arg, ",")[[1]]
  }
  start_year <- as.integer(parse_arg("--start-year"))
  end_year <- as.integer(parse_arg("--end-year"))
  output <- parse_arg("--output") %||% output
  outfile <- parse_arg("--file") %||% outfile

  result <- summarize_neonatal_trials(
    term = term,
    sponsor_field = sponsor_field,
    start_year = start_year,
    end_year = end_year,
    base_urls = base_urls,
    output = output,
    file = outfile
  )

  if (output != "csv") {
    print(result)
  }
}
