from __future__ import annotations

import asyncio
import unittest

from backend.app.llm import (
    bind_cloud_processing,
    cloud_processing_allowed,
    reset_cloud_processing,
)
from backend.app.main import _iterate_blocking


class StreamingContextTests(unittest.TestCase):
    def test_cloud_consent_survives_all_stream_worker_steps(self) -> None:
        async def collect():
            token = bind_cloud_processing(True)
            try:
                source = (cloud_processing_allowed() for _ in range(3))
                return [value async for value in _iterate_blocking(source)]
            finally:
                reset_cloud_processing(token)

        self.assertEqual([True, True, True], asyncio.run(collect()))


if __name__ == "__main__":
    unittest.main()
