"""Prepare a verified store-longevity-radar snapshot for R2 publication."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import zipfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts.store_longevity_source import (
    DATASET_ID,
    DATASET_PAGE,
    DOWNLOAD_URL,
    MirrorError,
    load_remote_manifest,
    resolve_source_file_id,
)

REQUIRED_COLUMNS = {
    "상가업소번호",
    "상호명",
    "상권업종소분류코드",
    "경도",
    "위도",
}


@dataclass(frozen=True, slots=True)
class ZipSummary:
    size_bytes: int
    sha256: str
    zip_member_count: int
    csv_member_count: int


@dataclass(frozen=True, slots=True)
class PrepareArgs:
    source_file_id: str | None
    manifest_url: str
    public_base_url: str
    prefix: str
    output_dir: str
    github_output: str | None
    force: bool


def needs_update(
    source_file_id: str,
    current_manifest: Mapping[str, object] | None,
    *,
    force: bool,
) -> bool:
    return force or current_manifest is None or current_manifest.get("source_file_id") != source_file_id


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def download_source_snapshot(url: str, path: Path) -> None:
    try:
        subprocess.run(
            [
                "curl",
                "--fail",
                "--show-error",
                "--location",
                "--ipv4",
                "--connect-timeout",
                "30",
                "--retry",
                "20",
                "--retry-all-errors",
                "--retry-delay",
                "30",
                "--retry-max-time",
                "1800",
                "--referer",
                DATASET_PAGE,
                "--output",
                str(path),
                url,
            ],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise MirrorError(f"source download failed: {exc}") from exc


def validate_zip(path: Path) -> ZipSummary:
    try:
        with zipfile.ZipFile(path) as archive:
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise MirrorError(f"corrupt ZIP member: {corrupt_member}")
            members = archive.infolist()
            csv_members = [member for member in members if member.filename.lower().endswith(".csv")]
            if not csv_members:
                raise MirrorError("snapshot ZIP contains no CSV files")
            with archive.open(csv_members[0]) as source:
                reader = csv.reader(io.TextIOWrapper(source, encoding="utf-8-sig", errors="replace"))
                header_row = next(reader, None)
                if header_row is None:
                    raise MirrorError("snapshot CSV has no header")
                header = set(header_row)
            missing = REQUIRED_COLUMNS - header
            if missing:
                raise MirrorError(f"snapshot CSV missing columns: {sorted(missing)}")
    except (OSError, zipfile.BadZipFile) as exc:
        raise MirrorError(f"invalid snapshot ZIP: {exc}") from exc
    return ZipSummary(
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        zip_member_count=len(members),
        csv_member_count=len(csv_members),
    )


def build_manifest(
    *,
    source_file_id: str,
    public_base_url: str,
    prefix: str,
    zip_path: Path,
    summary: ZipSummary,
    now: datetime,
) -> dict[str, object]:
    normalized_base = public_base_url.rstrip("/")
    normalized_prefix = prefix.strip("/")
    object_key = f"{normalized_prefix}/objects/{source_file_id}.zip"
    return {
        "schema_version": 1,
        "dataset_id": DATASET_ID,
        "source_page": DATASET_PAGE,
        "source_file_id": source_file_id,
        "source_download_url": DOWNLOAD_URL.format(file_id=source_file_id),
        "mirrored_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        **asdict(summary),
        "filename": zip_path.name,
        "object_key": object_key,
        "object_url": f"{normalized_base}/{object_key}",
        "version_manifest_key": f"{normalized_prefix}/manifests/{source_file_id}.json",
        "latest_manifest_key": f"{normalized_prefix}/latest.json",
    }


def write_github_output(path: str | None, values: Mapping[str, object]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as output:
        output.writelines(f"{key}={value}\n" for key, value in values.items())


def run(args: PrepareArgs) -> dict[str, object]:
    source_file_id = resolve_source_file_id(args.source_file_id)
    current_manifest = load_remote_manifest(args.manifest_url)
    if not needs_update(source_file_id, current_manifest, force=args.force):
        result: dict[str, object] = {
            "status": "unchanged",
            "source_file_id": source_file_id,
        }
        write_github_output(args.github_output, result)
        return result

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{source_file_id}.zip"
    partial_path = zip_path.with_suffix(".zip.part")
    download_source_snapshot(
        DOWNLOAD_URL.format(file_id=source_file_id),
        partial_path,
    )
    summary = validate_zip(partial_path)
    os.replace(partial_path, zip_path)

    manifest = build_manifest(
        source_file_id=source_file_id,
        public_base_url=args.public_base_url,
        prefix=args.prefix,
        zip_path=zip_path,
        summary=summary,
        now=datetime.now(UTC),
    )
    manifest_path = output_dir / f"{source_file_id}.json"
    _ = manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result = {
        "status": "prepared",
        "source_file_id": source_file_id,
        "zip_path": zip_path,
        "manifest_path": manifest_path,
        "object_key": manifest["object_key"],
        "version_manifest_key": manifest["version_manifest_key"],
        "latest_manifest_key": manifest["latest_manifest_key"],
        "object_url": manifest["object_url"],
    }
    write_github_output(args.github_output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--manifest-url", required=True)
    _ = parser.add_argument("--source-file-id")
    _ = parser.add_argument("--public-base-url", required=True)
    _ = parser.add_argument("--prefix", default="store-longevity-radar")
    _ = parser.add_argument("--output-dir", required=True)
    _ = parser.add_argument("--github-output")
    _ = parser.add_argument("--force", action="store_true")
    namespace = parser.parse_args()
    args = PrepareArgs(
        source_file_id=(
            str(namespace.source_file_id)
            if namespace.source_file_id is not None
            else None
        ),
        manifest_url=str(namespace.manifest_url),
        public_base_url=str(namespace.public_base_url),
        prefix=str(namespace.prefix),
        output_dir=str(namespace.output_dir),
        github_output=(
            str(namespace.github_output)
            if namespace.github_output is not None
            else None
        ),
        force=bool(namespace.force),
    )
    try:
        print(json.dumps(run(args), ensure_ascii=False, default=str))
    except MirrorError as exc:
        raise SystemExit(json.dumps({"status": "unavailable", "note": str(exc)}, ensure_ascii=False)) from None


if __name__ == "__main__":
    main()
