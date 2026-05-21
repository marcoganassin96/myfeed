import httpx
from fastapi import Response
from fastapi.responses import JSONResponse


def map_response(resp: httpx.Response) -> Response:
    if resp.status_code >= 500:
        return JSONResponse({"error": "Bad gateway"}, status_code=502)
    return JSONResponse(resp.json(), status_code=resp.status_code)


def unavailable() -> JSONResponse:
    return JSONResponse({"error": "Service unavailable"}, status_code=503)
