"""Bounded, checked snapshot streams. Compression is for storage, never LLM input.

Each record is independently length-delimited. Delta records use the preceding
snapshot as a zlib dictionary; full checkpoints need no preceding dictionary.
Hashes detect accidental damage, not malicious replacement/authenticity.
"""

import hashlib
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"DDT1\n"
HEADER = struct.Struct(">cQII32s32s")  # kind, seq, raw size, payload size, chain, content
MAX_BYTES = 16 * 1024 * 1024
ZERO = bytes(32)


class TapeError(ValueError):
    """Incomplete, damaged, or unsupported recording."""

    def __init__(self, message, *, incomplete=False):
        super().__init__(message)
        self.incomplete = incomplete


class SnapshotTooLarge(ValueError):
    """Rejected before any write or stream-state change."""

    def __init__(self, raw_bytes):
        super().__init__("snapshot exceeds 16 MiB")
        self.raw_bytes = raw_bytes
        self.limit_bytes = MAX_BYTES


@dataclass(frozen=True)
class TapeEntry:
    seq: int
    text: str
    kind: str
    stored_bytes: int


class TapeWriter:
    def __init__(self, path, *, checkpoint_interval=20):
        if not isinstance(checkpoint_interval, int) or not 1 <= checkpoint_interval <= 1000:
            raise ValueError("checkpoint_interval must be 1..1000")
        self.path = Path(path)
        self._file = self.path.open("xb")  # never replace an existing recording
        self._file.write(MAGIC)
        self.interval = checkpoint_interval
        self.seq, self._previous, self._chain = 0, b"", ZERO
        self._closed = False

    def add(self, text: str) -> TapeEntry:
        if self._closed:
            raise ValueError("recording is closed")
        raw = text.encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise SnapshotTooLarge(len(raw))
        full = zlib.compress(raw, 6)
        kind, payload = b"F", full
        if self.seq % self.interval and self._previous:
            if raw == self._previous:
                kind, payload = b"R", b""
            else:
                compressor = zlib.compressobj(6, zdict=self._previous[-32768:])
                delta = compressor.compress(raw) + compressor.flush()
                if len(delta) < len(full):
                    kind, payload = b"D", delta
        seq = self.seq + 1
        header = HEADER.pack(
            kind, seq, len(raw), len(payload), self._chain, hashlib.sha256(raw).digest()
        )
        self._file.write(header + payload)
        self._file.flush()
        self.seq, self._previous = seq, raw
        self._chain = hashlib.sha256(header + payload).digest()
        return TapeEntry(seq, text, kind.decode(), len(header) + len(payload))

    def close(self, *, complete=True):
        if not self._closed:
            try:
                if complete:
                    self._file.write(HEADER.pack(b"E", self.seq, 0, 0, self._chain, ZERO))
            finally:
                self._file.close()
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        self.close(complete=exc_type is None)


def read_tape(path):
    """Stream verified entries. Exhaust the iterator to verify the final seal too."""
    with Path(path).open("rb") as stream:
        if stream.read(len(MAGIC)) != MAGIC:
            raise TapeError("not a DeltaDOM DDT1 recording")
        seq, previous, chain = 0, b"", ZERO
        while True:
            header = stream.read(HEADER.size)
            if len(header) != HEADER.size:
                raise TapeError("incomplete recording: missing record or end seal", incomplete=True)
            kind, index, raw_size, size, base, digest = HEADER.unpack(header)
            if base != chain:
                raise TapeError("record chain mismatch (missing, reordered or damaged record)")
            if kind == b"E":
                if index != seq or raw_size or size or digest != ZERO or stream.read(1):
                    raise TapeError("invalid end seal or trailing data")
                return
            if index != seq + 1 or raw_size > MAX_BYTES or size > MAX_BYTES + 65536:
                raise TapeError("invalid sequence or oversized record")
            payload = stream.read(size)
            if len(payload) != size:
                raise TapeError("incomplete record payload", incomplete=True)
            try:
                if kind == b"R":
                    if not seq or payload:
                        raise TapeError("invalid repeat record")
                    raw = previous
                elif kind in {b"F", b"D"}:
                    if kind == b"D" and not previous:
                        raise TapeError("delta has no base snapshot")
                    dec = (
                        zlib.decompressobj(zdict=previous[-32768:])
                        if kind == b"D"
                        else zlib.decompressobj()
                    )
                    raw = dec.decompress(payload, raw_size + 1)
                    if not dec.eof or dec.unused_data or dec.unconsumed_tail:
                        raise TapeError("incomplete or oversized compressed payload")
                else:
                    raise TapeError("unknown record encoding")
                if len(raw) != raw_size or hashlib.sha256(raw).digest() != digest:
                    raise TapeError("snapshot checksum mismatch")
                text = raw.decode("utf-8")
            except (zlib.error, UnicodeError) as exc:
                raise TapeError("damaged snapshot payload") from exc
            seq, previous = index, raw
            chain = hashlib.sha256(header + payload).digest()
            yield TapeEntry(seq, text, kind.decode(), len(header) + size)
