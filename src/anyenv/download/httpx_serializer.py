from __future__ import annotations

import base64
from datetime import datetime

from hishel._serializers import (
    HEADERS_ENCODING,
    KNOWN_REQUEST_EXTENSIONS,
    KNOWN_RESPONSE_EXTENSIONS,
    BaseSerializer,
    Metadata,
    Request,
    Response,
    normalized_url,
)


class AnyEnvSerializer(BaseSerializer):
    """A json-based serializer using AnyEnv."""

    def dumps(
        self, response: Response, request: Request, metadata: Metadata
    ) -> str | bytes:
        """Dumps the HTTP response and its HTTP request.

        :param response: An HTTP response
        :type response: Response
        :param request: An HTTP request
        :type request: Request
        :param metadata: Additional information about the stored response
        :type metadata: Metadata
        :return: Serialized response
        :rtype: str | bytes
        """
        response_dict = {
            "status": response.status,
            "headers": [
                (key.decode(HEADERS_ENCODING), value.decode(HEADERS_ENCODING))
                for key, value in response.headers
            ],
            "content": base64.b64encode(response.content).decode("ascii"),
            "extensions": {
                key: value.decode("ascii")
                for key, value in response.extensions.items()
                if key in KNOWN_RESPONSE_EXTENSIONS
            },
        }

        request_dict = {
            "method": request.method.decode("ascii"),
            "url": normalized_url(request.url),
            "headers": [
                (key.decode(HEADERS_ENCODING), value.decode(HEADERS_ENCODING))
                for key, value in request.headers
            ],
            "extensions": {
                key: value
                for key, value in request.extensions.items()
                if key in KNOWN_REQUEST_EXTENSIONS
            },
        }

        metadata_dict = {
            "cache_key": metadata["cache_key"],
            "number_of_uses": metadata["number_of_uses"],
            "created_at": metadata["created_at"].strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }

        full_json = {
            "response": response_dict,
            "request": request_dict,
            "metadata": metadata_dict,
        }
        from anyenv.json_tools import dumping

        return dumping.dump_json(full_json, indent=True)

    def loads(self, data: str | bytes) -> tuple[Response, Request, Metadata]:
        """Loads the HTTP response and its HTTP request from serialized data.

        :param data: Serialized data
        :type data: str | bytes
        :return: HTTP response and its HTTP request
        :rtype: tuple[Response, Request, Metadata]
        """
        from anyenv.json_tools import loading

        full_json = loading.load_json(data)

        response_dict = full_json["response"]
        request_dict = full_json["request"]
        metadata_dict = full_json["metadata"]
        metadata_dict["created_at"] = datetime.strptime(
            metadata_dict["created_at"],
            "%a, %d %b %Y %H:%M:%S GMT",
        )

        response = Response(
            status=response_dict["status"],
            headers=[
                (key.encode(HEADERS_ENCODING), value.encode(HEADERS_ENCODING))
                for key, value in response_dict["headers"]
            ],
            content=base64.b64decode(response_dict["content"].encode("ascii")),
            extensions={
                key: value.encode("ascii")
                for key, value in response_dict["extensions"].items()
                if key in KNOWN_RESPONSE_EXTENSIONS
            },
        )

        request = Request(
            method=request_dict["method"],
            url=request_dict["url"],
            headers=[
                (key.encode(HEADERS_ENCODING), value.encode(HEADERS_ENCODING))
                for key, value in request_dict["headers"]
            ],
            extensions={
                key: value
                for key, value in request_dict["extensions"].items()
                if key in KNOWN_REQUEST_EXTENSIONS
            },
        )

        metadata = Metadata(
            cache_key=metadata_dict["cache_key"],
            created_at=metadata_dict["created_at"],
            number_of_uses=metadata_dict["number_of_uses"],
        )

        return response, request, metadata

    @property
    def is_binary(self) -> bool:
        return False
