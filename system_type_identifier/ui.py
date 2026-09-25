"""Backward-compatible standalone entry point for the NiceGUI interface."""

from nicegui import ui

from .config import SETTINGS
from .web_ui import register_pages


def run_app() -> None:
    register_pages(settings=SETTINGS)
    ui.run(
        host=SETTINGS.host,
        port=SETTINGS.port,
        title="AMAT System Matcher",
        dark=True,
        show=False,
        reload=False,
        favicon="⚡",
    )
