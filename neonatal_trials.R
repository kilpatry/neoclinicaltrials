# Neonatal clinical trials summarizer for R / RStudio
#
# This script mirrors the behavior of `neonatal_trials.py` in base R, using
# `httr` and `jsonlite` for HTTP and JSON handling. Load this file in RStudio
# and call `summarize_neonatal_trials()` to retrieve a data frame of yearly
# counts grouped by lead sponsor class.

API_BASE_URL <- "https://clinicaltrials.gov/data-api/api/studies"
DEFAULT_TERM <- "neonatal"
DEFAULT_SPONSOR_FIELD <- "sponsorInfo.leadSponsorClass"
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

extract_trial_record <- function(study, sponsor_field, date_fields) {
  sponsor_class <- get_nested_field(study, sponsor_field) %||%
    get_nested_field(study, "sponsorInfo.leadSponsorClass") %||%
    get_nested_field(study, "sponsors.lead_sponsor_class") %||% "Unknown"

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

  list(year = year_value, sponsor_class = as.character(sponsor_class))
}

fetch_trials <- function(term = DEFAULT_TERM,
                         sponsor_field = DEFAULT_SPONSOR_FIELD,
                         date_fields = DEFAULT_DATE_FIELDS,
                         page_size = DEFAULT_PAGE_SIZE,
                         max_pages = 30) {
  requireNamespace("httr", quietly = TRUE)
  requireNamespace("jsonlite", quietly = TRUE)

  params <- list(
    "query.term" = term,
    fields = paste(c(date_fields, sponsor_field), collapse = ","),
    pageSize = page_size
  )

  records <- list()
  page_token <- NULL

  for (i in seq_len(max_pages)) {
    paged_params <- params
    if (!is.null(page_token)) {
      paged_params$pageToken <- page_token
    }

    resp <- httr::GET(API_BASE_URL, query = paged_params, httr::timeout(30))
    httr::stop_for_status(resp)

    payload <- httr::content(resp, as = "text", encoding = "UTF-8")
    parsed <- jsonlite::fromJSON(payload, simplifyVector = FALSE)

    studies <- parsed$studies %||% parsed$results %||% list()
    records <- c(records, lapply(studies, extract_trial_record,
                                 sponsor_field = sponsor_field,
                                 date_fields = date_fields))

    page_token <- parsed$nextPageToken %||% parsed$next_page_token
    if (is.null(page_token)) break
  }

  records
}

aggregate_by_year_and_sponsor <- function(records, start_year = NULL, end_year = NULL) {
  if (!length(records)) return(data.frame())

  filtered <- Filter(function(rec) {
    if (is.na(rec$year)) return(FALSE)
    if (!is.null(start_year) && rec$year < start_year) return(FALSE)
    if (!is.null(end_year) && rec$year > end_year) return(FALSE)
    TRUE
  }, records)

  if (!length(filtered)) return(data.frame())

  df <- do.call(rbind, lapply(filtered, as.data.frame))
  df$year <- as.integer(df$year)

  sponsors <- sort(unique(df$sponsor_class))
  years <- sort(unique(df$year))

  rows <- lapply(years, function(y) {
    counts <- sapply(sponsors, function(s) sum(df$year == y & df$sponsor_class == s))
    data.frame(year = y, t(counts), check.names = FALSE)
  })

  out <- do.call(rbind, rows)
  names(out) <- c("year", sponsors)
  rownames(out) <- NULL
  out
}

summarize_neonatal_trials <- function(term = DEFAULT_TERM,
                                      sponsor_field = DEFAULT_SPONSOR_FIELD,
                                      start_year = NULL,
                                      end_year = NULL,
                                      page_size = DEFAULT_PAGE_SIZE,
                                      max_pages = 30,
                                      output = c("data.frame", "csv"),
                                      file = "") {
  output <- match.arg(output)
  records <- fetch_trials(term = term,
                          sponsor_field = sponsor_field,
                          date_fields = DEFAULT_DATE_FIELDS,
                          page_size = page_size,
                          max_pages = max_pages)

  summary <- aggregate_by_year_and_sponsor(records, start_year = start_year, end_year = end_year)

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

  parse_arg <- function(flag) {
    idx <- which(args == flag)
    if (length(idx) && idx < length(args)) args[[idx + 1]] else NULL
  }

  term <- parse_arg("--term") %||% term
  sponsor_field <- parse_arg("--sponsor-field") %||% sponsor_field
  start_year <- as.integer(parse_arg("--start-year"))
  end_year <- as.integer(parse_arg("--end-year"))
  output <- parse_arg("--output") %||% output
  outfile <- parse_arg("--file") %||% outfile

  result <- summarize_neonatal_trials(
    term = term,
    sponsor_field = sponsor_field,
    start_year = start_year,
    end_year = end_year,
    output = output,
    file = outfile
  )

  if (output != "csv") {
    print(result)
  }
}
