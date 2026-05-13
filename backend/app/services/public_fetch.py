from __future__ import annotations

import hashlib
import json
import socket
import ssl
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError


DEFAULT_USER_AGENT = "data-center-power-risk-public-discovery/0.1"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_BYTES = 1_000_000
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


@dataclass
class FetchResult:
    url: str
    ok: bool
    status_code: int | None
    content_type: str | None
    text: str | None
    content_hash: str | None
    fetched_at: str
    error_type: str | None = None
    error_message: str | None = None
    final_url: str | None = None
    insecure_fetch: bool = False
    attempts: int = 1
    bytes_read: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PublicFetchClient:
    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = 1,
        retry_backoff_seconds: float = 0.5,
        max_bytes: int = DEFAULT_MAX_BYTES,
        allow_insecure_fetch: bool = False,
    ):
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = retry_backoff_seconds
        self.max_bytes = max_bytes
        self.allow_insecure_fetch = allow_insecure_fetch

    def fetch(self, url: str) -> FetchResult:
        attempts = self.max_retries + 1
        last_result: FetchResult | None = None
        for attempt in range(1, attempts + 1):
            result = self._fetch_once(url, attempt=attempt)
            if result.ok or not self._should_retry(result):
                return result
            last_result = result
            if attempt < attempts:
                time.sleep(self.retry_backoff_seconds * attempt)
        return last_result or self._error_result(url, "unknown_error", "fetch did not run", attempts=0)

    def _fetch_once(self, url: str, *, attempt: int) -> FetchResult:
        req = request.Request(url, headers={"User-Agent": self.user_agent})
        context = self._ssl_context()
        try:
            with request.urlopen(req, timeout=self.timeout_seconds, context=context) as response:
                status_code = getattr(response, "status", None) or response.getcode()
                content_type = response.headers.get("Content-Type")
                raw = response.read(self.max_bytes)
                text = self._decode_text(raw, content_type)
                return FetchResult(
                    url=url,
                    ok=200 <= int(status_code) < 400,
                    status_code=int(status_code),
                    content_type=content_type,
                    text=text,
                    content_hash=hashlib.sha256(raw).hexdigest(),
                    fetched_at=self._now(),
                    final_url=response.geturl(),
                    insecure_fetch=self.allow_insecure_fetch,
                    attempts=attempt,
                    bytes_read=len(raw),
                    error_type=None if 200 <= int(status_code) < 400 else "http_status_error",
                    error_message=None if 200 <= int(status_code) < 400 else f"HTTP {status_code}",
                )
        except HTTPError as exc:
            error_type = "transient_http_error" if exc.code in TRANSIENT_STATUS_CODES else "http_status_error"
            return self._error_result(
                url,
                error_type,
                f"HTTP {exc.code}",
                attempts=attempt,
                status_code=exc.code,
                content_type=exc.headers.get("Content-Type") if exc.headers else None,
            )
        except URLError as exc:
            reason = exc.reason
            if isinstance(reason, ssl.SSLError):
                return self._error_result(
                    url,
                    "ssl_certificate_error",
                    str(reason),
                    attempts=attempt,
                )
            if isinstance(reason, socket.timeout):
                return self._error_result(url, "timeout", str(reason), attempts=attempt)
            return self._error_result(url, "network_error", str(reason), attempts=attempt)
        except ssl.SSLError as exc:
            return self._error_result(url, "ssl_certificate_error", str(exc), attempts=attempt)
        except TimeoutError as exc:
            return self._error_result(url, "timeout", str(exc), attempts=attempt)

    def _ssl_context(self) -> ssl.SSLContext:
        if self.allow_insecure_fetch:
            return ssl._create_unverified_context()
        try:
            import certifi  # type: ignore

            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return ssl.create_default_context()

    def _decode_text(self, raw: bytes, content_type: str | None) -> str | None:
        if content_type and not self._is_text_content(content_type):
            return None
        charset = "utf-8"
        if content_type and "charset=" in content_type:
            charset = content_type.rsplit("charset=", 1)[-1].split(";", 1)[0].strip()
        return raw.decode(charset or "utf-8", errors="replace")

    def _is_text_content(self, content_type: str) -> bool:
        normalized = content_type.lower()
        return (
            normalized.startswith("text/")
            or "html" in normalized
            or "json" in normalized
            or "xml" in normalized
        )

    def _should_retry(self, result: FetchResult) -> bool:
        return result.error_type in {"timeout", "network_error", "transient_http_error"} or (
            result.status_code in TRANSIENT_STATUS_CODES
        )

    def _error_result(
        self,
        url: str,
        error_type: str,
        error_message: str,
        *,
        attempts: int,
        status_code: int | None = None,
        content_type: str | None = None,
    ) -> FetchResult:
        return FetchResult(
            url=url,
            ok=False,
            status_code=status_code,
            content_type=content_type,
            text=None,
            content_hash=None,
            fetched_at=self._now(),
            error_type=error_type,
            error_message=error_message,
            insecure_fetch=self.allow_insecure_fetch,
            attempts=attempts,
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def write_fetch_result(output_dir: Path, result: FetchResult) -> Path:
    destination = output_dir / (result.content_hash or hashlib.sha256(result.url.encode("utf-8")).hexdigest())
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "metadata.json").write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    if result.text is not None:
        (destination / "content.txt").write_text(result.text, encoding="utf-8")
    return destination
