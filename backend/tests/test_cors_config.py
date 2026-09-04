from __future__ import annotations

import asyncio
import unittest

from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_backend_cors_origins


class CorsConfigTest(unittest.TestCase):
    async def _cors_response_headers(self, origin: str) -> dict[str, str]:
        async def app(scope, receive, send) -> None:
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b'{"status":"ok"}'})

        middleware = CORSMiddleware(
            app,
            allow_origins=get_backend_cors_origins(),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        messages = []

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            messages.append(message)

        await middleware(
            {
                "type": "http",
                "method": "GET",
                "path": "/ping",
                "headers": [(b"origin", origin.encode())],
            },
            receive,
            send,
        )

        response_start = next(message for message in messages if message["type"] == "http.response.start")
        return {key.decode(): value.decode() for key, value in response_start["headers"]}

    def test_cors_allows_localhost_8001_frontend(self) -> None:
        headers = asyncio.run(self._cors_response_headers("http://localhost:8001"))

        self.assertEqual(headers["access-control-allow-origin"], "http://localhost:8001")

    def test_cors_allows_vite_default_localhost_5173_frontend(self) -> None:
        headers = asyncio.run(self._cors_response_headers("http://localhost:5173"))

        self.assertEqual(headers["access-control-allow-origin"], "http://localhost:5173")


if __name__ == "__main__":
    unittest.main()
