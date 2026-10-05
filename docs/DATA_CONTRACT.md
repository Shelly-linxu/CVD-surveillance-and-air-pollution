# Local data contract

All files in this contract are local inputs or local outputs; none is part of the public repository.

## Workbook fields

The source-reader aliases include:

| Meaning | Original aliases |
|---|---|
| Event date | 发病日期 |
| Birth date | 出生日期 |
| Sex | 性别 |
| Diagnostic code | ICD10 |
| Diagnosis text | 诊断 |
| Report date | 报告日期 |
| Diagnosis date | 诊断日期 |
| Identity for local linkage | 身份证号 |
| Report-card identifier | 报告卡编号 |
| Review status | 审核状态, 卡片状态 |
| Duplicate flag | 是否重卡 |
| First-onset flag | 是否首次发病 |
| Current address province/city/district/street/community/number | 现住地址（省）, 现住地址（市）, 现住地址（区县）, 现住地址（街道/乡）, 现住地址（居委会/村）, 现住地址（门牌号）; alternative aliases are in `prepare_cases.py` |

Required fields must be reviewed against the actual export. Numeric Excel dates are interpreted using the workbook's expected 1900 date system; verify this before reusing the reader. Identity-format and checksum audits support linkage and anomaly flags, not public disclosure.

## Private interfaces

- `candidate_events.csv.gz`: one candidate event, local salted `person_id`, `event_id`, `location_id`, onset, ICD, age, sex and quality flags.
- `geocoding_queue.csv`: unique location token, address string and address-detail indicators; private even before coordinates are filled.
- `candidate_matches.csv.gz`: one event/date, one case indicator per event, fixed location ID and same-month/same-weekday referents.
- `event_outcome_candidates.csv.gz`: outcome coding annotations created by the temporal/outcome preparation.
- `event_adjudication.csv`: versioned decisions, review reasons, flags, eligibility and deduplication status. Never overwrite a frozen audit without a deliberate new version.
- `all_address_matching_completed.csv`: location coordinates plus original missingness, provenance and imputation flags.
- `all_address_matching_quality_checked.csv`: cache-based consistency assessment and ambiguity/precision flags.
- `location_quality.csv`: location ID, WGS84 longitude/latitude, eligible/core/coarse tiers and `coordinate_imputed`.
- `two_group/matched_exposure_rows.csv.gz`: event/date exposure histories and weather-grid identifiers.
- `weather_basis_*.csv.gz`: date/weather-grid temperature cross-basis and humidity spline columns.
- `two_group/registry_model_rows.rds`, `five_outcomes/registry_model_rows.rds`: private analytical rows, never distributable as code.

Provider orchestration expects its own local SQLite caches. You may instead supply locally approved coordinates, but must construct the documented audit/quality fields and avoid claiming independent accuracy without evidence. Do not mark an unknown source as verified merely to pass a model gate.
