# Privacy and release boundaries

The public release is selected source code and documentation only. No workbooks, event rows, address strings, geocoded person locations, identifier salts, local keys, provider responses, cached queries, model-row RDS files, actual numerical result tables, figures or manuscript documents are uploaded.

Identity tokens use a locally generated HMAC salt. Tokens do not make a clinical dataset anonymous. Dates, geography, age and disease combinations can allow re-identification; all person/event-level intermediate files remain confidential.

Address geocoding can transmit personal location information to an external provider. This repository does not authorize that transmission. Obtain custodian approval for the specific fields and provider before enabling `GEOCODING_AUTHORIZED=YES`. Never send identity numbers, names, diagnoses or event dates with a geocoding request. Keep credentials outside tracked source. Provider quota values in historical scripts are project-era limits; confirm the current account terms rather than assuming they apply.

Environment downloads request public archives or a fixed regional weather lattice, not patient coordinates. Generated diagnostics and aggregate tables may contain small cells or local provenance; they are ignored by default and need a separate disclosure review before sharing.

The release uses a clean directory and an explicit allowed-file list, never a copy of the clinical workspace or its private caches. The release checker is a conservative static screen, not a guarantee of de-identification. Manual review remains necessary for later commits.
