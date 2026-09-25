from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

from .agile import DEFAULT_WSDL_URL


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class AppSettings:
    """Runtime settings shared by the standalone and ASA-hosted variants."""

    host: str = os.getenv("AMAT_MATCHER_HOST", "0.0.0.0")
    port: int = _env_int("AMAT_MATCHER_PORT", 8100)
    route: str = os.getenv("AMAT_MATCHER_ROUTE", "/")
    wsdl_url: str = os.getenv("AMAT_AGILE_WSDL_URL", DEFAULT_WSDL_URL)
    max_upload_mb: int = _env_int("AMAT_MATCHER_MAX_UPLOAD_MB", 50)
    max_workers: int = _env_int("AMAT_MATCHER_WORKERS", 10)


SETTINGS = AppSettings()
