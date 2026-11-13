"""Static observation of a locally materialized Hugging Face Safetensors snapshot.

This module never deserializes tensor payloads and never imports model code.
It reads JSON metadata and the bounded Safetensors header only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any

NSD_SCHEMA = "in-formation-space.neural-structure-description.v0.1"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_HEADER_BYTES = 16 * 1024 * 1024
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
_REVISION_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class NSDError(ValueError):
    """Raised when a model snapshot cannot be observed within the NSD contract."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NSDError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise NSDError(f"non-finite JSON number is not accepted: {value}")


def _parse_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NSDError(f"{label} is not valid UTF-8 JSON: {exc}") from exc


def _read_json_file(path: Path, label: str) -> tuple[Any, bytes]:
    size = path.stat().st_size
    if size > MAX_JSON_BYTES:
        raise NSDError(f"{label} exceeds the {MAX_JSON_BYTES}-byte JSON limit")
    raw = path.read_bytes()
    return _parse_json(raw, label), raw


def _safe_snapshot_file(root: Path, relative: str) -> Path:
    """Resolve a snapshot-relative regular file without following symlinks."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise NSDError("snapshot file path must be a non-empty POSIX relative path")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or any(part in ("", ".", "..") for part in relative.split("/")):
        raise NSDError(f"unsafe snapshot-relative path: {relative!r}")

    candidate = root
    for part in posix.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise NSDError(f"snapshot path contains a symbolic link: {relative!r}")

    if not candidate.is_file():
        raise NSDError(f"snapshot file is missing or not a regular file: {relative!r}")
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise NSDError(f"snapshot path escapes its root: {relative!r}") from exc
    if not stat.S_ISREG(candidate.stat().st_mode):
        raise NSDError(f"snapshot path is not a regular file: {relative!r}")
    return candidate


def _require_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise NSDError(f"{label} must be a non-negative integer")
    return value


def read_safetensors_header(path: Path, relative_path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read and validate one Safetensors header, never reading tensor data."""
    file_size = path.stat().st_size
    if file_size < 8:
        raise NSDError(f"{relative_path}: file is shorter than the 8-byte header prefix")

    with path.open("rb") as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise NSDError(f"{relative_path}: truncated header prefix")
        header_length = int.from_bytes(prefix, byteorder="little", signed=False)
        if header_length < 2:
            raise NSDError(f"{relative_path}: header length is too small")
        if header_length > MAX_HEADER_BYTES:
            raise NSDError(
                f"{relative_path}: header exceeds the {MAX_HEADER_BYTES}-byte safety limit"
            )
        if 8 + header_length > file_size:
            raise NSDError(f"{relative_path}: declared header extends past end of file")
        header_raw = stream.read(header_length)
        if len(header_raw) != header_length:
            raise NSDError(f"{relative_path}: truncated Safetensors header")

    header = _parse_json(header_raw.rstrip(b" "), f"{relative_path} header")
    if not isinstance(header, dict):
        raise NSDError(f"{relative_path}: Safetensors header must be an object")

    metadata = header.pop("__metadata__", {})
    if not isinstance(metadata, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in metadata.items()
    ):
        raise NSDError(f"{relative_path}: __metadata__ must map strings to strings")

    data_size = file_size - 8 - header_length
    tensors: list[dict[str, Any]] = []
    ranges: list[tuple[int, int, str]] = []
    for name, entry in header.items():
        if not isinstance(name, str) or not name:
            raise NSDError(f"{relative_path}: tensor names must be non-empty strings")
        if not isinstance(entry, dict) or set(entry) != {"dtype", "shape", "data_offsets"}:
            raise NSDError(f"{relative_path}: tensor {name!r} has an unsupported header shape")
        dtype = entry["dtype"]
        shape = entry["shape"]
        offsets = entry["data_offsets"]
        if not isinstance(dtype, str) or not dtype:
            raise NSDError(f"{relative_path}: tensor {name!r} has an invalid dtype")
        if not isinstance(shape, list):
            raise NSDError(f"{relative_path}: tensor {name!r} shape must be an array")
        normalized_shape = [
            _require_nonnegative_int(dimension, f"{relative_path}:{name} shape")
            for dimension in shape
        ]
        if (
            not isinstance(offsets, list)
            or len(offsets) != 2
            or any(type(value) is not int for value in offsets)
        ):
            raise NSDError(f"{relative_path}: tensor {name!r} offsets must be two integers")
        start, end = offsets
        if start < 0 or end < start or end > data_size:
            raise NSDError(f"{relative_path}: tensor {name!r} offsets exceed the data section")
        ranges.append((start, end, name))
        tensors.append(
            {
                "name": name,
                "dtype": dtype,
                "shape": normalized_shape,
                "shard": relative_path,
                "data_offsets": [start, end],
                "data_bytes": end - start,
            }
        )

    if not tensors:
        raise NSDError(f"{relative_path}: no tensor entries were found")
    previous_end = 0
    for start, end, name in sorted(ranges):
        if start < previous_end:
            raise NSDError(f"{relative_path}: tensor data ranges overlap at {name!r}")
        previous_end = max(previous_end, end)

    header_digest = hashlib.sha256(prefix + header_raw).hexdigest()
    return tensors, {
        "path": relative_path,
        "role": "safetensors-shard",
        "size_bytes": file_size,
        "sha256": header_digest,
        "sha256_scope": "8-byte-prefix-and-header-only",
        "header_bytes": header_length,
        "data_bytes": data_size,
        "metadata": metadata,
    }


def inspect_snapshot(
    snapshot_dir: str | Path,
    *,
    repository: str,
    revision: str,
    license_id: str | None = None,
) -> dict[str, Any]:
    """Build an NSD v0.1 observation from a pinned local model snapshot.

    The revision must be the immutable 40-hex Git commit SHA resolved for the
    external repository. The caller supplies license_id explicitly; this
    reader does not infer or adjudicate licensing from model-card prose.
    """
    if not isinstance(repository, str) or not _REPOSITORY_RE.fullmatch(repository):
        raise NSDError("repository must have the form 'owner/name'")
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
        raise NSDError("revision must be an immutable 40-character Git commit SHA")
    if license_id is not None and (
        not isinstance(license_id, str) or not license_id.strip()
    ):
        raise NSDError("license_id must be a non-empty string when supplied")

    root = Path(snapshot_dir).resolve(strict=True)
    if not root.is_dir():
        raise NSDError("snapshot_dir must identify a directory")

    config_path = _safe_snapshot_file(root, "config.json")
    config, config_raw = _read_json_file(config_path, "config.json")
    if not isinstance(config, dict):
        raise NSDError("config.json must contain a JSON object")

    files: list[dict[str, Any]] = [
        {
            "path": "config.json",
            "role": "configuration",
            "size_bytes": len(config_raw),
            "sha256": hashlib.sha256(config_raw).hexdigest(),
            "sha256_scope": "entire-file",
        }
    ]

    index_relative = "model.safetensors.index.json"
    index_path = root / index_relative
    weight_map: dict[str, str] | None = None
    if index_path.exists() or index_path.is_symlink():
        index_path = _safe_snapshot_file(root, index_relative)
        index, index_raw = _read_json_file(index_path, index_relative)
        if not isinstance(index, dict) or not isinstance(index.get("weight_map"), dict):
            raise NSDError("Safetensors index must contain a weight_map object")
        candidate_map = index["weight_map"]
        if not candidate_map:
            raise NSDError("Safetensors weight_map must not be empty")
        if any(
            not isinstance(name, str) or not name
            or not isinstance(shard, str) or not shard
            for name, shard in candidate_map.items()
        ):
            raise NSDError("Safetensors weight_map entries must map tensor names to paths")
        weight_map = dict(candidate_map)
        files.append(
            {
                "path": index_relative,
                "role": "tensor-index",
                "size_bytes": len(index_raw),
                "sha256": hashlib.sha256(index_raw).hexdigest(),
                "sha256_scope": "entire-file",
            }
        )
        shard_names = sorted(set(weight_map.values()))
    else:
        shard_names = sorted(
            path.name for path in root.glob("*.safetensors") if path.is_file()
        )

    if not shard_names:
        raise NSDError("snapshot contains no Safetensors shards")

    tensor_manifest: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for shard_name in shard_names:
        shard_path = _safe_snapshot_file(root, shard_name)
        tensors, file_record = read_safetensors_header(shard_path, shard_name)
        files.append(file_record)
        for tensor in tensors:
            name = tensor["name"]
            if name in seen_names:
                raise NSDError(f"tensor name occurs in more than one shard: {name!r}")
            seen_names.add(name)
            tensor_manifest.append(tensor)

    if weight_map is not None:
        expected = set(weight_map)
        actual = seen_names
        if expected != actual:
            missing = sorted(expected - actual)
            unexpected = sorted(actual - expected)
            raise NSDError(
                "Safetensors index does not match shard headers "
                f"(missing={missing[:5]}, unexpected={unexpected[:5]})"
            )
        for tensor in tensor_manifest:
            if weight_map[tensor["name"]] != tensor["shard"]:
                raise NSDError(
                    f"Safetensors index assigns {tensor['name']!r} to the wrong shard"
                )

    tensor_manifest.sort(key=lambda tensor: tensor["name"])
    dtype_names = sorted({tensor["dtype"] for tensor in tensor_manifest})
    name_roots = sorted({tensor["name"].split(".", 1)[0] for tensor in tensor_manifest})

    return {
        "schema": NSD_SCHEMA,
        "source": {
            "repository": repository,
            "revision": revision.lower(),
            "license_id": license_id,
        },
        "observed": {
            "configuration": config,
            "files": files,
            "weight_map": dict(sorted(weight_map.items())) if weight_map is not None else None,
            "tensor_manifest": tensor_manifest,
        },
        "inferred": {
            "tensor_count": len(tensor_manifest),
            "shard_count": len(shard_names),
            "dtypes": dtype_names,
            "tensor_name_roots": name_roots,
        },
        "generated": {
            "architecture_graph": None,
            "parameter_rules": [],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect config.json and Safetensors headers without loading tensors or executing model code."
    )
    parser.add_argument("--snapshot", required=True, help="Local snapshot directory")
    parser.add_argument("--repository", required=True, help="Source repository, e.g. org/model")
    parser.add_argument("--revision", required=True, help="Immutable 40-character source commit SHA")
    parser.add_argument("--license-id", help="Explicitly recorded source license identifier")
    parser.add_argument("--output", help="Write NSD JSON to this path instead of stdout")
    args = parser.parse_args(argv)

    try:
        description = inspect_snapshot(
            args.snapshot,
            repository=args.repository,
            revision=args.revision,
            license_id=args.license_id,
        )
        rendered = json.dumps(description, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(rendered)
    except (NSDError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
