# AMAT System Matcher

Windows desktop application with two Excel workflows built on the versioned
AMAT system-type rules and direct Agile WSDL BOM retrieval.

## Run from source

Microsoft Excel must be installed because output workbooks are updated through
hidden Excel automation to preserve dropdowns, formulas, formatting, and other
workbook features.

```powershell
py -3 -m pip install -r requirements.txt
py -3 app.py
```

Agile credentials load automatically from `script_credentials.json` in the
parent `Scripts` directory using `AGILE_USER` and `AGILE_PASS`. Credential
values are not displayed or written to source files, reports, logs, or caches.

## System Type

Select a quote-request `.xlsx` workbook containing `System Number` and
`System Type` headers on the same row. The headers may occur within the first
25 rows; they are detected rather than assumed to be on a fixed row.

The application classifies each populated system number, copies the source
workbook to the chosen output path, and assigns only the corresponding System
Type cell value. Microsoft Excel performs the update, preserving list
validation such as the dropdowns in the quote-request workbook. Invalid,
unclassified, failed, and unconfirmed results are written as blank values.

## WD Template

Select an `.xlsx` workbook containing a column headed `System Number`. The
application writes `WD Template` in the adjacent column. A headerless column of
valid system numbers is also supported; in that case templates are written
beside the existing rows without adding a header.

The adjacent column must be empty or already headed `WD Template`, `Template`,
or `System Template`. The application refuses to overwrite an unrelated
adjacent column. The approved 42-type mapping is implemented in
`system_type_identifier.templates` and contains 31 unique WD templates.

## Processing

Both modes use a pool of 10 Agile workers. Output row order matches the source
workbook, concurrent requests for the same part share the synchronized BOM
cache, and the source workbook is never modified.

Six coverage-limited system types return `VERIFICATION_REQUIRED`. The
application prompts for each affected row. Confirmed proposals are written. If
a proposal is wrong, select a corrected canonical type and optionally enter a
feedback note; the corrected type or its WD template is written for that run.
Unresolved proposals remain blank, and cancelling verification aborts output
creation.

Every output workbook includes an `AMAT Match Evidence` worksheet. It records
the proposed and written values, status, matched rule IDs, BOM evidence,
warnings, ruleset/template versions, user verification, corrections, notes, and
a `Requirements Action`. Return this workbook when refining the rules:
`CONFIDENCE_EXAMPLE` supports the proposed low-confidence type,
`RULE_CORRECTION` identifies a wrong proposal with its corrected type, and
`RULE_REVIEW` identifies a rejected proposal that still needs investigation.

The deterministic rules and template map are documented in
[REQUIREMENTS.md](REQUIREMENTS.md). The labeled-evaluation modules and reports
remain in the codebase for regression testing and rule refinement.
