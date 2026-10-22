import csv
import hashlib
import io
import subprocess
import tempfile
import unittest
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import scripts.store_longevity_mirror as mirror
import scripts.store_longevity_source as source

HEADER = [
    "상가업소번호",
    "상호명",
    "상권업종소분류코드",
    "상권업종소분류명",
    "시도명",
    "시군구명",
    "행정동명",
    "도로명주소",
    "지번주소",
    "경도",
    "위도",
]


def make_zip(path: Path) -> None:
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(HEADER)
    writer.writerow([
        "S001",
        "행복문구",
        "G21302",
        "문구용품 소매업",
        "서울특별시",
        "중구",
        "명동",
        "서울 중구 세종대로 1",
        "서울 중구 태평로 1",
        "126.9780",
        "37.5665",
    ])
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("상가정보_서울.csv", csv_buffer.getvalue().encode())


class SourceDiscoveryTest(unittest.TestCase):
    def test_extract_file_id_from_rendered_html(self):
        self.assertEqual(
            source.extract_file_id('<button data-id="FILE_000000003676619">'),
            "FILE_000000003676619",
        )

    def test_direct_failure_uses_rendered_page_fallback(self):
        calls: list[tuple[str, Mapping[str, str]]] = []

        def fetch_text(url: str, headers: Mapping[str, str]) -> str:
            calls.append((url, headers))
            if url == source.DATASET_PAGE:
                raise TimeoutError("timed out")
            return '<button data-id="FILE_000000003676619">'

        self.assertEqual(
            source.discover_source_file_id(fetch_text),
            "FILE_000000003676619",
        )
        self.assertEqual(calls[0][0], source.DATASET_PAGE)
        self.assertEqual(calls[1][0], source.RENDERED_DATASET_PAGE)
        self.assertEqual(calls[1][1]["X-Respond-With"], "html")

    def test_explicit_file_id_bypasses_network_discovery(self):
        def fail_discovery() -> str:
            raise AssertionError("network discovery should not run")

        self.assertEqual(
            source.resolve_source_file_id(
                "FILE_000000003676619",
                discover=fail_discovery,
            ),
            "FILE_000000003676619",
        )

    def test_invalid_explicit_file_id_is_rejected(self):
        with self.assertRaises(source.MirrorError):
            source.resolve_source_file_id("https://attacker.example/file.zip")


class MirrorArtifactTest(unittest.TestCase):
    def test_download_source_snapshot_uses_resilient_curl(self):
        destination = Path("/tmp/source.zip")

        with mock.patch("scripts.store_longevity_mirror.subprocess.run") as run:
            mirror.download_source_snapshot(
                "https://example.test/source.zip",
                destination,
            )

        run.assert_called_once_with(
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
                source.DATASET_PAGE,
                "--output",
                str(destination),
                "https://example.test/source.zip",
            ],
            check=True,
        )

    def test_download_source_snapshot_surfaces_curl_failure(self):
        with mock.patch(
            "scripts.store_longevity_mirror.subprocess.run",
            side_effect=subprocess.CalledProcessError(28, ["curl"]),
        ), self.assertRaisesRegex(source.MirrorError, "source download failed"):
            mirror.download_source_snapshot(
                "https://example.test/source.zip",
                Path("/tmp/source.zip"),
            )

    def test_validate_zip_and_build_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            zip_path = Path(directory) / "snapshot.zip"
            make_zip(zip_path)

            summary = mirror.validate_zip(zip_path)
            manifest = mirror.build_manifest(
                source_file_id="FILE_000000003676619",
                public_base_url="https://pub-c974105a1e4840bcaa264cb2a55d99a1.r2.dev",
                prefix="store-longevity-radar",
                zip_path=zip_path,
                summary=summary,
                now=datetime(2026, 8, 1, tzinfo=UTC),
            )

        self.assertEqual(summary.csv_member_count, 1)
        self.assertEqual(manifest["source_file_id"], "FILE_000000003676619")
        self.assertEqual(
            manifest["object_url"],
            (
                "https://pub-c974105a1e4840bcaa264cb2a55d99a1.r2.dev/"
                "store-longevity-radar/objects/FILE_000000003676619.zip"
            ),
        )
        self.assertEqual(manifest["sha256"], summary.sha256)
        self.assertEqual(manifest["mirrored_at"], "2026-08-01T00:00:00Z")

    def test_same_file_id_skips_download_unless_forced(self):
        manifest = {"source_file_id": "FILE_000000003676619"}
        self.assertFalse(
            mirror.needs_update("FILE_000000003676619", manifest, force=False),
        )
        self.assertTrue(
            mirror.needs_update("FILE_000000003676619", manifest, force=True),
        )


class ManifestHashTest(unittest.TestCase):
    def test_sha256_matches_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.zip"
            _ = path.write_bytes(b"PK-test")
            expected = hashlib.sha256(b"PK-test").hexdigest()
            self.assertEqual(mirror.sha256_file(path), expected)


if __name__ == "__main__":
    _ = unittest.main()
