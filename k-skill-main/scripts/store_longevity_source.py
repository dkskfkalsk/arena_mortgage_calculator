"""Access the public store-longevity source and existing mirror metadata."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

DATASET_ID = "15083033"
DATASET_PAGE = f"https://www.data.go.kr/data/{DATASET_ID}/fileData.do"
RENDERED_DATASET_PAGE = f"https://r.jina.ai/{DATASET_PAGE}"
DOWNLOAD_URL = "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={file_id}&fileDetailSn=1"
USER_AGENT = "Mozilla/5.0 (compatible; k-skill-store-longevity-mirror)"
FILE_ID_PATTERN = re.compile(r"FILE_[0-9]{6,}")

FetchText = Callable[[str, Mapping[str, str]], str]
DiscoverFileId = Callable[[], str]


class BinaryResponse(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...

    def read(self, amount: int = -1) -> bytes: ...


class MirrorError(RuntimeError):
    """A source, validation, or publication-preparation failure."""


def request(
    url: str,
    timeout: int,
    headers: Mapping[str, str] | None = None,
) -> BinaryResponse:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    response: BinaryResponse = urllib.request.urlopen(req, timeout=timeout)
    return response


def fetch_text(url: str, headers: Mapping[str, str]) -> str:
    with request(url, timeout=90, headers=headers) as response:
        return response.read().decode("utf-8", "replace")


def extract_file_id(html: str) -> str:
    match = FILE_ID_PATTERN.search(html)
    if match is None:
        raise MirrorError(f"FILE_* identifier not found in {DATASET_PAGE}")
    return match.group(0)


def discover_source_file_id(fetch: FetchText = fetch_text) -> str:
    attempts: list[tuple[str, Mapping[str, str]]] = [
        (DATASET_PAGE, {}),
        (
            RENDERED_DATASET_PAGE,
            {
                "X-Respond-With": "html",
                "X-No-Cache": "true",
                "X-Timeout": "90",
            },
        ),
    ]
    failures: list[str] = []
    for url, headers in attempts:
        try:
            return extract_file_id(fetch(url, headers))
        except (MirrorError, TimeoutError, urllib.error.URLError) as exc:
            failures.append(f"{url}: {exc}")
    raise MirrorError("; ".join(failures))


def resolve_source_file_id(
    explicit_file_id: str | None,
    *,
    discover: DiscoverFileId = discover_source_file_id,
) -> str:
    if explicit_file_id is None:
        return discover()
    if FILE_ID_PATTERN.fullmatch(explicit_file_id) is None:
        raise MirrorError("source file ID must match FILE_<digits>")
    return explicit_file_id


def load_remote_manifest(url: str) -> dict[str, object] | None:
    try:
        with request(url, timeout=30, headers={"Accept": "application/json"}) as response:
            decoded: object = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise MirrorError(f"mirror manifest request failed: {exc}") from exc
    except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise MirrorError(f"mirror manifest request failed: {exc}") from exc
    if not isinstance(decoded, dict):
        raise MirrorError("mirror manifest must be a JSON object")
    payload: dict[str, object] = {}
    for key, value in decoded.items():
        if not isinstance(key, str):
            raise MirrorError("mirror manifest keys must be strings")
        payload[key] = value
    return payload


def download_source_zip(source_file_id: str, path: Path) -> None:
    url = DOWNLOAD_URL.format(file_id=source_file_id)
    try:
        with request(url, timeout=1800) as response, path.open("wb") as output:
            while chunk := response.read(1 << 20):
                _ = output.write(chunk)
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        raise MirrorError(f"source ZIP download failed: {exc}") from exc
