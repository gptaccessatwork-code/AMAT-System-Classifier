"""Host-PC smoke test for the Microsoft Excel output pipeline."""

from pathlib import Path
import tempfile

from openpyxl import Workbook, load_workbook

from system_type_identifier.models import (
    ClassificationDecision,
    DecisionStatus,
    SystemClassification,
)
from system_type_identifier.workflows import (
    EVIDENCE_SHEET_NAME,
    WorkflowMode,
    _excel_staging_directory,
    build_update_plan,
    load_quote_request_layout,
    write_workbook_copy_with_result,
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="amat_excel_check_") as folder:
        root = Path(folder)
        source = root / "input.xlsx"
        output = root / "output.xlsx"

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Quote Request"
        sheet["D1"] = "System Number"
        sheet["H1"] = "System Type"
        sheet["D2"] = "707844-XA3-GPA"
        workbook.save(source)

        layout = load_quote_request_layout(source)
        plan = build_update_plan(
            layout,
            [
                SystemClassification(
                    source_row=2,
                    system_number="707844-XA3-GPA",
                    build_type="NORMAL",
                    decision=ClassificationDecision(
                        DecisionStatus.CLASSIFIED,
                        "ETCH SYM3 AP (XA)",
                    ),
                )
            ],
            WorkflowMode.SYSTEM_TYPE,
        )
        write_result = write_workbook_copy_with_result(plan, output)

        result = load_workbook(output, read_only=True, data_only=False)
        try:
            assert result["Quote Request"]["H2"].value == "ETCH SYM3 AP (XA)"
            assert EVIDENCE_SHEET_NAME in result.sheetnames
        finally:
            result.close()

        print(f"Workbook output verification passed using: {write_result.writer}")
        if write_result.warning:
            print("Microsoft Excel automation failed, but compatibility mode succeeded.")
            print(f"Excel details: {write_result.warning}")
        print(f"Excel staging folder: {_excel_staging_directory()}")


if __name__ == "__main__":
    main()
