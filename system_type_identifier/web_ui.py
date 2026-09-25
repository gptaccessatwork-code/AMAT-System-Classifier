from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from queue import SimpleQueue
import tempfile
import threading
from typing import Any

from nicegui import events, run, ui

from .classifier import RULESET_VERSION
from .config import AppSettings, SETTINGS
from .models import DecisionStatus, SystemClassification
from .parser import parse_system_number
from .service import SystemMatcherService, display_result, result_row
from .templates import SYSTEM_TYPE_TO_WD_TEMPLATE, TEMPLATE_MAP_VERSION
from .web_styles import APP_CSS
from .workflows import (
    VerificationFeedback,
    VerificationOutcome,
    WorkflowMode,
    build_update_plan,
    write_value_only_workbook_copy,
)


_STATUS_STYLE = {
    DecisionStatus.CLASSIFIED: ("check_circle", "status-success", "Classified"),
    DecisionStatus.VERIFICATION_REQUIRED: ("verified_user", "status-warning", "Verification required"),
    DecisionStatus.NEEDS_REVIEW: ("rate_review", "status-warning", "Needs review"),
    DecisionStatus.MANUAL_REVIEW_NSO: ("engineering", "status-warning", "Manual review NSO"),
    DecisionStatus.UNCLASSIFIED: ("help_outline", "status-neutral", "Unclassified"),
    DecisionStatus.EXCLUDED_INVALID_FORMAT: ("error_outline", "status-danger", "Invalid format"),
    DecisionStatus.BOM_RETRIEVAL_ERROR: ("cloud_off", "status-danger", "BOM retrieval error"),
    DecisionStatus.RULE_CONFLICT: ("warning", "status-danger", "Rule conflict"),
}


class MatcherPage:
    """One isolated System Matcher workspace for a browser client."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.service = SystemMatcherService(settings)
        self.mode: str = "lookup"
        self.lookup_value = ""
        self.lookup_result: SystemClassification | None = None
        self.lookup_feedback: VerificationFeedback | None = None
        self.layouts: dict[WorkflowMode, Any] = {}
        self.input_paths: dict[WorkflowMode, Path] = {}
        self.classifications: dict[WorkflowMode, list[SystemClassification]] = {}
        self.feedback: dict[WorkflowMode, dict[int, VerificationFeedback]] = {}
        self.output_paths: dict[WorkflowMode, Path] = {}
        self.cancel_event = threading.Event()
        self.messages: SimpleQueue[str] = SimpleQueue()
        self._temp = tempfile.TemporaryDirectory(prefix="amat_matcher_")
        self.workspace = Path(self._temp.name)
        self.client: Any = None
        self.progress_timer: ui.timer | None = None
        self.activity_log: ui.log | None = None
        self.progress_label: ui.label | None = None
        self.progress_bar: ui.linear_progress | None = None
        self.status_label: ui.label | None = None
        self.username_input: ui.input | None = None
        self.password_input: ui.input | None = None
        self.login_button: ui.button | None = None
        self.signed_in_username = ""
        self.busy = False
        self.workflow_cards: dict[str, ui.card] = {}

    def build(self) -> None:
        ui.add_css(APP_CSS)
        ui.colors(primary="#6fc926", secondary="#65d5a7", accent="#55b993", dark="#081116")
        ui.dark_mode().enable()
        self.client = ui.context.client
        self.client.on_disconnect(self.close)
        with ui.column().classes("app-shell w-full no-wrap gap-0"):
            with ui.column().classes("w-full grow gap-0"):
                self.render_content()
            with ui.row().classes("statusbar w-full items-center no-wrap"):
                self.status_label = ui.label("Sign in to begin")
                ui.space()
                ui.label(f"Ruleset {RULESET_VERSION}  ·  Template map {TEMPLATE_MAP_VERSION}")
        self.progress_timer = ui.timer(0.2, self._drain_progress, active=False)

    def close(self) -> None:
        self.cancel_event.set()
        self.service.sign_out()
        try:
            self._temp.cleanup()
        except (OSError, PermissionError):
            pass

    def _header(self) -> None:
        with ui.row().classes("topbar w-full items-center no-wrap"):
            ui.label("S").classes("logo-mark flex items-center justify-center")
            with ui.column().classes("gap-0"):
                ui.label("AMAT System Matcher").classes("brand-title")
                ui.label("Engineering intelligence").classes("brand-sub")
            ui.space()
            with ui.row().classes("items-center gap-3 desktop-only"):
                ui.icon("verified_user", size="17px").classes("text-green-300")
                with ui.column().classes("gap-0"):
                    ui.label(self.signed_in_username).classes("field-label")
                    ui.label("Agile session active").classes("brand-sub")
            ui.button(icon="help_outline", on_click=self._show_help).props("flat round dense")
            ui.button("Sign out", icon="logout", on_click=self.logout).props("flat no-caps").classes("link-btn")

    def _workflow_selector(self) -> None:
        with ui.row().classes("workflow-row w-full gap-3 items-stretch"):
            self._workflow_card(
                "lookup", "search", "Individual Lookup",
                "Look up one system without uploading a workbook.", "Fastest",
            )
            self._workflow_card(
                "system", "description", "System Type Excel",
                "Populate System Type values in a quote-request workbook.", "Batch",
            )
            self._workflow_card(
                "template", "file_present", "WD Template Excel",
                "Match system numbers to approved WD templates.", "Batch",
            )

    def _workflow_card(
        self, key: str, icon: str, title: str, description: str, badge: str
    ) -> None:
        active = key == self.mode
        card = ui.card().classes(
            f"workflow-card {'active' if active else ''} flex-1 min-w-[240px]"
        ).on("click", lambda _, selected=key: self.select_mode(selected))
        self.workflow_cards[key] = card
        with card:
            with ui.row().classes("w-full items-start no-wrap"):
                ui.icon(icon, size="24px").classes("text-green-300 bg-[#153b30] rounded-lg p-2")
                with ui.column().classes("gap-1 flex-1"):
                    ui.label(title).classes("workflow-title")
                    ui.label(description).classes("workflow-description leading-relaxed")
                ui.badge(badge).props("outline").classes("text-[10px]")

    def select_mode(self, key: str) -> None:
        if self.busy or key == self.mode:
            return
        self.mode = key
        self.render_content.refresh()

    @ui.refreshable_method
    def render_content(self) -> None:
        self.workflow_cards = {}
        if not self.service.signed_in:
            self._render_login()
            return
        self._header()
        with ui.column().classes("page-wrap gap-4"):
            ui.label("SYSTEM CLASSIFICATION").classes("eyebrow")
            ui.label("What do you want to identify?").classes("page-title")
            ui.label(
                "Classify one AMAT system or process an Excel workbook using live Agile BOM data."
            ).classes("subtitle")
            self._workflow_selector()
            ui.element("div").classes("divider my-2")
            if self.mode == "lookup":
                self._render_lookup()
            else:
                mode = WorkflowMode.SYSTEM_TYPE if self.mode == "system" else WorkflowMode.WD_TEMPLATE
                self._render_batch(mode)

    def _render_login(self) -> None:
        with ui.row().classes("w-full grow items-center justify-center p-8"):
            with ui.row().classes("login-card gap-0 no-wrap"):
                with ui.column().classes("login-feature justify-between grow"):
                    with ui.row().classes("items-center gap-3"):
                        ui.label("S").classes("logo-mark flex items-center justify-center")
                        ui.label("AMAT SYSTEM MATCHER").classes("eyebrow")
                    with ui.column().classes("gap-0"):
                        ui.label("Know the system.").classes("hero")
                        ui.label("Choose the right template.").classes("hero hero-accent")
                    with ui.column().classes("gap-1"):
                        ui.label("◇  Private workspace").classes("field-label")
                        ui.label(
                            "Your Agile credentials stay in this private session."
                        ).classes("brand-sub ml-6")
                with ui.column().classes("login-form grow"):
                    ui.label("WELCOME BACK").classes("eyebrow")
                    ui.label("Sign in to Agile").classes("page-title mt-4 mb-4")
                    with ui.column().classes("control-group w-full"):
                        ui.label("Agile Username").classes("field-label")
                        self.username_input = ui.input(
                            placeholder="Enter your username"
                        ).props("outlined hide-bottom-space autocomplete=username").classes(
                            "delta-input w-full"
                        )
                    with ui.column().classes("control-group w-full mt-2"):
                        ui.label("Agile Password").classes("field-label")
                        self.password_input = ui.input(
                            password=True,
                            password_toggle_button=True,
                            placeholder="Enter your password",
                        ).props("outlined hide-bottom-space autocomplete=current-password").classes(
                            "delta-input w-full"
                        )
                        self.password_input.on("keydown.enter", self.login)
                    self.login_button = ui.button(
                        "Sign in   →", on_click=self.login
                    ).classes("primary-btn w-full mt-3").props("no-caps unelevated")
                    ui.space()
                    with ui.row().classes("self-center items-center gap-2"):
                        ui.icon("lock", size="14px").classes("text-green-300")
                        ui.label("Secure connection to Agile PLM").classes("brand-sub")

    async def login(self) -> None:
        assert self.username_input is not None
        assert self.password_input is not None
        assert self.login_button is not None
        username = (self.username_input.value or "").strip()
        password = self.password_input.value or ""
        if not username or not password:
            ui.notify("Enter your Agile username and password.", type="warning")
            return
        self.login_button.disable()
        self.login_button.set_text("Verifying credentials…")
        if self.status_label is not None:
            self.status_label.set_text("Connecting to Agile…")
        try:
            await run.io_bound(self.service.sign_in, username, password)
        except Exception as exc:
            self.password_input.value = ""
            ui.notify(f"Agile sign-in failed: {exc}", type="negative", timeout=9000)
            if self.status_label is not None:
                self.status_label.set_text("Sign-in failed")
            self.login_button.enable()
            self.login_button.set_text("Sign in   →")
            return
        self.password_input.value = ""
        password = ""
        self.signed_in_username = username
        if self.status_label is not None:
            self.status_label.set_text("Workspace online")
        await self.render_content.refresh()

    async def logout(self) -> None:
        if self.busy:
            ui.notify("Cancel or finish the current operation before signing out.", type="warning")
            return
        await run.io_bound(self.service.sign_out)
        self.signed_in_username = ""
        self.lookup_result = None
        self.lookup_feedback = None
        self.layouts.clear()
        self.input_paths.clear()
        self.classifications.clear()
        self.feedback.clear()
        self.output_paths.clear()
        if self.status_label is not None:
            self.status_label.set_text("Signed out")
        await self.render_content.refresh()

    def _render_lookup(self) -> None:
        with ui.card().classes("amat-card w-full p-6"):
            with ui.row().classes("w-full justify-between items-start"):
                with ui.column().classes("gap-1"):
                    ui.label("INDIVIDUAL LOOKUP").classes("eyebrow")
                    ui.label("Find a system match").classes("text-xl font-semibold mt-2")
                    ui.label(
                        "Enter a complete AMAT system number to classify it and find an approved template."
                    ).classes("text-sm muted")
                with ui.badge().props("outline").classes("text-xs gap-1"):
                    ui.icon("verified_user", size="13px")
                    ui.label("Rules-based")
            ui.label("System number").classes("field-label mt-5")
            with ui.row().classes("w-full items-start gap-2 no-wrap"):
                system_input = ui.input(
                    placeholder="Example: 510284-DX-GPB",
                    value=self.lookup_value,
                ).classes("amat-input flex-1").props("outlined dense clearable")
                system_input.on("keydown.enter", lambda: self.lookup(system_input.value))
                ui.button(
                    "Look Up System", icon="search",
                    on_click=lambda: self.lookup(system_input.value),
                ).classes("primary-btn h-[46px]").props("no-caps unelevated")
                ui.button("Clear", on_click=self.clear_lookup).props("flat no-caps").classes("h-[46px]")
            ui.label(
                "Some systems require a live Agile BOM lookup. Letters and leading zeroes are preserved."
            ).classes("text-xs muted")

        if self.busy:
            self._processing_panel()
        if self.lookup_result is not None:
            self._lookup_result_card()
        else:
            with ui.row().classes(
                "w-full items-center gap-2 border border-dashed border-[#385661] rounded-xl p-3"
            ):
                ui.icon("history", size="18px").classes("muted")
                ui.label("Try a known example").classes("text-xs muted")
                for example in ("707844-XA3-GPA", "710001-XP-GP"):
                    ui.button(example, on_click=lambda _, value=example: self.lookup(value)).props(
                        "dense no-caps unelevated"
                    ).classes("bg-[#14272d] text-white text-xs")
                ui.button("Invalid format", on_click=lambda: self.lookup("500678N123-DX-GPB")).props(
                    "dense no-caps unelevated"
                ).classes("bg-[#14272d] text-white text-xs")

    async def lookup(self, value: str | None) -> None:
        if self.busy:
            return
        self.lookup_value = (value or "").strip().upper()
        if not self.lookup_value:
            ui.notify("Enter a system number", type="warning")
            return
        self.lookup_result = None
        self.lookup_feedback = None
        self.busy = True
        self.cancel_event.clear()
        await self.render_content.refresh()
        assert self.progress_timer is not None
        self.progress_timer.activate()
        try:
            self.messages.put("Validating system number")
            self.lookup_result = await run.io_bound(
                self.service.classify_one,
                self.lookup_value,
                progress=self.messages.put,
                cancel_event=self.cancel_event,
            )
        except Exception as exc:
            self._notify(f"Lookup failed: {exc}", type="negative", timeout=8000)
        finally:
            self.progress_timer.deactivate()
            self._drain_progress()
            self.busy = False
            await self.render_content.refresh()

    def clear_lookup(self) -> None:
        if self.busy:
            return
        self.lookup_value = ""
        self.lookup_result = None
        self.lookup_feedback = None
        self.render_content.refresh()

    def _processing_panel(self) -> None:
        with ui.card().classes("amat-card w-full p-5"):
            with ui.row().classes("w-full items-center justify-between"):
                self.progress_label = ui.label("Preparing…").classes("text-sm font-medium")
                ui.button("Cancel", icon="close", on_click=self.cancel_event.set).props(
                    "flat dense no-caps"
                )
            self.progress_bar = ui.linear_progress(value=None).classes("mt-2")
            self.activity_log = ui.log(max_lines=100).classes(
                "w-full h-24 mt-2 bg-[#09151a] text-xs rounded-lg p-2"
            )

    def _drain_progress(self) -> None:
        while not self.messages.empty():
            message = self.messages.get()
            if self.status_label is not None:
                self.status_label.set_text(message)
            if self.progress_label is not None:
                self.progress_label.set_text(message)
            if self.activity_log is not None:
                self.activity_log.push(f"{datetime.now():%H:%M:%S}  {message}")

    def _notify(self, message: str, **kwargs: Any) -> None:
        """Send a notification from a stable client context after UI refreshes."""

        with self.client:
            ui.notify(message, **kwargs)

    def _lookup_result_card(self) -> None:
        assert self.lookup_result is not None
        classification = self.lookup_result
        decision = classification.decision
        result = display_result(classification)
        icon, css, label = _STATUS_STYLE[decision.status]
        system_value = result.system_type
        template_value = result.wd_template
        system_label = "System Type"
        template_label = "WD Template"
        if decision.status == DecisionStatus.VERIFICATION_REQUIRED:
            if self.lookup_feedback is None:
                system_label = "Proposed System Type"
                template_label = "Proposed WD Template"
            elif self.lookup_feedback.outcome == VerificationOutcome.CONFIRMED:
                icon, css, label = "check_circle", "status-success", "Confirmed"
            elif self.lookup_feedback.outcome == VerificationOutcome.REJECTED:
                icon, css, label = "rate_review", "status-warning", "Left unresolved"
                system_value = ""
                template_value = ""
        with ui.card().classes("amat-card w-full p-6"):
            with ui.row().classes("w-full items-start justify-between gap-4"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon(icon, size="30px").classes(css.split()[-1])
                    with ui.column().classes("gap-0"):
                        ui.label(classification.system_number).classes("text-xl font-semibold")
                        ui.label(f"Build type: {classification.build_type or 'Not available'}").classes(
                            "text-xs muted"
                        )
                ui.label(label).classes(f"status-pill {css}")

            if decision.status == DecisionStatus.VERIFICATION_REQUIRED and self.lookup_feedback is None:
                with ui.row().classes("w-full mt-4 p-3 rounded-lg bg-amber-950/30 border border-amber-700"):
                    ui.icon("verified_user").classes("text-amber-400")
                    ui.label(
                        "This coverage-limited result must be verified before downstream use."
                    ).classes("text-sm text-amber-200")

            with ui.row().classes("w-full gap-3 mt-4 items-stretch"):
                self._value_card(system_label, system_value or "No approved result", "category")
                self._value_card(template_label, template_value or "No approved template", "view_quilt")

            parsed = parse_system_number(classification.system_number)
            with ui.row().classes("w-full gap-3 mt-2 items-stretch"):
                with ui.card().classes("metric flex-1 min-w-[300px]"):
                    ui.label("SYSTEM DETAILS").classes("eyebrow")
                    for name, value in (
                        ("Base slot", parsed.base_slot_number),
                        ("Product family", parsed.product_family),
                        ("Chamber", parsed.chamber),
                        ("NSO suffix", parsed.nso_suffix or "Not applicable"),
                    ):
                        with ui.row().classes("w-full justify-between border-b border-[#284452] py-2"):
                            ui.label(name).classes("text-xs muted")
                            ui.label(value or "—").classes("text-xs font-medium")
                with ui.card().classes("metric flex-1 min-w-[300px]"):
                    ui.label("MATCH EVIDENCE").classes("eyebrow")
                    ui.label("; ".join(decision.rule_ids) or "No rule matched").classes(
                        "text-sm font-medium mt-2"
                    )
                    with ui.expansion("View technical evidence", icon="fact_check").classes("w-full"):
                        for line in decision.evidence or ("No evidence recorded",):
                            ui.label(line).classes("text-xs muted")
                        for warning in decision.warnings:
                            ui.label(warning).classes("text-xs text-amber-300")
                        ui.label(
                            f"Ruleset {RULESET_VERSION} · Templates {TEMPLATE_MAP_VERSION}"
                        ).classes("text-[11px] muted mt-2")

            if decision.status == DecisionStatus.VERIFICATION_REQUIRED and self.lookup_feedback is None:
                with ui.row().classes("w-full justify-end gap-2 mt-3"):
                    ui.button("Leave Unresolved", on_click=self.reject_lookup).props("outline no-caps")
                    ui.button("Correct Type", on_click=self.correct_lookup).props("outline no-caps")
                    ui.button("Confirm Result", icon="check", on_click=self.confirm_lookup).classes(
                        "primary-btn"
                    ).props("no-caps unelevated")

    def _value_card(self, title: str, value: str, icon: str) -> None:
        with ui.card().classes("metric flex-1 min-w-[300px]"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon, size="18px").classes("text-green-300")
                ui.label(title.upper()).classes("eyebrow")
            with ui.row().classes("w-full items-center justify-between mt-2 no-wrap"):
                ui.label(value).classes("text-sm font-semibold break-all")
                if not value.startswith("No approved"):
                    ui.button(
                        icon="content_copy",
                        on_click=lambda _, text=value: self._copy(text),
                    ).props("flat round dense")

    async def _copy(self, value: str) -> None:
        await ui.run_javascript(f"navigator.clipboard.writeText({value!r})")
        ui.notify("Copied", type="positive")

    def confirm_lookup(self) -> None:
        self.lookup_feedback = VerificationFeedback(VerificationOutcome.CONFIRMED)
        ui.notify("Result confirmed", type="positive")
        self.render_content.refresh()

    def reject_lookup(self) -> None:
        self.lookup_feedback = VerificationFeedback(VerificationOutcome.REJECTED)
        ui.notify("Result left unresolved", type="warning")
        self.render_content.refresh()

    async def correct_lookup(self) -> None:
        feedback = await self._correction_dialog(self.lookup_result)
        if feedback is not None:
            self.lookup_feedback = feedback
            if feedback.outcome == VerificationOutcome.CORRECTED and self.lookup_result:
                old = self.lookup_result
                corrected = old.decision.__class__(
                    status=DecisionStatus.CLASSIFIED,
                    predicted_system_type=feedback.corrected_system_type,
                    rule_ids=old.decision.rule_ids,
                    evidence=old.decision.evidence,
                    warnings=old.decision.warnings,
                )
                self.lookup_result = old.__class__(
                    old.source_row, old.system_number, old.build_type, corrected
                )
            await self.render_content.refresh()

    async def _correction_dialog(
        self, classification: SystemClassification | None
    ) -> VerificationFeedback | None:
        if classification is None:
            return None
        with ui.dialog() as dialog, ui.card().classes("w-[680px] max-w-[95vw] p-5 amat-card"):
            ui.label("Verify classification").classes("text-lg font-semibold")
            ui.label(classification.system_number).classes("text-sm muted")
            ui.label(f"Proposed: {classification.decision.predicted_system_type}").classes(
                "text-sm mt-2"
            )
            corrected = ui.select(
                options=list(SYSTEM_TYPE_TO_WD_TEMPLATE),
                label="Correct system type",
                with_input=True,
            ).classes("amat-input w-full").props("outlined options-dense")
            notes = ui.textarea(label="Feedback notes").classes("amat-input w-full").props("outlined")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat no-caps")
                ui.button(
                    "Leave Unresolved",
                    on_click=lambda: dialog.submit(
                        VerificationFeedback(VerificationOutcome.REJECTED, notes=notes.value or "")
                    ),
                ).props("outline no-caps")

                def submit_correction() -> None:
                    if corrected.value not in SYSTEM_TYPE_TO_WD_TEMPLATE:
                        ui.notify("Select a canonical system type", type="warning")
                        return
                    dialog.submit(
                        VerificationFeedback(
                            VerificationOutcome.CORRECTED,
                            corrected_system_type=corrected.value,
                            notes=notes.value or "",
                        )
                    )

                ui.button("Use Correction", on_click=submit_correction).classes("primary-btn").props(
                    "no-caps unelevated"
                )
        dialog.open()
        return await dialog

    def _render_batch(self, mode: WorkflowMode) -> None:
        title = "Populate System Types" if mode == WorkflowMode.SYSTEM_TYPE else "Match WD Templates"
        description = (
            "Upload a quote-request .xlsx workbook containing System Number and System Type columns."
            if mode == WorkflowMode.SYSTEM_TYPE
            else "Upload an .xlsx workbook containing a System Number column. The WD Template is written beside it."
        )
        with ui.card().classes("amat-card w-full p-6"):
            ui.label("SYSTEM TYPE EXCEL" if mode == WorkflowMode.SYSTEM_TYPE else "WD TEMPLATE EXCEL").classes(
                "eyebrow"
            )
            ui.label(title).classes("text-xl font-semibold mt-2")
            ui.label(description).classes("text-sm muted")
            ui.upload(
                label="Drop an Excel workbook here or click to browse",
                on_upload=lambda e, selected=mode: self.upload_workbook(selected, e),
                on_rejected=lambda: ui.notify("Use an .xlsx file up to the configured size limit", type="negative"),
                auto_upload=True,
                max_file_size=self.settings.max_upload_mb * 1024 * 1024,
            ).props("accept=.xlsx flat bordered color=primary").classes("upload-zone w-full mt-5")
            note = (
                "Headers are detected within the first 25 rows. The source workbook is never modified."
                if mode == WorkflowMode.SYSTEM_TYPE
                else "Headerless input is supported. An unrelated populated adjacent column will not be overwritten."
            )
            ui.label(note).classes("text-xs muted")

        layout = self.layouts.get(mode)
        if layout is not None:
            self._workbook_summary(mode, layout)
        if self.busy:
            self._processing_panel()
        classifications = self.classifications.get(mode)
        if classifications:
            self._batch_results(mode, classifications)

    async def upload_workbook(self, mode: WorkflowMode, event: events.UploadEventArguments) -> None:
        if self.busy:
            return
        name = Path(event.file.name).name
        if Path(name).suffix.lower() != ".xlsx":
            ui.notify("Only .xlsx workbooks are supported", type="negative")
            return
        target = self.workspace / f"{mode.value.lower()}_{name}"
        try:
            await event.file.save(target)
            layout = await run.io_bound(self.service.load_layout, target, mode)
        except Exception as exc:
            target.unlink(missing_ok=True)
            ui.notify(f"Workbook rejected: {exc}", type="negative", timeout=9000)
            return
        self.input_paths[mode] = target
        self.layouts[mode] = layout
        self.classifications.pop(mode, None)
        self.output_paths.pop(mode, None)
        self.feedback[mode] = {}
        ui.notify(f"Loaded {len(layout.inputs)} system numbers", type="positive")
        await self.render_content.refresh()

    def _workbook_summary(self, mode: WorkflowMode, layout: Any) -> None:
        path = self.input_paths[mode]
        with ui.card().classes("amat-card w-full p-5"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("description", size="30px").classes("text-green-400")
                    with ui.column().classes("gap-0"):
                        ui.label(path.name.split("_", 1)[-1]).classes("text-sm font-semibold")
                        ui.label(f"{path.stat().st_size / 1024:.1f} KB").classes("text-xs muted")
                ui.button("Remove", icon="delete_outline", on_click=lambda: self.remove_workbook(mode)).props(
                    "flat no-caps"
                )
            with ui.row().classes("w-full gap-3 mt-3"):
                self._metric("Worksheet", layout.sheet_name)
                self._metric("Systems", str(len(layout.inputs)))
                self._metric("System column", str(layout.system_column))
                self._metric("Output column", str(layout.output_column))
            if not self.classifications.get(mode):
                label = "Process Workbook" if mode == WorkflowMode.SYSTEM_TYPE else "Find WD Templates"
                ui.button(label, icon="play_arrow", on_click=lambda: self.process_workbook(mode)).classes(
                    "primary-btn mt-4"
                ).props("no-caps unelevated")

    def _metric(self, title: str, value: str) -> None:
        with ui.element("div").classes("metric flex-1 min-w-[125px]"):
            ui.label(title.upper()).classes("eyebrow")
            ui.label(value).classes("text-sm font-semibold mt-1")

    def remove_workbook(self, mode: WorkflowMode) -> None:
        if self.busy:
            return
        path = self.input_paths.pop(mode, None)
        if path:
            path.unlink(missing_ok=True)
        self.layouts.pop(mode, None)
        self.classifications.pop(mode, None)
        self.output_paths.pop(mode, None)
        self.feedback.pop(mode, None)
        self.render_content.refresh()

    async def process_workbook(self, mode: WorkflowMode) -> None:
        if self.busy or mode not in self.layouts:
            return
        self.busy = True
        self.cancel_event.clear()
        self.classifications.pop(mode, None)
        self.output_paths.pop(mode, None)
        await self.render_content.refresh()
        assert self.progress_timer is not None
        self.progress_timer.activate()
        try:
            layout = self.layouts[mode]
            classifications = await run.io_bound(
                self.service.classify_inputs,
                layout.inputs,
                progress=self.messages.put,
                cancel_event=self.cancel_event,
            )
            if self.cancel_event.is_set():
                self._notify("Processing cancelled", type="warning")
                return
            self.classifications[mode] = classifications
            pending = sum(
                c.decision.status == DecisionStatus.VERIFICATION_REQUIRED
                for c in classifications
            )
            self._notify(
                f"Classification complete. {pending} result(s) require verification."
                if pending else "Classification complete",
                type="warning" if pending else "positive",
            )
            if not pending:
                await self.generate_output(mode)
        except Exception as exc:
            self._notify(f"Processing failed: {exc}", type="negative", timeout=10000)
        finally:
            self.progress_timer.deactivate()
            self._drain_progress()
            self.busy = False
            await self.render_content.refresh()

    def _batch_results(
        self, mode: WorkflowMode, classifications: list[SystemClassification]
    ) -> None:
        counts = Counter(c.decision.status for c in classifications)
        with ui.card().classes("amat-card w-full p-5"):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.column().classes("gap-0"):
                    ui.label("PROCESSING RESULTS").classes("eyebrow")
                    ui.label(f"{len(classifications)} systems classified").classes(
                        "text-lg font-semibold mt-1"
                    )
                output = self.output_paths.get(mode)
                if output:
                    ui.button(
                        "Download Workbook", icon="download",
                        on_click=lambda _, path=output: ui.download(path, path.name),
                    ).classes("primary-btn").props("no-caps unelevated")
            with ui.row().classes("w-full gap-3 mt-3"):
                self._metric("Total", str(len(classifications)))
                self._metric("Classified", str(counts[DecisionStatus.CLASSIFIED]))
                self._metric("Verification", str(counts[DecisionStatus.VERIFICATION_REQUIRED]))
                review_count = len(classifications) - counts[DecisionStatus.CLASSIFIED] - counts[DecisionStatus.VERIFICATION_REQUIRED]
                self._metric("Review / errors", str(review_count))

            pending = [
                c for c in classifications
                if c.decision.status == DecisionStatus.VERIFICATION_REQUIRED
                and c.source_row not in self.feedback.get(mode, {})
            ]
            if pending:
                with ui.row().classes(
                    "w-full mt-4 items-center justify-between rounded-lg border border-amber-700 bg-amber-950/30 p-3"
                ):
                    ui.label(f"{len(pending)} result(s) must be reviewed before download").classes(
                        "text-sm text-amber-200"
                    )
                    ui.button(
                        f"Review {len(pending)} Results", icon="fact_check",
                        on_click=lambda: self.review_batch(mode),
                    ).props("no-caps unelevated color=warning")

            columns = [
                {"name": "row", "label": "Row", "field": "row", "align": "left", "sortable": True},
                {"name": "system_number", "label": "System Number", "field": "system_number", "align": "left", "sortable": True},
                {"name": "build_type", "label": "Build", "field": "build_type", "align": "left"},
                {"name": "status", "label": "Status", "field": "status", "align": "left", "sortable": True},
                {"name": "system_type", "label": "System Type", "field": "system_type", "align": "left"},
                {"name": "wd_template", "label": "WD Template", "field": "wd_template", "align": "left"},
                {"name": "rules", "label": "Matched Rules", "field": "rules", "align": "left"},
            ]
            rows = [result_row(c, mode) for c in classifications]
            search = ui.input(placeholder="Search results").props(
                "outlined dense clearable"
            ).classes("amat-input w-72 mt-4")
            table = ui.table(
                columns=columns,
                rows=rows,
                row_key="row",
                pagination={"rowsPerPage": 10, "sortBy": "row"},
                selection="single",
                on_select=lambda e, items=classifications: self.show_selected_evidence(e, items),
            ).classes("amat-table w-full").props("dense flat bordered wrap-cells")
            search.on_value_change(lambda e: table.set_filter(e.value or ""))
            ui.label("Select a row to inspect its evidence and warnings.").classes("text-xs muted")

    async def review_batch(self, mode: WorkflowMode) -> None:
        items = self.classifications.get(mode, [])
        feedback = self.feedback.setdefault(mode, {})
        for classification in items:
            if classification.decision.status != DecisionStatus.VERIFICATION_REQUIRED:
                continue
            if classification.source_row in feedback:
                continue
            response = await self._verification_dialog(classification)
            if response is None:
                self._notify("Verification paused", type="warning")
                await self.render_content.refresh()
                return
            feedback[classification.source_row] = response
        await self.generate_output(mode)
        await self.render_content.refresh()

    async def _verification_dialog(
        self, classification: SystemClassification
    ) -> VerificationFeedback | None:
        with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-[95vw] p-5 amat-card"):
            ui.label("Verify classification").classes("text-lg font-semibold")
            ui.label(f"Workbook row {classification.source_row}").classes("text-xs muted")
            ui.label(classification.system_number).classes("text-base font-semibold")
            ui.label(f"Proposed: {classification.decision.predicted_system_type}").classes("text-sm")
            with ui.expansion("Match evidence", icon="fact_check").classes("w-full"):
                for line in classification.decision.evidence:
                    ui.label(line).classes("text-xs muted")
            corrected = ui.select(
                list(SYSTEM_TYPE_TO_WD_TEMPLATE), label="Correction (optional)", with_input=True
            ).classes("amat-input w-full").props("outlined options-dense")
            notes = ui.textarea(label="Feedback notes").classes("amat-input w-full").props("outlined")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Pause Review", on_click=lambda: dialog.submit(None)).props("flat no-caps")
                ui.button(
                    "Leave Unresolved",
                    on_click=lambda: dialog.submit(
                        VerificationFeedback(VerificationOutcome.REJECTED, notes=notes.value or "")
                    ),
                ).props("outline no-caps")

                def resolve() -> None:
                    if corrected.value:
                        if corrected.value not in SYSTEM_TYPE_TO_WD_TEMPLATE:
                            ui.notify("Select a canonical system type", type="warning")
                            return
                        dialog.submit(
                            VerificationFeedback(
                                VerificationOutcome.CORRECTED,
                                corrected_system_type=corrected.value,
                                notes=notes.value or "",
                            )
                        )
                    else:
                        dialog.submit(
                            VerificationFeedback(VerificationOutcome.CONFIRMED, notes=notes.value or "")
                        )

                ui.button("Confirm Result", icon="check", on_click=resolve).classes("primary-btn").props(
                    "no-caps unelevated"
                )
        dialog.open()
        return await dialog

    async def generate_output(self, mode: WorkflowMode) -> None:
        layout = self.layouts[mode]
        classifications = self.classifications[mode]
        source = self.input_paths[mode]
        suffix = "_system_types.xlsx" if mode == WorkflowMode.SYSTEM_TYPE else "_wd_templates.xlsx"
        output = self.workspace / f"{source.stem}{suffix}"
        try:
            plan = build_update_plan(
                layout,
                classifications,
                mode,
                feedback_by_row=self.feedback.get(mode, {}),
            )
            await run.io_bound(write_value_only_workbook_copy, plan, output)
            self.output_paths[mode] = output
            self._notify(
                f"Workbook ready: {plan.written_count} written, {plan.blank_count} left blank",
                type="positive" if not plan.blank_count else "warning",
                timeout=7000,
            )
        except Exception as exc:
            self._notify(f"Output generation failed: {exc}", type="negative", timeout=10000)

    async def show_selected_evidence(
        self,
        event: events.TableSelectionEventArguments,
        classifications: list[SystemClassification],
    ) -> None:
        if not event.selection:
            return
        row_number = event.selection[0]["row"]
        classification = next(c for c in classifications if c.source_row == row_number)
        decision = classification.decision
        with ui.dialog() as dialog, ui.card().classes("w-[760px] max-w-[95vw] p-5 amat-card"):
            ui.label(classification.system_number).classes("text-lg font-semibold")
            ui.label(decision.status.value.replace("_", " ").title()).classes("text-xs muted")
            ui.separator().classes("my-2")
            ui.label("Matched rules").classes("eyebrow")
            ui.label("; ".join(decision.rule_ids) or "None").classes("text-sm")
            ui.label("Evidence").classes("eyebrow mt-3")
            for line in decision.evidence or ("No evidence recorded",):
                ui.label(line).classes("text-sm muted")
            for warning in decision.warnings:
                ui.label(warning).classes("text-sm text-amber-300")
            ui.button("Close", on_click=dialog.close).props("flat no-caps").classes("self-end")
        dialog.open()
        await dialog

    def _show_help(self) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-[640px] max-w-[95vw] p-5 amat-card"):
            ui.label("AMAT System Matcher").classes("text-lg font-semibold")
            ui.label(
                "Use Individual Lookup for one system, or upload an Excel workbook for batch processing. "
                "Results requiring verification must be confirmed or corrected before they are written."
            ).classes("text-sm muted")
            ui.label(
                "Excel output requires Microsoft Excel on this Windows host so workbook validation, formulas, and formatting are preserved."
            ).classes("text-sm muted")
            ui.label(
                "Your Agile credentials are held only in memory for this session and are cleared when you sign out or disconnect."
            ).classes("text-sm muted")
            ui.button("Close", on_click=dialog.close).props("flat no-caps").classes("self-end")
        dialog.open()


def register_pages(route: str | None = None, settings: AppSettings | None = None) -> None:
    """Register the matcher page in NiceGUI (standalone or within ASA)."""

    selected_settings = settings or SETTINGS
    selected_route = route or selected_settings.route
    if not selected_route.startswith("/"):
        selected_route = "/" + selected_route

    @ui.page(selected_route)
    def system_matcher_page() -> None:
        MatcherPage(selected_settings).build()

