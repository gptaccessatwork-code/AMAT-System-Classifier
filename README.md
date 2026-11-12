# AMAT System Matcher

Current application release: `2026.10.02.1`

Release-ready NiceGUI application for identifying AMAT system types and approved
WD templates from individual system numbers or Excel workbooks. The application
uses the versioned classifier rules and live Agile BOM data already maintained in
this repository.

## Included workflows

- **Individual Lookup** — classify one system without uploading Excel. Results
  include the system type, WD template, parsed system details, rule IDs, evidence,
  and warnings.
- **System Type Excel** — populate the existing `System Type` column in a quote
  request workbook.
- **WD Template Excel** — write the approved WD template beside a `System Number`
  column, including supported headerless workbooks.

The app always creates a downloadable workbook after classification. Any
coverage-limited, unresolved, or failed rows remain blank and are documented in
the `AMAT Match Evidence` worksheet. A user can review coverage-limited proposals,
confirm or correct them, and regenerate the workbook.

## Host requirements

- Windows 10 or Windows 11
- Python 3.11 or newer (64-bit recommended)
- Microsoft Excel desktop application
- Network access to the configured Agile WSDL
- An individual Agile PLM user account

Microsoft Excel is required on the host because output is written through hidden
Excel automation. This preserves validation dropdowns, formulas, formatting, and
other workbook features.

## Install on another PC

1. Extract the release ZIP to a normal local folder. Avoid running directly from
   inside the ZIP.
2. Double-click `setup.bat`. It creates an isolated `.venv` and installs the
   pinned dependencies.
3. Optionally copy `.env.example` to `.env` to change the port or another runtime
   setting.
4. Users enter their own Agile username and password when opening the app. The
   credentials remain in the in-memory server session for that browser and are never written
   to the host PC, logs, workbooks, or caches.
5. Double-click `start_server.bat`.
6. Open `http://localhost:8080`.

Other PCs on the same approved network can use `http://HOST-PC-NAME:8080` if the
Windows firewall and company network policy permit it. Agile sign-in protects the
PLM session but is not a replacement for ASA access control; restrict standalone
network access to the trusted internal network.

## Configuration

Settings are read from `.env`:

| Setting | Default | Purpose |
| --- | --- | --- |
| `AMAT_MATCHER_HOST` | `0.0.0.0` | Listen interface |
| `AMAT_MATCHER_PORT` | `8080` | Web server port |
| `AMAT_MATCHER_ROUTE` | `/` | Standalone route |
| `AMAT_MATCHER_MAX_UPLOAD_MB` | `50` | Maximum workbook size |
| `AMAT_MATCHER_WORKERS` | `10` | Concurrent Agile workers |
| `AMAT_AGILE_WSDL_URL` | Current internal endpoint | Agile Table WSDL |
| `AMAT_EXCEL_STAGING_DIR` | `%LOCALAPPDATA%\AMATSystemMatcher\Excel` | Short local Excel automation folder |

## Integrate into ASA

Copy the `system_type_identifier` package into the ASA Python environment and add
NiceGUI plus the dependencies in `requirements.txt`. Register the page before ASA
calls `ui.run`:

```python
from system_type_identifier.web_ui import register_pages

register_pages('/amat-system-matcher')
```

ASA must call `ui.run` only once. Do not call `system_type_identifier.ui.run_app`
from ASA; that function is solely the standalone launcher.

## Run from source

```powershell
py -3 -m pip install -r requirements.txt
py -3 app.py
```

## Verification

```powershell
py -3 -m unittest discover -s tests -v
py -3 -m compileall -q app.py system_type_identifier tests
```

To verify Microsoft Excel automation on the host PC without connecting to Agile:

```powershell
.venv\Scripts\python.exe verify_excel_output.py
```

The detailed deterministic classification rules are documented in
[REQUIREMENTS.md](REQUIREMENTS.md).
