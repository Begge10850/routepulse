"""Upload the audited RoutePulse analysis window to Amazon S3."""

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

BUCKET_NAME = "routepulse-raw-eu-central-1-9b355f4a"
AWS_PROFILE = "routepulse"
AWS_REGION = "eu-central-1"

INVENTORY_PATH = Path(
    "evidence/collection/analysis_window_inventory.jsonl"
)
SUMMARY_PATH = Path(
    "evidence/collection/analysis_window_summary.json"
)


@dataclass(frozen=True)
class UploadItem:
    """Describe one local file and its intended S3 object."""

    local_path: Path
    object_key: str
    checksum_sha256: str
    content_type: str


def calculate_file_sha256(path: Path) -> str:
    """Calculate a file's SHA-256 checksum in bounded memory."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def load_inventory(path: Path) -> list[dict[str, Any]]:
    """Load and validate records from the audited JSON Lines inventory."""

    records: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as inventory_file:
        for line_number, line in enumerate(inventory_file, start=1):
            stripped_line = line.strip()

            if not stripped_line:
                continue

            try:
                record = json.loads(stripped_line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON on inventory line {line_number}: {error}"
                ) from error

            if not isinstance(record, dict):
                raise TypeError(
                    f"Inventory line {line_number} is not a JSON object"
                )

            records.append(record)

    return records

def build_upload_plan(
    records: list[dict[str, Any]],
) -> list[UploadItem]:
    """Validate audited files and build the complete S3 upload plan."""

    items: list[UploadItem] = []

    for line_number, record in enumerate(records, start=1):
        snapshot_text = record.get("snapshot_path")
        sidecar_text = record.get("sidecar_path")
        expected_checksum = record.get("checksum_sha256")

        if not isinstance(snapshot_text, str):
            raise TypeError(
                f"Inventory line {line_number} has no snapshot path"
            )

        if not isinstance(sidecar_text, str):
            raise TypeError(
                f"Inventory line {line_number} has no sidecar path"
            )

        if not isinstance(expected_checksum, str):
            raise TypeError(
                f"Inventory line {line_number} has no SHA-256 checksum"
            )

        snapshot_path = Path(snapshot_text)
        sidecar_path = Path(sidecar_text)

        if not snapshot_path.is_file():
            raise FileNotFoundError(snapshot_path)

        if not sidecar_path.is_file():
            raise FileNotFoundError(sidecar_path)

        actual_checksum = calculate_file_sha256(snapshot_path)

        if actual_checksum != expected_checksum:
            raise ValueError(
                f"Checksum mismatch for {snapshot_path}"
            )

        sidecar_checksum = calculate_file_sha256(sidecar_path)

        items.append(
            UploadItem(
                local_path=snapshot_path,
                object_key=snapshot_path.relative_to("data").as_posix(),
                checksum_sha256=expected_checksum,
                content_type="application/x-protobuf",
            )
        )
        items.append(
            UploadItem(
                local_path=sidecar_path,
                object_key=sidecar_path.relative_to("data").as_posix(),
                checksum_sha256=sidecar_checksum,
                content_type="application/json",
            )
        )

    for evidence_path, content_type in [
        (INVENTORY_PATH, "application/x-ndjson"),
        (SUMMARY_PATH, "application/json"),
    ]:
        if not evidence_path.is_file():
            raise FileNotFoundError(evidence_path)

        items.append(
            UploadItem(
                local_path=evidence_path,
                object_key=evidence_path.as_posix(),
                checksum_sha256=calculate_file_sha256(evidence_path),
                content_type=content_type,
            )
        )

    return items


def remote_object_matches(s3_client: Any, item: UploadItem) -> bool:
    """Return whether S3 already contains this exact audited object."""

    try:
        response = s3_client.head_object(
            Bucket=BUCKET_NAME,
            Key=item.object_key,
        )
    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code")

        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False

        raise

    remote_checksum = response.get("Metadata", {}).get("sha256")

    if remote_checksum != item.checksum_sha256:
        raise RuntimeError(
            f"S3 object exists with a different checksum: "
            f"{item.object_key}"
        )

    return True


def upload_plan(s3_client: Any, items: list[UploadItem]) -> None:
    """Upload missing objects and refuse conflicting replacements."""

    uploaded = 0
    skipped = 0

    for position, item in enumerate(items, start=1):
        if remote_object_matches(s3_client, item):
            skipped += 1
            print(f"[{position}/{len(items)}] Skipped {item.object_key}")
            continue

        s3_client.upload_file(
            str(item.local_path),
            BUCKET_NAME,
            item.object_key,
            ExtraArgs={
                "ContentType": item.content_type,
                "Metadata": {
                    "sha256": item.checksum_sha256,
                },
            },
        )
        uploaded += 1
        print(f"[{position}/{len(items)}] Uploaded {item.object_key}")

    print(f"Uploaded objects: {uploaded}")
    print(f"Skipped matching objects: {skipped}")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate and upload the audited RoutePulse analysis window"
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Upload files after validation; otherwise perform a dry run",
    )

    return parser.parse_args()


def main() -> None:
    """Validate the inventory and optionally upload it to S3."""

    arguments = parse_arguments()
    records = load_inventory(INVENTORY_PATH)
    items = build_upload_plan(records)
    total_bytes = sum(item.local_path.stat().st_size for item in items)

    print(f"Audited inventory records: {len(records)}")
    print(f"Planned S3 objects: {len(items)}")
    print(f"Planned bytes: {total_bytes}")

    if not arguments.execute:
        print("Dry run complete. No files were uploaded.")
        return

    session = boto3.Session(
        profile_name=AWS_PROFILE,
        region_name=AWS_REGION,
    )
    s3_client = session.client("s3")
    upload_plan(s3_client, items)


if __name__ == "__main__":
    main()