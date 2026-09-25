# AMAT System Matcher — Release 2026.09.25

## New

- NiceGUI web interface based on the approved dark engineering-tool design.
- Individual system lookup with no workbook upload.
- Combined system-type and WD-template result for individual lookups.
- Parsed system details, rule evidence, warnings, and copy actions.
- In-browser verification, correction, and unresolved-result handling.
- Drag-and-drop System Type and WD Template Excel workflows.
- Batch summary, searchable browser table, and row-level evidence viewer.
- Per-browser-session temporary workspaces for safe concurrent use.
- Configurable host, port, route, upload limit, worker count, and WSDL.
- Per-user Agile sign-in with credentials held only in the browser workspace's
  in-memory server session.
- Visual parity with the Delta BOM Generator theme, including its split sign-in
  card, green/lime palette, panels, typography, top bar, and status bar.
- Reusable `register_pages` entry point for ASA integration.
- One-click Windows setup and server launch scripts.

## Preserved

- Ruleset `2026.09.02.2` and its deterministic rule precedence.
- Template map `2026.09.02.2`.
- Ten-worker Agile batch processing by default.
- Value-only Excel updates through Microsoft Excel automation.
- Source workbook protection and `AMAT Match Evidence` audit worksheet.

## Operational note

Agile sign-in protects each PLM session but does not replace ASA access control.
When hosted outside ASA, bind it only to a trusted internal network or set
`AMAT_MATCHER_HOST=127.0.0.1` for local-only access.

## Maintenance fixes

- Replaced manual content clearing with NiceGUI refreshable components so batch
  processing does not invalidate the button event slot while work starts.
- Moved progress polling to a persistent page-level timer and routed background
  notifications through the stable browser-client context.
