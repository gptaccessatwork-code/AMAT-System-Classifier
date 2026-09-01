from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
import threading
from typing import Any

from lxml import etree
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client, Settings, helpers
from zeep.transports import Transport

from .models import BomItem, BomSnapshot, ProgressCallback


DEFAULT_WSDL_URL = (
    "http://pagapps1.ichorsystems.com:7001/"
    "CoreService/services/Table?wsdl"
)
DEFAULT_CREDENTIALS_PATH = Path(__file__).resolve().parents[2] / "script_credentials.json"


class AgileConnectionError(RuntimeError):
    pass


class AgileBomError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgileCredentials:
    username: str
    password: str


def load_script_credentials(path: str | Path = DEFAULT_CREDENTIALS_PATH) -> AgileCredentials:
    credentials_path = Path(path)
    try:
        payload = json.loads(credentials_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AgileConnectionError(
            f"Credential file not found: {credentials_path}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AgileConnectionError(
            f"Unable to read credential file {credentials_path}: {exc}"
        ) from exc

    username = str(payload.get("AGILE_USER") or "").strip()
    password = str(payload.get("AGILE_PASS") or "")
    missing = [
        key
        for key, value in (("AGILE_USER", username), ("AGILE_PASS", password))
        if not value
    ]
    if missing:
        raise AgileConnectionError(
            f"Credential file is missing populated keys: {', '.join(missing)}"
        )
    return AgileCredentials(username, password)


@dataclass(frozen=True)
class _DirectBomResult:
    items: tuple[BomItem, ...]


class AgileBomClient:
    """Small, classification-focused client for the Agile BOM SOAP table."""

    def __init__(
        self,
        username: str,
        password: str,
        wsdl_url: str = DEFAULT_WSDL_URL,
        timeout_seconds: int = 45,
    ) -> None:
        if not username.strip() or not password:
            raise AgileConnectionError("Agile username and password are required")
        self.wsdl_url = wsdl_url.strip()
        self._request_wait_seconds = max(timeout_seconds * 2, 30)
        self._session = Session()
        self._session.auth = HTTPBasicAuth(username.strip(), password)
        self._transport = Transport(
            session=self._session,
            timeout=timeout_seconds,
            operation_timeout=timeout_seconds,
        )
        self._settings = Settings(strict=False, xml_huge_tree=True)
        self._direct_cache: dict[str, _DirectBomResult] = {}
        self._direct_failures: dict[str, Exception] = {}
        self._inflight: dict[str, threading.Event] = {}
        self._cache_lock = threading.Lock()
        try:
            self._client = Client(
                self.wsdl_url,
                transport=self._transport,
                settings=self._settings,
            )
            namespace = "http://xmlns.oracle.com/AgileObjects/Core/Table/V1"
            self._request_table_type = self._client.get_type(
                f"{{{namespace}}}RequestTableType"
            )
            self._load_table_request_type = self._client.get_type(
                f"{{{namespace}}}LoadTableRequestType"
            )
        except Exception as exc:
            raise AgileConnectionError(f"Unable to initialize Agile WSDL client: {exc}") from exc

    @classmethod
    def from_script_credentials(
        cls,
        wsdl_url: str = DEFAULT_WSDL_URL,
        credentials_path: str | Path = DEFAULT_CREDENTIALS_PATH,
        timeout_seconds: int = 45,
    ) -> "AgileBomClient":
        credentials = load_script_credentials(credentials_path)
        return cls(
            credentials.username,
            credentials.password,
            wsdl_url=wsdl_url,
            timeout_seconds=timeout_seconds,
        )

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._direct_cache.clear()
            self._direct_failures.clear()

    def fetch_bom(
        self,
        root_part_number: str,
        max_depth: int | None,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        max_items: int = 50_000,
    ) -> BomSnapshot:
        root = root_part_number.strip().upper()
        queue: deque[tuple[str, int, tuple[str, ...]]] = deque([(root, 0, (root,))])
        items: list[BomItem] = []
        errors: list[str] = []
        warnings: list[str] = []

        while queue:
            if cancel_event is not None and cancel_event.is_set():
                errors.append("BOM retrieval cancelled")
                break

            parent, parent_depth, path = queue.popleft()
            if max_depth is not None and parent_depth >= max_depth:
                continue
            if progress:
                progress(f"Retrieving Agile BOM: {parent} (level {parent_depth + 1})")

            try:
                direct_items = self._load_direct_children(parent)
            except Exception as exc:
                errors.append(f"{parent}: {exc}")
                continue

            for direct in direct_items:
                child_path = path + (direct.part_number,)
                item = BomItem(
                    parent_part_number=parent,
                    part_number=direct.part_number,
                    description=direct.description,
                    category=direct.category,
                    local_quantity=direct.local_quantity,
                    depth=parent_depth + 1,
                    path=child_path,
                )
                items.append(item)
                if len(items) >= max_items:
                    errors.append(f"BOM exceeded safety limit of {max_items} rows")
                    queue.clear()
                    break
                if direct.part_number in path:
                    warnings.append("Cycle skipped: " + " -> ".join(child_path))
                    continue
                if direct.category.strip().lower() == "document":
                    continue
                queue.append((direct.part_number, parent_depth + 1, child_path))

        return BomSnapshot(
            root_part_number=root,
            items=tuple(items),
            complete=not errors,
            requested_depth=max_depth,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def _load_direct_children(self, parent_part_number: str) -> tuple[BomItem, ...]:
        parent = parent_part_number.strip().upper()
        with self._cache_lock:
            cached = self._direct_cache.get(parent)
            if cached is not None:
                return cached.items
            failure = self._direct_failures.get(parent)
            if failure is not None:
                raise AgileBomError(str(failure)) from failure
            event = self._inflight.get(parent)
            if event is None:
                event = threading.Event()
                self._inflight[parent] = event
                owns_request = True
            else:
                owns_request = False

        if not owns_request:
            if not event.wait(timeout=self._request_wait_seconds):
                raise AgileBomError("Timed out waiting for a concurrent BOM request")
            with self._cache_lock:
                cached = self._direct_cache.get(parent)
                if cached is not None:
                    return cached.items
                failure = self._direct_failures.get(parent)
            if failure is not None:
                raise AgileBomError(str(failure)) from failure
            raise AgileBomError("Concurrent BOM request ended without a result")

        try:
            table_request = self._request_table_type(
                classIdentifier="Part",
                objectNumber=parent,
                tableIdentifier="BOM",
            )
            load_request = self._load_table_request_type(tableRequest=[table_request])
            response = self._client.service.loadTable(load_request)
            payload = helpers.serialize_object(response)
        except Exception as exc:
            error = AgileBomError(f"loadTable failed: {exc}")
            with self._cache_lock:
                self._direct_failures[parent] = error
                self._inflight.pop(parent, event).set()
            raise error from exc

        try:
            parsed: list[BomItem] = []
            for table in (payload or {}).get("tableContents", []) or []:
                for row in table.get("row", []) or []:
                    item = self._parse_row(parent, row)
                    if item is not None:
                        parsed.append(item)
        except Exception as exc:
            error = AgileBomError(f"Unable to parse BOM response: {exc}")
            with self._cache_lock:
                self._direct_failures[parent] = error
                self._inflight.pop(parent, event).set()
            raise error from exc
        result = _DirectBomResult(tuple(parsed))
        with self._cache_lock:
            self._direct_cache[parent] = result
            self._inflight.pop(parent, event).set()
        return result.items

    @staticmethod
    def _parse_row(parent: str, row: dict[str, Any]) -> BomItem | None:
        referent = row.get("objectReferentId") or {}
        part_number = str(referent.get("objectName") or "").strip().upper()
        if not part_number:
            return None

        quantity = 1.0
        description = ""
        category = ""
        for element in row.get("_value_1", []) or []:
            try:
                local_name = etree.QName(element.tag).localname.lower()
                value = "".join(element.itertext()).strip()
            except (AttributeError, TypeError, ValueError):
                continue
            if "qty" in local_name:
                try:
                    quantity = float(value) if value else 1.0
                except ValueError:
                    quantity = 1.0
            elif "itemdescription" in local_name or "desc" in local_name:
                description = value
            elif "itemcategory" in local_name or "template" in local_name:
                category = _clean_category(value)

        return BomItem(
            parent_part_number=parent,
            part_number=part_number,
            description=description,
            category=category,
            local_quantity=quantity,
            depth=1,
            path=(parent, part_number),
        )


def _clean_category(value: str) -> str:
    upper = value.upper()
    if "PURCH" in upper:
        return "Purch"
    if "PHANTOM" in upper:
        return "Phantom"
    if "DOCUMENT" in upper:
        return "Document"
    return value.strip()
