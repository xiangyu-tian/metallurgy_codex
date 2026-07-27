#!/usr/bin/env Rscript

options(stringsAsFactors = FALSE)

user_library <- Sys.getenv("R_LIBS_USER")
if (nzchar(user_library)) {
  .libPaths(c(user_library, .libPaths()))
}

EXPECTED_R <- "4.6.1"
EXPECTED_PACKAGES <- c(
  rbibutils = "2.4.1",
  Rcpp = "1.1.2",
  RcppEigen = "0.3.4.0.2",
  minqa = "1.2.8",
  nloptr = "2.2.1",
  Rdpack = "2.6.6",
  reformulas = "0.4.4",
  estimability = "2.0.0",
  mvtnorm = "1.4.2",
  numDeriv = "2016.8.1.1",
  rlang = "1.3.0",
  lme4 = "2.0.6",
  emmeans = "2.0.4"
)
METHOD_LEVELS <- c(
  "full_schema",
  "lexical_top5",
  "dense_top5",
  "hierarchical"
)
NEIGHBOR_LEVELS <- c(
  "none_0",
  "lexical_4",
  "lexical_8",
  "functional_overlap_4",
  "functional_overlap_8"
)
SINGULAR_TOLERANCE <- 1e-4
MAXFUN <- 200000


stop_with <- function(message, status = 2L) {
  write(message, stderr())
  quit(save = "no", status = status)
}


check_engine <- function() {
  if (as.character(getRversion()) != EXPECTED_R) {
    stop(sprintf(
      "R version mismatch: expected %s, found %s",
      EXPECTED_R,
      as.character(getRversion())
    ))
  }
  for (package_name in names(EXPECTED_PACKAGES)) {
    if (!requireNamespace(package_name, quietly = TRUE)) {
      stop(sprintf("Missing R package: %s", package_name))
    }
    actual <- as.character(packageVersion(package_name))
    expected <- unname(EXPECTED_PACKAGES[[package_name]])
    if (actual != expected) {
      stop(sprintf(
        "Package version mismatch for %s: expected %s, found %s",
        package_name,
        expected,
        actual
      ))
    }
  }
  invisible(TRUE)
}


if (length(commandArgs(trailingOnly = TRUE)) == 1L &&
    commandArgs(trailingOnly = TRUE)[[1]] == "--check") {
  check_engine()
  cat(sprintf("R=%s\n", as.character(getRversion())))
  for (package_name in names(EXPECTED_PACKAGES)) {
    cat(sprintf(
      "%s=%s\n",
      package_name,
      as.character(packageVersion(package_name))
    ))
  }
  quit(save = "no", status = 0L)
}

check_engine()
suppressPackageStartupMessages(library(lme4))
suppressPackageStartupMessages(library(emmeans))


required_columns <- c(
  "selection_correct",
  "method",
  "minimal_pair_group",
  "target_tool_family",
  "pool_family_id",
  "model_run_repeat",
  "difficulty_score",
  "schema_token_count"
)


validate_input <- function(data, hypothesis) {
  missing_columns <- setdiff(required_columns, names(data))
  if (length(missing_columns) > 0L) {
    stop(sprintf(
      "%s input is missing columns: %s",
      hypothesis,
      paste(missing_columns, collapse = ", ")
    ))
  }
  if (nrow(data) == 0L) {
    stop(sprintf("%s input has no rows", hypothesis))
  }
  if (!all(data$selection_correct %in% c(0, 1))) {
    stop("selection_correct must contain only 0 and 1")
  }
  if (length(unique(data$selection_correct)) < 2L) {
    stop("selection_correct is constant; GLMM is not estimable")
  }
  missing_methods <- setdiff(METHOD_LEVELS, unique(data$method))
  unexpected_methods <- setdiff(unique(data$method), METHOD_LEVELS)
  if (length(missing_methods) > 0L || length(unexpected_methods) > 0L) {
    stop(sprintf(
      "%s method set mismatch; missing=[%s], unexpected=[%s]",
      hypothesis,
      paste(missing_methods, collapse = ","),
      paste(unexpected_methods, collapse = ",")
    ))
  }
  for (column in c("difficulty_score", "schema_token_count")) {
    if (any(!is.finite(data[[column]]))) {
      stop(sprintf("%s contains non-finite values", column))
    }
    if (sd(data[[column]]) == 0) {
      stop(sprintf("%s has zero variance", column))
    }
  }
  invisible(TRUE)
}


standardize_input <- function(data) {
  difficulty_mean <- mean(data$difficulty_score)
  difficulty_sd <- sd(data$difficulty_score)
  schema_mean <- mean(data$schema_token_count)
  schema_sd <- sd(data$schema_token_count)
  data$difficulty_score_z <- (
    data$difficulty_score - difficulty_mean
  ) / difficulty_sd
  data$schema_token_count_z <- (
    data$schema_token_count - schema_mean
  ) / schema_sd
  list(
    data = data,
    metadata = data.frame(
      variable = c("difficulty_score", "schema_token_count"),
      mean = c(difficulty_mean, schema_mean),
      sd = c(difficulty_sd, schema_sd)
    )
  )
}


random_sd <- function(fit, group_name) {
  variance_table <- as.data.frame(VarCorr(fit))
  values <- variance_table$sdcor[variance_table$grp == group_name]
  if (length(values) == 0L) {
    return(NA_real_)
  }
  as.numeric(values[[1]])
}


fit_diagnostics <- function(fit, warnings, optimizer, formula_text) {
  optinfo <- slot(fit, "optinfo")
  optimizer_code <- optinfo[["conv"]][["opt"]]
  if (is.null(optimizer_code)) {
    optimizer_code <- NA_integer_
  }
  lme4_messages <- optinfo[["conv"]][["lme4"]][["messages"]]
  if (is.null(lme4_messages)) {
    lme4_messages <- character()
  }
  derivatives <- optinfo[["derivs"]]
  gradient <- if (is.null(derivatives)) NULL else derivatives[["gradient"]]
  hessian <- if (is.null(derivatives)) NULL else derivatives[["Hessian"]]
  max_gradient <- if (is.null(gradient)) NA_real_ else max(abs(gradient))
  min_hessian_eigenvalue <- NA_real_
  if (!is.null(hessian)) {
    min_hessian_eigenvalue <- min(eigen(
      hessian,
      symmetric = TRUE,
      only.values = TRUE
    )$values)
  }
  singular <- isSingular(fit, tol = SINGULAR_TOLERANCE)
  passed <- (
    !is.na(optimizer_code) &&
    optimizer_code == 0 &&
    length(lme4_messages) == 0L &&
    !singular &&
    is.finite(min_hessian_eigenvalue) &&
    min_hessian_eigenvalue > -1e-6
  )
  list(
    passed = passed,
    singular = singular,
    row = data.frame(
      formula = formula_text,
      optimizer = optimizer,
      optimizer_code = optimizer_code,
      lme4_messages = paste(lme4_messages, collapse = " | "),
      warnings = paste(unique(warnings), collapse = " | "),
      max_absolute_gradient = max_gradient,
      min_hessian_eigenvalue = min_hessian_eigenvalue,
      singular = singular,
      passed = passed
    )
  )
}


fit_once <- function(data, formula, optimizer) {
  captured_warnings <- character()
  fit <- tryCatch(
    withCallingHandlers(
      glmer(
        formula,
        data = data,
        family = binomial(link = "logit"),
        nAGQ = 1,
        control = glmerControl(
          optimizer = optimizer,
          calc.derivs = TRUE,
          optCtrl = list(maxfun = MAXFUN)
        )
      ),
      warning = function(warning_condition) {
        captured_warnings <<- c(
          captured_warnings,
          conditionMessage(warning_condition)
        )
        invokeRestart("muffleWarning")
      }
    ),
    error = function(error_condition) error_condition
  )
  formula_text <- paste(deparse(formula), collapse = " ")
  if (inherits(fit, "error")) {
    return(list(
      fit = NULL,
      diagnostics = list(
        passed = FALSE,
        singular = NA,
        row = data.frame(
          formula = formula_text,
          optimizer = optimizer,
          optimizer_code = NA_integer_,
          lme4_messages = conditionMessage(fit),
          warnings = paste(unique(captured_warnings), collapse = " | "),
          max_absolute_gradient = NA_real_,
          min_hessian_eigenvalue = NA_real_,
          singular = NA,
          passed = FALSE
        )
      )
    ))
  }
  list(
    fit = fit,
    diagnostics = fit_diagnostics(
      fit,
      captured_warnings,
      optimizer,
      formula_text
    )
  )
}


make_formula <- function(fixed_formula, random_groups) {
  random_terms <- sprintf("(1 | %s)", random_groups)
  as.formula(paste(
    fixed_formula,
    paste(random_terms, collapse = " + "),
    sep = " + "
  ))
}


fit_with_chain <- function(data, fixed_formula) {
  random_groups <- c(
    "minimal_pair_group",
    "target_tool_family",
    "pool_family_id",
    "model_run_repeat"
  )
  drop_order <- c("model_run_repeat", "pool_family_id")
  attempts <- list()
  attempt_number <- 0L
  last_fit <- NULL

  repeat {
    candidates <- list()
    for (optimizer in c("bobyqa", "Nelder_Mead")) {
      attempt_number <- attempt_number + 1L
      formula <- make_formula(fixed_formula, random_groups)
      result <- fit_once(data, formula, optimizer)
      result$diagnostics$row$attempt <- attempt_number
      result$diagnostics$row$random_groups <- paste(
        random_groups,
        collapse = ","
      )
      attempts[[length(attempts) + 1L]] <- result$diagnostics$row
      if (!is.null(result$fit)) {
        last_fit <- result$fit
        candidates[[length(candidates) + 1L]] <- result
      }
      if (result$diagnostics$passed) {
        return(list(
          status = "converged",
          fit = result$fit,
          attempts = do.call(rbind, attempts),
          random_groups = random_groups,
          optimizer = optimizer
        ))
      }
    }

    if (length(candidates) == 0L) {
      break
    }
    singular_candidates <- Filter(
      function(candidate) isTRUE(candidate$diagnostics$singular),
      candidates
    )
    if (length(singular_candidates) == 0L) {
      break
    }
    candidate_fit <- singular_candidates[[1L]]$fit
    removable <- NULL
    for (group_name in drop_order) {
      if (
        group_name %in% random_groups &&
        is.finite(random_sd(candidate_fit, group_name)) &&
        random_sd(candidate_fit, group_name) <= SINGULAR_TOLERANCE
      ) {
        removable <- group_name
        break
      }
    }
    if (is.null(removable)) {
      break
    }
    random_groups <- setdiff(random_groups, removable)
  }

  list(
    status = "failed",
    fit = last_fit,
    attempts = do.call(rbind, attempts),
    random_groups = random_groups,
    optimizer = NA_character_
  )
}


write_model_tables <- function(result, output_dir, prefix) {
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  write.csv(
    result$attempts,
    file.path(output_dir, paste0(prefix, "_model_attempts.csv")),
    row.names = FALSE,
    na = ""
  )
  if (result$status != "converged") {
    stop(sprintf("%s GLMM failed the convergence chain", toupper(prefix)))
  }

  fit <- result$fit
  fixed <- as.data.frame(coef(summary(fit)))
  fixed$term <- rownames(fixed)
  rownames(fixed) <- NULL
  names(fixed) <- c(
    "estimate",
    "std_error",
    "z_value",
    "p_value_two_sided",
    "term"
  )
  fixed <- fixed[, c(
    "term",
    "estimate",
    "std_error",
    "z_value",
    "p_value_two_sided"
  )]
  write.csv(
    fixed,
    file.path(output_dir, paste0(prefix, "_glmm_fixed_effects.csv")),
    row.names = FALSE,
    na = ""
  )

  random <- as.data.frame(VarCorr(fit))
  write.csv(
    random,
    file.path(output_dir, paste0(prefix, "_glmm_random_effects.csv")),
    row.names = FALSE,
    na = ""
  )
}


run_h3 <- function(data, output_dir) {
  if (!all(c(
    "near_neighbor_type",
    "near_neighbor_count"
  ) %in% names(data))) {
    stop("H3 input is missing neighbor fields")
  }
  data$neighbor_condition <- paste(
    data$near_neighbor_type,
    data$near_neighbor_count,
    sep = "_"
  )
  unexpected <- setdiff(unique(data$neighbor_condition), NEIGHBOR_LEVELS)
  missing <- setdiff(NEIGHBOR_LEVELS, unique(data$neighbor_condition))
  if (length(unexpected) > 0L || length(missing) > 0L) {
    stop(sprintf(
      "H3 neighbor condition mismatch; missing=[%s], unexpected=[%s]",
      paste(missing, collapse = ","),
      paste(unexpected, collapse = ",")
    ))
  }
  data$neighbor_condition <- factor(
    data$neighbor_condition,
    levels = NEIGHBOR_LEVELS
  )
  result <- fit_with_chain(
    data,
    paste(
      "selection_correct ~ method + neighbor_condition",
      "+ difficulty_score_z + schema_token_count_z"
    )
  )
  write_model_tables(result, output_dir, "h3")
  fit <- result$fit

  marginal_means <- emmeans(
    fit,
    ~ neighbor_condition,
    weights = "equal"
  )
  coefficients <- list(
    functional_overlap_8_minus_lexical_8 = c(0, 0, -1, 0, 1),
    functional_overlap_8_minus_none_0 = c(-1, 0, 0, 0, 1),
    lexical_8_minus_none_0 = c(-1, 0, 1, 0, 0)
  )
  contrasts <- contrast(
    marginal_means,
    method = coefficients,
    adjust = "none"
  )
  two_sided <- as.data.frame(summary(
    contrasts,
    infer = c(TRUE, TRUE),
    adjust = "none"
  ))
  direct_one_sided <- as.data.frame(test(
    contrast(
      marginal_means,
      method = list(
        functional_overlap_8_minus_lexical_8 = c(0, 0, -1, 0, 1)
      ),
      adjust = "none"
    ),
    side = "<",
    adjust = "none"
  ))
  two_sided$alternative <- "two_sided"
  two_sided$p_value_one_sided <- NA_real_
  direct_index <- (
    two_sided$contrast ==
    "functional_overlap_8_minus_lexical_8"
  )
  two_sided$alternative[direct_index] <- "less"
  two_sided$p_value_one_sided[direct_index] <- direct_one_sided$p.value[[1]]
  write.csv(
    two_sided,
    file.path(output_dir, "h3_glmm_planned_contrasts.csv"),
    row.names = FALSE,
    na = ""
  )
  result
}


run_h4 <- function(data, output_dir) {
  if (!"tool_pool_size" %in% names(data)) {
    stop("H4 input is missing tool_pool_size")
  }
  if (!all(data$tool_pool_size %in% c(17, 50, 100, 120))) {
    stop("H4 tool_pool_size contains unsupported values")
  }
  data$log_tool_pool_size <- log(data$tool_pool_size)
  result <- fit_with_chain(
    data,
    paste(
      "selection_correct ~ method * log_tool_pool_size",
      "+ difficulty_score_z + schema_token_count_z"
    )
  )
  write_model_tables(result, output_dir, "h4")
  fit <- result$fit

  response_grid <- regrid(
    emmeans(
      fit,
      ~ method * log_tool_pool_size,
      at = list(log_tool_pool_size = log(c(17, 120))),
      weights = "equal"
    ),
    transform = "response"
  )
  grid <- as.data.frame(response_grid)
  comparison_coefficients <- list()
  for (baseline in METHOD_LEVELS[METHOD_LEVELS != "hierarchical"]) {
    coefficient <- rep(0, nrow(grid))
    coefficient[
      grid$method == "hierarchical" &
      abs(grid$log_tool_pool_size - log(120)) < 1e-10
    ] <- 1
    coefficient[
      grid$method == "hierarchical" &
      abs(grid$log_tool_pool_size - log(17)) < 1e-10
    ] <- -1
    coefficient[
      grid$method == baseline &
      abs(grid$log_tool_pool_size - log(120)) < 1e-10
    ] <- -1
    coefficient[
      grid$method == baseline &
      abs(grid$log_tool_pool_size - log(17)) < 1e-10
    ] <- 1
    comparison_coefficients[[
      paste0("hierarchical_vs_", baseline)
    ]] <- coefficient
  }
  comparisons <- contrast(
    response_grid,
    method = comparison_coefficients,
    adjust = "none"
  )
  comparison_table <- as.data.frame(summary(
    comparisons,
    infer = c(TRUE, TRUE),
    side = ">",
    adjust = "none"
  ))
  comparison_table$p_value_raw <- comparison_table$p.value
  comparison_table$p_value_holm <- p.adjust(
    comparison_table$p_value_raw,
    method = "holm"
  )
  comparison_table$passed <- (
    comparison_table$estimate > 0 &
    comparison_table$p_value_holm < 0.05
  )
  all_positive <- all(comparison_table$estimate > 0)
  passed_count <- sum(comparison_table$passed)
  support <- if (passed_count == nrow(comparison_table)) {
    "full_support"
  } else if (all_positive && passed_count > 0L) {
    "partial_support"
  } else {
    "not_supported"
  }
  comparison_table$support_classification <- support
  write.csv(
    comparison_table,
    file.path(output_dir, "h4_glmm_planned_contrasts.csv"),
    row.names = FALSE,
    na = ""
  )
  result
}


args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) {
  stop_with(
    "Usage: glmm_engine.R <h3|h4> <input.csv> <output_dir>"
  )
}
hypothesis <- tolower(args[[1]])
input_path <- args[[2]]
output_dir <- args[[3]]
if (!hypothesis %in% c("h3", "h4")) {
  stop_with("Hypothesis must be h3 or h4")
}
if (!file.exists(input_path)) {
  stop_with(sprintf("Input file does not exist: %s", input_path))
}

data <- read.csv(input_path, check.names = FALSE)
validate_input(data, toupper(hypothesis))
data$method <- factor(data$method, levels = METHOD_LEVELS)
for (column in c(
  "minimal_pair_group",
  "target_tool_family",
  "pool_family_id",
  "model_run_repeat"
)) {
  data[[column]] <- factor(data[[column]])
}
standardized <- standardize_input(data)
data <- standardized$data
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
write.csv(
  standardized$metadata,
  file.path(output_dir, paste0(hypothesis, "_standardization.csv")),
  row.names = FALSE
)

engine_metadata <- data.frame(
  key = c(
    "r_version",
    "lme4_version",
    "emmeans_version",
    "family",
    "link",
    "nAGQ",
    "maxfun",
    "singular_tolerance"
  ),
  value = c(
    as.character(getRversion()),
    as.character(packageVersion("lme4")),
    as.character(packageVersion("emmeans")),
    "binomial",
    "logit",
    "1",
    as.character(MAXFUN),
    as.character(SINGULAR_TOLERANCE)
  )
)
write.csv(
  engine_metadata,
  file.path(output_dir, paste0(hypothesis, "_engine_metadata.csv")),
  row.names = FALSE
)

tryCatch(
  {
    if (hypothesis == "h3") {
      run_h3(data, output_dir)
    } else {
      run_h4(data, output_dir)
    }
  },
  error = function(error_condition) {
    stop_with(conditionMessage(error_condition), status = 3L)
  }
)

cat(sprintf("%s GLMM completed: %s\n", toupper(hypothesis), output_dir))
