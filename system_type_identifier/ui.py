from __future__ import annotations

from collections import Counter
from pathlib import Path
import threading
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .agile import DEFAULT_CREDENTIALS_PATH, DEFAULT_WSDL_URL, AgileBomClient
from .classifier import RULESET_VERSION, SystemTypeClassifier
from .models import DecisionStatus
from .parser import parse_system_number
from .processor import BatchSystemClassifier
from .templates import SYSTEM_TYPE_TO_WD_TEMPLATE
from .workflows import (
    VerificationFeedback,
    VerificationOutcome,
    WorkflowMode,
    build_update_plan,
    load_quote_request_layout,
    load_template_input_layout,
    write_value_only_workbook_copy,
)


_MODE_LABELS = {
    "System Type": WorkflowMode.SYSTEM_TYPE,
    "WD Template": WorkflowMode.WD_TEMPLATE,
}


class ClassificationCorrectionDialog(ctk.CTkToplevel):
    def __init__(self, parent, classification) -> None:
        super().__init__(parent)
        self.result: VerificationFeedback | None = None
        self.title("Correct classification")
        self.geometry("700x430")
        self.minsize(620, 390)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        decision = classification.decision
        ctk.CTkLabel(
            self,
            text=f"Row {classification.source_row}: {classification.system_number}",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 6))
        ctk.CTkLabel(
            self,
            text=f"Proposed: {decision.predicted_system_type}",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))
        ctk.CTkLabel(self, text="Correct system type", anchor="w").grid(
            row=2, column=0, sticky="ew", padx=20, pady=(0, 4)
        )
        self.type_combo = ctk.CTkComboBox(
            self,
            values=list(SYSTEM_TYPE_TO_WD_TEMPLATE),
            state="readonly",
        )
        self.type_combo.set("")
        self.type_combo.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 14))
        ctk.CTkLabel(self, text="Feedback notes", anchor="w").grid(
            row=4, column=0, sticky="new", padx=20, pady=(0, 4)
        )
        self.notes = ctk.CTkTextbox(self, height=110, wrap="word")
        self.notes.grid(row=5, column=0, sticky="nsew", padx=20, pady=(0, 14))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="e", padx=20, pady=(0, 20))
        ctk.CTkButton(
            actions,
            text="Use Correction",
            command=self._use_correction,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Leave Unresolved",
            fg_color="#7A5B20",
            hover_color="#624918",
            command=self._leave_unresolved,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Cancel",
            fg_color="#8B3A3A",
            hover_color="#6F2D2D",
            command=self._cancel,
        ).grid(row=0, column=2)

        self.grab_set()
        self.after(50, self.focus_force)

    def show(self) -> VerificationFeedback | None:
        self.wait_window()
        return self.result

    def _use_correction(self) -> None:
        corrected = self.type_combo.get().strip()
        if corrected not in SYSTEM_TYPE_TO_WD_TEMPLATE:
            messagebox.showerror(
                "Select a system type",
                "Select the correct canonical system type.",
                parent=self,
            )
            return
        self.result = VerificationFeedback(
            VerificationOutcome.CORRECTED,
            corrected_system_type=corrected,
            notes=self.notes.get("1.0", "end").strip(),
        )
        self.destroy()

    def _leave_unresolved(self) -> None:
        self.result = VerificationFeedback(
            VerificationOutcome.REJECTED,
            notes=self.notes.get("1.0", "end").strip(),
        )
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class SystemTypeWorkbench(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("green")
        self.title("AMAT System Matcher")
        self.geometry("1120x760")
        self.minsize(900, 650)
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="AMAT System Matcher",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text=f"Ruleset {RULESET_VERSION}",
            text_color=("#55615F", "#AAB6B3"),
        ).grid(row=0, column=1, sticky="e")

        mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_frame.grid(row=1, column=0, sticky="w", padx=24, pady=4)
        self.mode_control = ctk.CTkSegmentedButton(
            mode_frame,
            values=list(_MODE_LABELS),
            command=self._mode_changed,
            width=300,
        )
        self.mode_control.grid(row=0, column=0)

        connection = ctk.CTkFrame(self, corner_radius=6)
        connection.grid(row=2, column=0, sticky="ew", padx=24, pady=6)
        connection.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(connection, text="Agile WSDL").grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )
        self.wsdl_entry = ctk.CTkEntry(connection)
        self.wsdl_entry.insert(0, DEFAULT_WSDL_URL)
        self.wsdl_entry.grid(
            row=0,
            column=1,
            columnspan=3,
            padx=(0, 12),
            pady=10,
            sticky="ew",
        )
        ctk.CTkLabel(connection, text="Credentials").grid(
            row=1, column=0, padx=12, pady=(0, 10), sticky="w"
        )
        ctk.CTkLabel(
            connection,
            text=str(DEFAULT_CREDENTIALS_PATH),
            anchor="w",
            text_color=("#55615F", "#AAB6B3"),
        ).grid(
            row=1,
            column=1,
            columnspan=3,
            padx=(0, 12),
            pady=(0, 10),
            sticky="ew",
        )

        files = ctk.CTkFrame(self, corner_radius=6)
        files.grid(row=3, column=0, sticky="ew", padx=24, pady=6)
        files.grid_columnconfigure(1, weight=1)
        self.input_label = ctk.CTkLabel(files, text="Quote request workbook")
        self.input_label.grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.input_entry = ctk.CTkEntry(files)
        self.input_entry.grid(row=0, column=1, padx=8, pady=10, sticky="ew")
        ctk.CTkButton(
            files,
            text="Browse",
            width=90,
            command=self._browse_input,
        ).grid(row=0, column=2, padx=12, pady=10)
        self.output_label = ctk.CTkLabel(files, text="System type workbook")
        self.output_label.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")
        self.output_entry = ctk.CTkEntry(files)
        self.output_entry.grid(row=1, column=1, padx=8, pady=(0, 10), sticky="ew")
        ctk.CTkButton(
            files,
            text="Browse",
            width=90,
            command=self._browse_output,
        ).grid(row=1, column=2, padx=12, pady=(0, 10))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=24, pady=8)
        actions.grid_columnconfigure(2, weight=1)
        self.run_button = ctk.CTkButton(
            actions,
            text="Find System Types",
            width=160,
            command=self._start,
        )
        self.run_button.grid(row=0, column=0, padx=(0, 8))
        self.cancel_button = ctk.CTkButton(
            actions,
            text="Cancel",
            width=90,
            fg_color="#8B3A3A",
            hover_color="#6F2D2D",
            state="disabled",
            command=self.cancel_event.set,
        )
        self.cancel_button.grid(row=0, column=1)
        self.status_label = ctk.CTkLabel(actions, text="Ready", anchor="e")
        self.status_label.grid(row=0, column=2, sticky="e")

        results = ctk.CTkFrame(self, corner_radius=6)
        results.grid(row=5, column=0, sticky="nsew", padx=24, pady=(4, 12))
        results.grid_columnconfigure(0, weight=1)
        results.grid_rowconfigure(1, weight=1)
        self.progress = ctk.CTkProgressBar(results, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        self.progress.set(0)

        columns = ("status", "count")
        self.summary_tree = ttk.Treeview(
            results,
            columns=columns,
            show="headings",
            height=8,
        )
        self.summary_tree.heading("status", text="Classification Status")
        self.summary_tree.heading("count", text="Count")
        self.summary_tree.column("status", width=320, anchor="w")
        self.summary_tree.column("count", width=100, anchor="center")
        self.summary_tree.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=12,
            pady=(0, 12),
        )

        self.log = ctk.CTkTextbox(self, height=115, wrap="word")
        self.log.grid(row=6, column=0, sticky="ew", padx=24, pady=(0, 20))
        self.log.configure(state="disabled")
        self.mode_control.set("System Type")

    def _mode_changed(self, selected: str) -> None:
        if _MODE_LABELS[selected] == WorkflowMode.SYSTEM_TYPE:
            self.input_label.configure(text="Quote request workbook")
            self.output_label.configure(text="System type workbook")
            self.run_button.configure(text="Find System Types")
        else:
            self.input_label.configure(text="System number workbook")
            self.output_label.configure(text="WD template workbook")
            self.run_button.configure(text="Find WD Templates")
        input_path = self.input_entry.get().strip()
        if input_path:
            self._set_entry(self.output_entry, self._default_output_path(input_path))

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Excel workbook", "*.xlsx")])
        if not path:
            return
        self._set_entry(self.input_entry, path)
        self._set_entry(self.output_entry, self._default_output_path(path))

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if path:
            self._set_entry(self.output_entry, path)

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        input_path = self.input_entry.get().strip()
        output_path = self.output_entry.get().strip()
        if not input_path or not output_path:
            messagebox.showerror(
                "Missing file",
                "Select an input workbook and output workbook path.",
            )
            return
        try:
            if Path(input_path).resolve() == Path(output_path).resolve():
                raise ValueError("Output path must be different from the source workbook")
            mode = self._selected_mode()
            layout = (
                load_quote_request_layout(input_path)
                if mode == WorkflowMode.SYSTEM_TYPE
                else load_template_input_layout(input_path)
            )
        except Exception as exc:
            messagebox.showerror("Invalid workbook", str(exc))
            return
        if Path(output_path).exists() and not messagebox.askyesno(
            "Replace output",
            f"Replace the existing output workbook?\n\n{output_path}",
        ):
            return

        classifier = SystemTypeClassifier()
        needs_bom = any(
            classifier.required_bom_depth(parse_system_number(item.system_number)) != 0
            for item in layout.inputs
        )
        self.cancel_event.clear()
        self.run_button.configure(state="disabled")
        self.mode_control.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.start()
        self._clear_summary()
        self._append_log(
            f"Loaded {len(layout.inputs)} system numbers from {layout.sheet_name}"
        )
        wsdl_url = self.wsdl_entry.get().strip()
        self.worker = threading.Thread(
            target=self._run_classification,
            args=(layout, output_path, mode, classifier, needs_bom, wsdl_url),
            daemon=True,
        )
        self.worker.start()

    def _run_classification(
        self,
        layout,
        output_path: str,
        mode: WorkflowMode,
        classifier: SystemTypeClassifier,
        needs_bom: bool,
        wsdl_url: str,
    ) -> None:
        try:
            client = None
            if needs_bom:
                self._queue_status("Connecting to Agile WSDL")
                client = AgileBomClient.from_script_credentials(
                    wsdl_url=wsdl_url,
                    credentials_path=DEFAULT_CREDENTIALS_PATH,
                )
            classifications = BatchSystemClassifier(classifier, client).classify(
                layout.inputs,
                progress=self._queue_status,
                cancel_event=self.cancel_event,
            )
            if self.cancel_event.is_set():
                self.after(0, lambda: self._finish(None, "Operation cancelled"))
                return
            self.after(
                0,
                lambda: self._review_and_write(
                    layout,
                    classifications,
                    output_path,
                    mode,
                ),
            )
        except Exception as exc:
            message = f"Classification failed: {exc}"
            self.after(
                0,
                lambda message=message: self._finish(None, message, error=True),
            )

    def _review_and_write(
        self,
        layout,
        classifications,
        output_path: str,
        mode: WorkflowMode,
    ) -> None:
        feedback_by_row: dict[int, VerificationFeedback] = {}
        for classification in classifications:
            decision = classification.decision
            if decision.status != DecisionStatus.VERIFICATION_REQUIRED:
                continue
            response = messagebox.askyesnocancel(
                "Verify classification",
                f"Workbook row: {classification.source_row}\n"
                f"System number: {classification.system_number}\n"
                f"Proposed type: {decision.predicted_system_type}\n\n"
                "Is this classification correct?\n\n"
                "Yes: write the result\n"
                "No: enter a correction or leave unresolved\n"
                "Cancel: abort without creating the output workbook",
            )
            if response is None:
                self._finish(None, "Operation cancelled during verification")
                return
            if response:
                feedback_by_row[classification.source_row] = VerificationFeedback(
                    VerificationOutcome.CONFIRMED
                )
            else:
                correction = ClassificationCorrectionDialog(
                    self,
                    classification,
                ).show()
                if correction is None:
                    self._finish(None, "Operation cancelled during verification")
                    return
                feedback_by_row[classification.source_row] = correction

        resolved_feedback_rows = {
            row
            for row, feedback in feedback_by_row.items()
            if feedback.outcome
            in {VerificationOutcome.CONFIRMED, VerificationOutcome.CORRECTED}
        }
        unresolved = [
            classification
            for classification in classifications
            if classification.decision.status != DecisionStatus.CLASSIFIED
            and classification.source_row not in resolved_feedback_rows
        ]
        for classification in unresolved[:100]:
            decision = classification.decision
            detail = next(iter(decision.warnings or decision.evidence), "Manual review required")
            self._append_log(
                f"Review row {classification.source_row}: "
                f"{classification.system_number} [{decision.status.value}] {detail}"
            )
        if len(unresolved) > 100:
            self._append_log(
                f"{len(unresolved) - 100} additional blank rows require review"
            )

        try:
            plan = build_update_plan(
                layout,
                classifications,
                mode,
                feedback_by_row=feedback_by_row,
            )
        except Exception as exc:
            self._finish(None, f"Unable to prepare output: {exc}", error=True)
            return

        self.cancel_button.configure(state="disabled")
        self.status_label.configure(text="Writing output workbook")
        self._append_log("Writing value-only updates through Microsoft Excel")
        self.worker = threading.Thread(
            target=self._run_writer,
            args=(plan, classifications, output_path),
            daemon=True,
        )
        self.worker.start()

    def _run_writer(self, plan, classifications, output_path: str) -> None:
        try:
            saved_path = write_value_only_workbook_copy(plan, output_path)
            message = (
                f"Workbook saved: {saved_path}\n"
                f"Values written: {plan.written_count}; left blank: {plan.blank_count}"
            )
            self.after(
                0,
                lambda: self._finish(
                    classifications,
                    message,
                    blank_count=plan.blank_count,
                ),
            )
        except Exception as exc:
            message = f"Workbook output failed: {exc}"
            self.after(
                0,
                lambda message=message: self._finish(None, message, error=True),
            )

    def _finish(
        self,
        classifications,
        message: str,
        error: bool = False,
        blank_count: int = 0,
    ) -> None:
        self.progress.stop()
        self.progress.set(0)
        self.run_button.configure(state="normal")
        self.mode_control.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.status_label.configure(text="Failed" if error else "Ready")
        self._append_log(message)
        if classifications is not None:
            counts = Counter(
                classification.decision.status.value
                for classification in classifications
            )
            for status, count in sorted(counts.items()):
                self.summary_tree.insert("", "end", values=(status, count))
        if error:
            messagebox.showerror("Operation failed", message)
        elif blank_count:
            messagebox.showwarning(
                "Workbook complete with review items",
                f"{message}\n\n"
                "Blank output cells require manual review or were not confirmed.",
            )
        elif classifications is not None:
            messagebox.showinfo("Workbook complete", message)

    def _queue_status(self, message: str) -> None:
        self.after(
            0,
            lambda: (
                self.status_label.configure(text=message),
                self._append_log(message),
            ),
        )

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_summary(self) -> None:
        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)

    def _selected_mode(self) -> WorkflowMode:
        return _MODE_LABELS[self.mode_control.get()]

    def _default_output_path(self, input_path: str) -> str:
        path = Path(input_path)
        suffix = (
            "_system_types.xlsx"
            if self._selected_mode() == WorkflowMode.SYSTEM_TYPE
            else "_wd_templates.xlsx"
        )
        return str(path.with_name(f"{path.stem}{suffix}"))

    @staticmethod
    def _set_entry(entry: ctk.CTkEntry, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)


def run_app() -> None:
    app = SystemTypeWorkbench()
    app.mainloop()
