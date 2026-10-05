# Reproducibility and export changes

This export preserves the study's Python preparation, R model engines, sensitivity analyses and plotting logic. Paths under `work/air_pollution_cc`, local diagnostic directories and historical output filenames are retained so modules resolve their existing dependencies. Run from the repository root.

Export adaptations:

- Local workbook names and worksheet names were moved to an ignored source configuration with generic examples.
- Fixed study-size assertions in selected preparation/model scripts were replaced by nonempty and uniqueness checks; the original clinical rules and statistical contrasts were retained.
- Node's machine-specific executable path was replaced with `node`; the offline coordinate package is declared in `package.json`.
- External geocoding entry points require an explicit local authorization environment variable.
- Flow-chart labels are computed from local aggregate files rather than copied cohort counts.
- Small helper scripts create the five-subtype local scope, stage aggregate plotting inputs and describe annual counts. These export helpers do not change event adjudication.
- All article/Word/EndNote builders, literary-review tools and documents were excluded.

Validation performed for the release: Python parsing, R parsing, static allowed-file/privacy checks, and simulated conditional-likelihood validation. The original patient-level analysis was not rerun for publication of code. Actual-data results require private inputs and the original clinical/geographic quality decisions. No simulated output should be represented as a Guangzhou study result.

The requirements file provides bounded ranges; it is not a complete lockfile. Record all environment versions in each local run. Product records and checksums are pinned in the downloader; APIs, provider quotas and packages can change. Existing intermediate files are often deliberately protected from overwrite. Use fresh versioned local directories when rerunning, and preserve audit/provenance records.

Model limitations to retain when interpreting results include uncertain acute-event eligibility in some surveillance categories, address imputation and lack of independent spatial validation, weather-grid coarseness, person versus temporal dependence, exploratory additions and multiplicity. These qualifications are part of the analysis code, not permission to replace unresolved records with confirmed events.
