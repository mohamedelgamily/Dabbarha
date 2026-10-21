"""Outer ASGI guards bound input before parsing and redact unhandled failures."""
import logging

import anyio
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.core.api_security import source_ip

logger = logging.getLogger("dabbarha.security")


def json_too_deep(body: bytes, maximum: int) -> bool:
    depth = 0
    quoted = escaped = False
    for value in body:
        if quoted:
            if escaped:
                escaped = False
            elif value == 92:
                escaped = True
            elif value == 34:
                quoted = False
        elif value == 34:
            quoted = True
        elif value in (91, 123):
            depth += 1
            if depth > maximum:
                return True
        elif value in (93, 125):
            depth -= 1
    return False


class RequestSecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        runtime = scope["app"].state.security
        settings = runtime.settings
        started = False

        async def secure_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                protected = {b"cache-control", b"x-content-type-options", b"referrer-policy"}
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() not in protected]
                headers += [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                            (b"referrer-policy", b"no-referrer")]
                message = {**message, "headers": headers}
            await send(message)

        async def error(code, detail, headers=None):
            await JSONResponse(status_code=code, content={"detail": detail}, headers=headers)(scope, receive, secure_send)

        try:
            lengths = [v for k, v in scope["headers"] if k.lower() == b"content-length"]
            if lengths:
                if len(lengths) != 1 or not lengths[0].isdigit():
                    return await error(400, "Invalid request length.")
                if len(lengths[0]) > 20 or int(lengths[0]) > settings.body_bytes:
                    return await error(413, "Request body is too large.")
            encodings = [v.lower().strip() for k, v in scope["headers"] if k.lower() == b"content-encoding"]
            if any(value != b"identity" for value in encodings):
                return await error(415, "Compressed request bodies are not supported.")
            path = scope["path"]
            root = scope.get("root_path", "")
            if root and path.startswith(root + "/"):
                path = path[len(root):]
            if scope["method"] == "POST" and path.rstrip("/") in {"/auth/login", "/auth/register"}:
                await run_in_threadpool(runtime.auth_ip, path.rstrip("/"), source_ip(scope))
            buffered, size = bytearray(), 0
            try:
                with anyio.fail_after(settings.body_timeout):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        size += len(chunk)
                        if size > settings.body_bytes:
                            return await error(413, "Request body is too large.")
                        buffered.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await error(408, "Request body took too long to arrive.")
            if lengths and size != int(lengths[0]):
                return await error(400, "Request body length does not match its declared length.")
            body = bytes(buffered)
            if json_too_deep(body, settings.json_depth):
                return await error(422, [{"type": "json_invalid", "loc": ["body"], "msg": "JSON nesting exceeds the supported limit."}])
            delivered = False
            async def replay():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            await self.app(scope, replay, secure_send)
        except HTTPException as exc:
            if not started:
                await error(exc.status_code, exc.detail, exc.headers)
        except Exception:
            # Deliberately omit exception text, traceback, request values and SQL.
            logger.error("api_request_failed")
            if not started:
                await error(500, "The request could not be completed. Please try again.")
