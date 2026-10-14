import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Request
from python_multipart import MultipartParser
from python_multipart.exceptions import FormParserError, MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.concurrency import run_in_threadpool

from romledger import importer
from romledger.web.jobs import Jobs

if TYPE_CHECKING:
    from python_multipart.multipart import MultipartCallbacks

PART_SUFFIX = ".part"
MAX_NAME_BYTES = 200


class UploadError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Saved:
    name: str
    size: int


def safe_name(raw: str) -> str:
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if char.isprintable()).strip().lstrip(".")
    return name.encode()[:MAX_NAME_BYTES].decode(errors="ignore")


class Receiver:
    def __init__(self, inbox: Path) -> None:
        self._inbox = inbox
        self._headers: dict[bytes, bytes] = {}
        self._field = b""
        self._value = b""
        self._part: Path | None = None
        self._final: Path | None = None
        self._handle: Any = None
        self._size = 0
        self.saved: list[Saved] = []
        self.complete = False

    def callbacks(self) -> "MultipartCallbacks":
        return {
            "on_part_begin": self._begin,
            "on_header_field": self._header_field,
            "on_header_value": self._header_value,
            "on_header_end": self._header_end,
            "on_headers_finished": self._headers_finished,
            "on_part_data": self._data,
            "on_part_end": self._end,
            "on_end": self._finish,
        }

    def abort(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        if self._part is not None:
            self._part.unlink(missing_ok=True)
            self._part = None

    def _begin(self) -> None:
        self._headers = {}
        self._field = self._value = b""

    def _header_field(self, data: bytes, start: int, end: int) -> None:
        self._field += data[start:end]

    def _header_value(self, data: bytes, start: int, end: int) -> None:
        self._value += data[start:end]

    def _header_end(self) -> None:
        self._headers[self._field.lower()] = self._value
        self._field = self._value = b""

    def _headers_finished(self) -> None:
        _, params = parse_options_header(self._headers.get(b"content-disposition", b""))
        name = safe_name(params.get(b"filename", b"").decode("utf-8", errors="replace"))
        if not name:
            return
        if name.endswith(PART_SUFFIX):
            raise UploadError(f"names ending in {PART_SUFFIX} are reserved for unfinished uploads")
        self._final = importer.free_path(self._inbox / name)
        self._part = self._final.with_name(self._final.name + PART_SUFFIX)
        self._handle = self._part.open("wb")
        self._size = 0

    def _data(self, data: bytes, start: int, end: int) -> None:
        if self._handle is not None:
            self._handle.write(data[start:end])
            self._size += end - start

    def _end(self) -> None:
        if self._handle is None or self._part is None or self._final is None:
            return
        self._handle.close()
        self._handle = None
        os.replace(self._part, self._final)
        self.saved.append(Saved(self._final.name, self._size))
        self._part = None

    def _finish(self) -> None:
        self.complete = True


def refuse_while_running(jobs: Jobs) -> None:
    running = jobs.current()
    if running is not None:
        raise UploadError(f"a {running.kind} is running; upload again when it finishes", 409)


def boundary_of(content_type: str) -> bytes:
    kind, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if kind != b"multipart/form-data" or not boundary:
        raise UploadError("send the files as multipart/form-data", 415)
    return boundary


async def receive(request: Request, inbox: Path) -> list[Saved]:
    receiver = Receiver(inbox)
    parser = MultipartParser(
        boundary_of(request.headers.get("content-type", "")), receiver.callbacks()
    )
    try:
        async for chunk in request.stream():
            await run_in_threadpool(parser.write, chunk)
        parser.finalize()
        if not receiver.complete:
            raise UploadError("the upload ended early; nothing from the unfinished file was kept")
    except OSError as error:
        receiver.abort()
        raise UploadError(f"cannot write to {inbox}: {error.strerror or error}", 500) from error
    except (FormParserError, MultipartParseError) as error:
        receiver.abort()
        raise UploadError(f"the upload is malformed ({error})") from error
    except BaseException:
        receiver.abort()
        raise
    return receiver.saved
