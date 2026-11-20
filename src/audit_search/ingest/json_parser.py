"""Stream JSON audit logs record by record using only the standard library.

Three layouts are accepted:

1. JSON array      `[{...}, {...}, ...]`  -> streamed: read in 64 KB chunks, one record at a time.
2. JSON Lines      one object per line     -> streamed line by line (.jsonl / .ndjson files).
3. Wrapped object  `{"pageItems": [...]}`  -> the shape Apache Fineract's API returns. This one
                                              is loaded in full, because the list could be anywhere
                                              inside the object.

Why not just `json.load()`? It reads the whole file into memory at once. A multi-gigabyte
export would not fit, which breaks the PRD's "streaming ingestion" promise.

Numbers with decimals are parsed as Decimal instead of float, so amounts like 0.10 stay exact.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO

from audit_search.models import RawRecord

_CHUNK_SIZE = 64 * 1024
_WHITESPACE = " \t\r\n"
# Keys that usually hold the list of records inside a wrapped JSON object.
_WRAPPER_KEYS = ("pageItems", "records", "data", "items", "events", "auditLogs")


def _new_decoder() -> json.JSONDecoder:
    return json.JSONDecoder(parse_float=Decimal)


def _as_record(location: str, value: Any) -> RawRecord:
    if isinstance(value, dict):
        return RawRecord(location, value)
    return RawRecord(location, {}, error=f"expected a JSON object, got {type(value).__name__}")


# --------------------------------------------------------------------------- JSON Lines


def iter_jsonl(path: str | Path) -> Iterator[RawRecord]:
    """One JSON object per line. A broken line is reported and the next line still works."""
    decoder = _new_decoder()
    with open(path, encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            location = f"line {line_number}"
            try:
                value = decoder.decode(text)
            except json.JSONDecodeError as exc:
                yield RawRecord(location, {}, error=f"invalid JSON: {exc.msg}")
                continue
            yield _as_record(location, value)


# --------------------------------------------------------------------------- JSON array / object


class _ChunkedText:
    """A read buffer over a text file that refills itself 64 KB at a time."""

    def __init__(self, handle: TextIO) -> None:
        self._handle = handle
        self.buffer = ""
        self.pos = 0

    def _refill(self) -> bool:
        chunk = self._handle.read(_CHUNK_SIZE)
        if not chunk:
            return False
        self.buffer = self.buffer[self.pos :] + chunk  # throw away what was already consumed
        self.pos = 0
        return True

    def peek(self) -> str:
        """Skip whitespace and return the next character without consuming it ("" at end)."""
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos] in _WHITESPACE:
                self.pos += 1
            if self.pos < len(self.buffer):
                return self.buffer[self.pos]
            if not self._refill():
                return ""

    def take(self) -> str:
        char = self.peek()
        self.pos += len(char)
        return char

    def decode_value(self, decoder: json.JSONDecoder) -> Any:
        """Decode exactly one JSON value, reading more of the file if the value is cut off."""
        self.peek()  # raw_decode cannot skip leading whitespace itself
        while True:
            try:
                value, end = decoder.raw_decode(self.buffer, self.pos)
            except json.JSONDecodeError:
                if self._refill():
                    continue  # the value was probably cut in half by the chunk boundary
                raise
            if end == len(self.buffer) and self._refill():
                continue  # a number at the very end might continue in the next chunk
            self.pos = end
            return value

    def read_rest(self) -> str:
        return self.buffer[self.pos :] + self._handle.read()


def iter_json(path: str | Path) -> Iterator[RawRecord]:
    decoder = _new_decoder()
    with open(path, encoding="utf-8-sig") as handle:
        stream = _ChunkedText(handle)
        first = stream.peek()
        if first == "":
            return  # empty file: nothing to import
        if first == "[":
            yield from _stream_array(stream, decoder)
        elif first == "{":
            yield from _load_wrapped_object(stream, decoder)
        else:
            raise ValueError("JSON file must contain an array [...] or an object {...}")


def _stream_array(stream: _ChunkedText, decoder: json.JSONDecoder) -> Iterator[RawRecord]:
    stream.take()  # the opening "["
    if stream.peek() == "]":
        stream.take()
        return
    index = 0
    while True:
        index += 1
        try:
            value = stream.decode_value(decoder)
        except json.JSONDecodeError as exc:
            # Inside an array we cannot safely find where the next record starts,
            # so a syntax error stops this file (records before it are already imported).
            raise ValueError(f"invalid JSON in record {index}: {exc.msg}") from None
        yield _as_record(f"record {index}", value)

        separator = stream.take()
        if separator == "]":
            break
        if separator != ",":
            raise ValueError(f"invalid JSON after record {index}: expected ',' or ']'")

    if stream.peek() != "":
        raise ValueError("unexpected data after the end of the JSON array")


def _load_wrapped_object(stream: _ChunkedText, decoder: json.JSONDecoder) -> Iterator[RawRecord]:
    try:
        document = decoder.decode(stream.read_rest())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg} (line {exc.lineno})") from None

    records = _find_record_list(document)
    if records is None:
        yield _as_record("record 1", document)  # a single object is a single record
        return
    for index, value in enumerate(records, start=1):
        yield _as_record(f"record {index}", value)


def _find_record_list(document: dict[str, Any]) -> list[Any] | None:
    for key in _WRAPPER_KEYS:
        if isinstance(document.get(key), list):
            return document[key]
    for value in document.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value
    return None
