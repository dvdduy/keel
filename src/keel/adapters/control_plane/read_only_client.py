from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class ReadOnlyControlPlane:
    """A control-plane client that can only read.

    There is deliberately no write verb here, so no tool built on it
    can mutate Keel state -- safety by construction, not by convention.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        return await self._client.get(path, params=params)
