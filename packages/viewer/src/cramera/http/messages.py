"""
HTTP requests and responses as the viewer's routes see them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs

from typing_extensions import Any, Dict, List, Optional, Self

from cramera_protocol.document import JsonValue
from cramera_protocol.viewer import ErrorKey

# %% vocabulary


class HttpMethod(StrEnum):
    """
    The HTTP methods the viewer answers.
    """

    GET = "GET"
    """
    Reads a resource.
    """

    HEAD = "HEAD"
    """
    Reads a resource's headers.
    """

    POST = "POST"
    """
    Asks a route to act.
    """

    OPTIONS = "OPTIONS"
    """
    Asks which cross-origin requests are allowed.
    """

    DELETE = "DELETE"
    """
    Removes a resource.
    """


class Header(StrEnum):
    """
    The HTTP headers the viewer reads or writes.
    """

    ORIGIN = "Origin"
    """
    The origin of the page that sent the request.
    """

    HOST = "Host"
    """
    The host name the client addressed.
    """

    CONTENT_TYPE = "Content-Type"
    """
    The media type of the body.
    """

    CONTENT_LENGTH = "Content-Length"
    """
    The length of the body in bytes.
    """

    CACHE_CONTROL = "Cache-Control"
    """
    How long the client may keep the answer.
    """

    ALLOW_ORIGIN = "Access-Control-Allow-Origin"
    """
    The origin a cross-origin answer is meant for.
    """

    ALLOW_METHODS = "Access-Control-Allow-Methods"
    """
    The methods a cross-origin request may use.
    """

    ALLOW_HEADERS = "Access-Control-Allow-Headers"
    """
    The headers a cross-origin request may send.
    """

    VARY = "Vary"
    """
    The request headers the answer depends on.
    """


class CacheDirective(StrEnum):
    """
    The ``Cache-Control`` directives the viewer sends.
    """

    NO_STORE = "no-store"
    """
    The answer must not be kept: scenes and live state change between requests.
    """


class MediaType(StrEnum):
    """
    The media types of the files the viewer serves.
    """

    HTML = "text/html; charset=utf-8"
    """
    Pages.
    """

    JAVASCRIPT = "text/javascript; charset=utf-8"
    """
    Scripts and ES modules.
    """

    CSS = "text/css; charset=utf-8"
    """
    Style sheets.
    """

    JSON = "application/json"
    """
    JSON documents.
    """

    XML = "application/xml"
    """
    URDF and other XML documents.
    """

    TEXT = "text/plain; charset=utf-8"
    """
    Plain text.
    """

    GLB = "model/gltf-binary"
    """
    Binary glTF meshes.
    """

    GLTF = "model/gltf+json"
    """
    GlTF meshes.
    """

    STL = "model/stl"
    """
    STL meshes.
    """

    OBJ = "model/obj"
    """
    Wavefront OBJ meshes and their material libraries.
    """

    COLLADA = "model/vnd.collada+xml"
    """
    COLLADA meshes.
    """

    PNG = "image/png"
    """
    PNG images.
    """

    JPEG = "image/jpeg"
    """
    JPEG images.
    """

    SVG = "image/svg+xml"
    """
    SVG images.
    """

    HDR = "image/vnd.radiance"
    """
    High dynamic range environment images.
    """

    WASM = "application/wasm"
    """
    WebAssembly modules.
    """

    BINARY = "application/octet-stream"
    """
    Anything else.
    """

    @classmethod
    def of_path(cls, path: Path) -> MediaType:
        """
        :param path: A file.
        :return: The media type its suffix names, :attr:`BINARY` when unknown.
        """
        return SUFFIX_MEDIA_TYPES.get(path.suffix.lower(), cls.BINARY)


SUFFIX_MEDIA_TYPES: Dict[str, MediaType] = {
    ".html": MediaType.HTML,
    ".js": MediaType.JAVASCRIPT,
    ".mjs": MediaType.JAVASCRIPT,
    ".css": MediaType.CSS,
    ".json": MediaType.JSON,
    ".urdf": MediaType.XML,
    ".xml": MediaType.XML,
    ".sdf": MediaType.XML,
    ".txt": MediaType.TEXT,
    ".md": MediaType.TEXT,
    ".csv": MediaType.TEXT,
    ".glb": MediaType.GLB,
    ".gltf": MediaType.GLTF,
    ".stl": MediaType.STL,
    ".obj": MediaType.OBJ,
    ".mtl": MediaType.OBJ,
    ".dae": MediaType.COLLADA,
    ".png": MediaType.PNG,
    ".jpg": MediaType.JPEG,
    ".jpeg": MediaType.JPEG,
    ".svg": MediaType.SVG,
    ".hdr": MediaType.HDR,
    ".wasm": MediaType.WASM,
}
"""
The media type of each file suffix the viewer knows.
"""


# %% request


@dataclass(frozen=True)
class Request:
    """
    One HTTP request.
    """

    method: HttpMethod
    """
    The request's method.
    """

    path: str
    """
    The path of the request target, without the query.
    """

    query: str = ""
    """
    The query of the request target, without the ``?``.
    """

    headers: Dict[str, str] = field(default_factory=dict)
    """
    The request headers, with their names as the client sent them.
    """

    body: bytes = b""
    """
    The request body.
    """

    def header(self, name: Header) -> Optional[str]:
        """
        :param name: A header name.
        :return: The header's value, compared without regard to case, or None.
        """
        wanted = name.lower()
        return next(
            (value for key, value in self.headers.items() if key.lower() == wanted),
            None,
        )

    def parameters(self) -> Dict[str, List[str]]:
        """
        :return: The query parameters, each with every value it was given.
        """
        return parse_qs(self.query)

    def json(self) -> Any:
        """
        :return: The decoded JSON body.
        """
        return json.loads(self.body.decode("utf-8"))


# %% response


@dataclass
class Response:
    """
    One HTTP response.
    """

    status: HTTPStatus = HTTPStatus.OK
    """
    The response status.
    """

    body: bytes = b""
    """
    The response body.
    """

    media_type: MediaType = MediaType.TEXT
    """
    The media type of the body.
    """

    headers: Dict[str, str] = field(default_factory=dict)
    """
    Further headers.
    """

    @classmethod
    def of_json(cls, value: Any, status: HTTPStatus = HTTPStatus.OK) -> Self:
        """
        :param value: A protocol value or a JSON-serializable value.
        :param status: The response status.
        :return: The value as a JSON response.
        """
        data = value.to_json() if isinstance(value, JsonValue) else value
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return cls(status=status, body=body, media_type=MediaType.JSON)

    @classmethod
    def of_text(cls, text: str, media_type: MediaType = MediaType.TEXT) -> Self:
        """
        :param text: The body text.
        :param media_type: The body's media type.
        :return: The text as a response.
        """
        return cls(body=text.encode("utf-8"), media_type=media_type)

    @classmethod
    def of_file(cls, path: Path) -> Self:
        """
        :param path: A file the caller has checked may be served.
        :return: The file's content with its media type.
        """
        return cls(body=path.read_bytes(), media_type=MediaType.of_path(path))

    @classmethod
    def of_error(cls, status: HTTPStatus, message: str) -> Self:
        """
        :param status: The error status.
        :param message: The reason, for the person reading the error.
        :return: The error as a JSON response ``{"error": message}``.
        """
        return cls.of_json({ErrorKey.ERROR: message}, status)
