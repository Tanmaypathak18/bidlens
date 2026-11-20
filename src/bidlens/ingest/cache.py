"""Raw response cache with a JSONL manifest (decision D-017).

Layout under the cache root:
    <endpoint>/<sha1 of sorted query>.html.gz   raw response body
    manifest.jsonl                              one line per fetch attempt outcome

The latest manifest line for a key wins, so the cache can be resumed after any stop.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

Params = list[tuple[str, str]]


def cache_key(endpoint: str, params: Params) -> str:
    """Stable key for a request: endpoint plus the sorted, encoded query."""
    query = urlencode(sorted(params))
    return hashlib.sha1(f"{endpoint}?{query}".encode()).hexdigest()


@dataclass
class ManifestEntry:
    key: str
    endpoint: str
    params: Params
    status: str  # "ok" | "site_error" | "http_error"
    http_status: int | None
    message: str | None
    path: str | None
    bytes: int
    fetched_at: str


class RawCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.jsonl"
        self._latest: dict[str, ManifestEntry] = {}
        if self.manifest_path.exists():
            with self.manifest_path.open() as fh:
                for line in fh:
                    if line.strip():
                        d = json.loads(line)
                        d["params"] = [tuple(p) for p in d["params"]]
                        self._latest[d["key"]] = ManifestEntry(**d)

    def entry(self, endpoint: str, params: Params) -> ManifestEntry | None:
        return self._latest.get(cache_key(endpoint, params))

    def entries(self) -> list[ManifestEntry]:
        return list(self._latest.values())

    def read(self, entry: ManifestEntry) -> str:
        if entry.path is None:
            raise FileNotFoundError(f"no body cached for {entry.key}")
        return gzip.decompress((self.root / entry.path).read_bytes()).decode("utf-8", "replace")

    def record(
        self,
        endpoint: str,
        params: Params,
        *,
        status: str,
        http_status: int | None,
        body: str | None = None,
        message: str | None = None,
    ) -> ManifestEntry:
        key = cache_key(endpoint, params)
        rel: str | None = None
        size = 0
        if body is not None:
            rel = f"{endpoint.removesuffix('.php')}/{key}.html.gz"
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            data = body.encode("utf-8")
            size = len(data)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(gzip.compress(data))
            tmp.replace(target)
        entry = ManifestEntry(
            key=key,
            endpoint=endpoint,
            params=list(params),
            status=status,
            http_status=http_status,
            message=message,
            path=rel,
            bytes=size,
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        with self.manifest_path.open("a") as fh:
            fh.write(json.dumps(asdict(entry)) + "\n")
        self._latest[key] = entry
        return entry
