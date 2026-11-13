"""Read-only Hugging Face Hub observer using bounded HTTP byte ranges.

Only public repository metadata, config/index JSON, and Safetensors headers
are fetched. Tensor payload bytes are never requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

try:
    from .nsd import (
        MAX_HEADER_BYTES,
        MAX_JSON_BYTES,
        NSD_SCHEMA,
        NSDError,
        _REPOSITORY_RE,
        _REVISION_RE,
        _parse_json,
        parse_safetensors_header_bytes,
    )
except ImportError:  # direct unittest discovery from this directory
    from nsd import (
        MAX_HEADER_BYTES,
        MAX_JSON_BYTES,
        NSD_SCHEMA,
        NSDError,
        _REPOSITORY_RE,
        _REVISION_RE,
        _parse_json,
        parse_safetensors_header_bytes,
    )

DEFAULT_ENDPOINT = "https://huggingface.co"
_USER_AGENT = "In-Formation-Space-HFR-001/0.1"
_CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
Opener = Callable[..., Any]


def _header_value(headers: Any, name: str) -> str | None:
    for key, value in headers.items():
        if str(key).lower() == name.lower():
            return str(value)
    return None


def _status(response: Any) -> int:
    value = getattr(response, "status", None)
    if value is None:
        value = response.getcode()
    return int(value)


def _check_https_response(response: Any, requested_url: str) -> None:
    final_url = response.geturl() if hasattr(response, "geturl") else requested_url
    if urlparse(final_url).scheme.lower() != "https":
        raise NSDError("Hub request redirected to a non-HTTPS URL")


def _open(request: Request, *, timeout: float, opener: Opener | None) -> Any:
    selected = opener or urlopen
    try:
        return selected(request, timeout=timeout)
    except (HTTPError, URLError, OSError) as exc:
        raise NSDError(f"Hub request failed: {exc}") from exc


def _read_small_response(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    opener: Opener | None,
) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": _USER_AGENT,
        },
        method="GET",
    )
    with _open(request, timeout=timeout, opener=opener) as response:
        _check_https_response(response, url)
        if _status(response) != 200:
            raise NSDError(f"expected HTTP 200 for metadata file, received {_status(response)}")
        length = _header_value(response.headers, "Content-Length")
        if length is not None:
            try:
                if int(length) > max_bytes:
                    raise NSDError(f"metadata response exceeds the {max_bytes}-byte limit")
            except ValueError as exc:
                raise NSDError("metadata Content-Length is invalid") from exc
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise NSDError(f"metadata response exceeds the {max_bytes}-byte limit")
        return payload


def _read_json_url(
    url: str,
    *,
    label: str,
    timeout: float,
    opener: Opener | None,
) -> tuple[Any, bytes]:
    raw = _read_small_response(
        url,
        timeout=timeout,
        max_bytes=MAX_JSON_BYTES,
        opener=opener,
    )
    return _parse_json(raw, label), raw


def _read_exact_range(
    url: str,
    start: int,
    end: int,
    *,
    timeout: float,
    opener: Opener | None,
) -> tuple[bytes, int]:
    if start < 0 or end < start:
        raise NSDError("invalid requested byte range")
    expected_size = end - start + 1
    request = Request(
        url,
        headers={
            "Range": f"bytes={start}-{end}",
            "Accept-Encoding": "identity",
            "User-Agent": _USER_AGENT,
        },
        method="GET",
    )
    with _open(request, timeout=timeout, opener=opener) as response:
        _check_https_response(response, url)
        status = _status(response)
        if status != 206:
            raise NSDError(
                f"range request {start}-{end} was not honored (HTTP {status}); "
                "refusing a possible full-file response"
            )
        value = _header_value(response.headers, "Content-Range")
        match = _CONTENT_RANGE_RE.fullmatch(value or "")
        if match is None:
            raise NSDError("range response has no valid Content-Range")
        actual_start, actual_end, total_size = map(int, match.groups())
        if actual_start != start or actual_end != end or total_size < end + 1:
            raise NSDError("range response Content-Range does not match the requested interval")
        length = _header_value(response.headers, "Content-Length")
        if length is not None and int(length) != expected_size:
            raise NSDError("range response Content-Length does not match the requested interval")
        payload = response.read(expected_size + 1)
        if len(payload) != expected_size:
            raise NSDError("range response body length does not match the requested interval")
        return payload, total_size


def _safe_hub_path(relative: str) -> str:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise NSDError("Hub file path must be a non-empty POSIX relative path")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in ("", ".", "..") for part in relative.split("/")):
        raise NSDError(f"unsafe Hub repository path: {relative!r}")
    return path.as_posix()


def _model_file_url(endpoint: str, repository: str, revision: str, path: str) -> str:
    repo_part = quote(repository, safe="/")
    path_part = quote(_safe_hub_path(path), safe="/")
    return f"{endpoint}/{repo_part}/resolve/{revision}/{path_part}"


def _sibling_names(info: dict[str, Any]) -> set[str]:
    siblings = info.get("siblings")
    if not isinstance(siblings, list):
        raise NSDError("Hub model metadata does not contain a siblings array")
    names: set[str] = set()
    for sibling in siblings:
        if isinstance(sibling, str):
            name = sibling
        elif isinstance(sibling, dict):
            name = sibling.get("rfilename")
        else:
            name = None
        if not isinstance(name, str) or not name:
            raise NSDError("Hub model metadata contains an invalid sibling entry")
        name = _safe_hub_path(name)
        if name in names:
            raise NSDError(f"Hub model metadata repeats a file path: {name!r}")
        names.add(name)
    return names


def inspect_huggingface_model(
    repository: str,
    revision: str,
    *,
    license_id: str | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 20.0,
    opener: Opener | None = None,
) -> dict[str, Any]:
    """Observe a public Hugging Face model at an immutable commit without downloading weights.

    The caller must provide a 40-character commit SHA. The Hub's resolved SHA
    is checked against it. Model metadata/config/index JSON are bounded reads;
    each Safetensors shard is queried only for its 8-byte prefix and header.
    """
    if not isinstance(repository, str) or not _REPOSITORY_RE.fullmatch(repository):
        raise NSDError("repository must have the form 'owner/name'")
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
        raise NSDError("revision must be an immutable 40-character Git commit SHA")
    if license_id is not None and (
        not isinstance(license_id, str) or not license_id.strip()
    ):
        raise NSDError("license_id must be a non-empty string when supplied")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise NSDError("timeout must be a positive number")
    if not isinstance(endpoint, str) or urlparse(endpoint).scheme.lower() != "https":
        raise NSDError("Hub endpoint must use HTTPS")
    endpoint = endpoint.rstrip("/")

    repository_part = quote(repository, safe="/")
    metadata_url = f"{endpoint}/api/models/{repository_part}/revision/{revision.lower()}"
    info, _ = _read_json_url(
        metadata_url,
        label="Hub model metadata",
        timeout=float(timeout),
        opener=opener,
    )
    if not isinstance(info, dict):
        raise NSDError("Hub model metadata must be a JSON object")
    resolved_sha = info.get("sha")
    if not isinstance(resolved_sha, str) or resolved_sha.lower() != revision.lower():
        raise NSDError("Hub did not resolve the requested immutable revision exactly")
    siblings = _sibling_names(info)
    if "config.json" not in siblings:
        raise NSDError("Hub model snapshot has no root config.json")

    config_url = _model_file_url(endpoint, repository, revision.lower(), "config.json")
    config, config_raw = _read_json_url(
        config_url,
        label="config.json",
        timeout=float(timeout),
        opener=opener,
    )
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
    weight_map: dict[str, str] | None = None
    if index_relative in siblings:
        index_url = _model_file_url(endpoint, repository, revision.lower(), index_relative)
        index, index_raw = _read_json_url(
            index_url,
            label=index_relative,
            timeout=float(timeout),
            opener=opener,
        )
        if not isinstance(index, dict) or not isinstance(index.get("weight_map"), dict):
            raise NSDError("Safetensors index must contain a weight_map object")
        candidate_map = index["weight_map"]
        if not candidate_map or any(
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
        shard_names = sorted(set(_safe_hub_path(name) for name in weight_map.values()))
    else:
        candidates = sorted(
            name for name in siblings
            if name.endswith(".safetensors") and "/" not in name
        )
        if "model.safetensors" in candidates:
            shard_names = ["model.safetensors"]
        elif len(candidates) == 1:
            shard_names = candidates
        elif not candidates:
            raise NSDError("Hub model snapshot has no Safetensors model file")
        else:
            raise NSDError(
                "Hub model has multiple unindexed Safetensors files; "
                "the primary weight file is ambiguous"
            )

    for shard_name in shard_names:
        if shard_name not in siblings:
            raise NSDError(f"Safetensors index references an unlisted shard: {shard_name!r}")

    tensor_manifest: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for shard_name in shard_names:
        shard_url = _model_file_url(endpoint, repository, revision.lower(), shard_name)
        prefix, total_size = _read_exact_range(
            shard_url,
            0,
            7,
            timeout=float(timeout),
            opener=opener,
        )
        header_length = int.from_bytes(prefix, byteorder="little", signed=False)
        if header_length < 2:
            raise NSDError(f"{shard_name}: header length is too small")
        if header_length > MAX_HEADER_BYTES:
            raise NSDError(
                f"{shard_name}: header exceeds the {MAX_HEADER_BYTES}-byte safety limit"
            )
        header_raw, header_total = _read_exact_range(
            shard_url,
            8,
            7 + header_length,
            timeout=float(timeout),
            opener=opener,
        )
        if header_total != total_size:
            raise NSDError(f"{shard_name}: file size changed between header range requests")
        tensors, file_record = parse_safetensors_header_bytes(
            prefix,
            header_raw,
            total_size,
            shard_name,
        )
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
            if _safe_hub_path(weight_map[tensor["name"]]) != tensor["shard"]:
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
        description="Observe a pinned Hugging Face model using small Safetensors HTTP range requests."
    )
    parser.add_argument("--repository", required=True, help="Hub model repository, e.g. openai-community/gpt2")
    parser.add_argument("--revision", required=True, help="Immutable 40-character Hub commit SHA")
    parser.add_argument("--license-id", help="Explicitly recorded source license identifier")
    parser.add_argument("--output", help="Write NSD JSON to this path instead of stdout")
    args = parser.parse_args(argv)

    try:
        description = inspect_huggingface_model(
            args.repository,
            args.revision,
            license_id=args.license_id,
        )
        rendered = json.dumps(
            description,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(rendered)
    except (NSDError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
