from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .db import Store
from .models import AnalysisRun
from .workflow import Workflow

logger = logging.getLogger(__name__)


@dataclass
class AnalysisTask:
    project_id: str
    participant_id: str
    source_ids: list[str]
    idempotency_key: str


@dataclass
class BatchResult:
    task: AnalysisTask
    run: AnalysisRun | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.run is not None and self.error is None


class ConcurrentAnalyzer:
    def __init__(self, store: Store, provider=None, max_concurrent: int = 4):
        if not 1 <= max_concurrent <= 16:
            raise ValueError('max_concurrent must be between 1 and 16')
        self.store = store
        self.provider = provider
        self.max_concurrent = max_concurrent

    async def analyze_batch(self, tasks: list[AnalysisTask]) -> list[BatchResult]:
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _run_one(task: AnalysisTask) -> BatchResult:
            async with semaphore:
                return await self._run_single(task)

        results = await asyncio.gather(*[_run_one(t) for t in tasks])
        successes = sum(1 for r in results if r.success)
        logger.info("batch complete: %d/%d succeeded", successes, len(results))
        return list(results)

    async def _run_single(self, task: AnalysisTask) -> BatchResult:
        loop = asyncio.get_running_loop()
        try:
            run = await loop.run_in_executor(
                None,
                lambda: self._create_workflow().run(
                    task.project_id, task.participant_id,
                    task.source_ids, task.idempotency_key,
                ),
            )
            return BatchResult(task=task, run=run)
        except Exception as e:
            logger.warning("task failed for participant %s: %s", task.participant_id, e)
            return BatchResult(task=task, error=str(e))

    def _create_workflow(self) -> Workflow:
        thread_store = Store(self.store.path)
        return Workflow(thread_store, self.provider)
