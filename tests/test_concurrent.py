from __future__ import annotations

import pytest
import asyncio

from scriptorium.concurrent import ConcurrentAnalyzer, AnalysisTask, BatchResult
from scriptorium.db import Store, new_id
from scriptorium.models import (
    Project, Participant, ConsentScope, SourceDocument, RunState,
)
from scriptorium.rag import ingest


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    s = Store(db_path)
    s.create_project(Project(id="proj"))
    return s


@pytest.fixture
def populated_store(store, tmp_path):
    for i in range(3):
        pid = f"p{i}"
        store.put_participant(Participant(
            id=pid, project_id="proj", pseudonym=f"P{i}",
            consent_scope=ConsentScope(research_analysis=True),
        ))
        txt = tmp_path / f"chat_{i}.txt"
        txt.write_text(f"participant {i} says hello\n" * 5, encoding="utf-8")
        ingest(store, str(txt), "proj", pid, ConsentScope(research_analysis=True))
    return store


class TestAnalysisTask:
    def test_creation(self):
        task = AnalysisTask(
            project_id="proj", participant_id="p1",
            source_ids=["s1"], idempotency_key="k1",
        )
        assert task.project_id == "proj"
        assert task.participant_id == "p1"


class TestBatchResult:
    def test_success(self):
        task = AnalysisTask("proj", "p1", ["s1"], "k1")
        r = BatchResult(task=task)
        assert not r.success
        r.error = "some error"
        assert not r.success

    def test_success_with_run(self):
        from scriptorium.models import AnalysisRun
        task = AnalysisTask("proj", "p1", ["s1"], "k1")
        run = AnalysisRun(id="r1", project_id="proj", participant_id="p1",
                          source_ids=["s1"], state=RunState.CREATED, idempotency_key="k1")
        r = BatchResult(task=task, run=run)
        assert r.success


class TestConcurrentAnalyzer:
    @pytest.mark.asyncio
    async def test_batch_analysis(self, populated_store):
        docs = populated_store.list_documents("proj")
        tasks = []
        for i in range(3):
            pid = f"p{i}"
            doc_ids = [d.id for d in docs if d.participant_id == pid]
            tasks.append(AnalysisTask(
                project_id="proj", participant_id=pid,
                source_ids=doc_ids, idempotency_key=f"batch_{pid}",
            ))
        analyzer = ConcurrentAnalyzer(populated_store, max_concurrent=2)
        results = await analyzer.analyze_batch(tasks)
        assert len(results) == 3
        successes = [r for r in results if r.success]
        assert len(successes) == 3

    @pytest.mark.asyncio
    async def test_concurrency_limit(self, populated_store):
        docs = populated_store.list_documents("proj")
        tasks = []
        for i in range(3):
            pid = f"p{i}"
            doc_ids = [d.id for d in docs if d.participant_id == pid]
            tasks.append(AnalysisTask(
                project_id="proj", participant_id=pid,
                source_ids=doc_ids, idempotency_key=f"conc_{pid}",
            ))
        analyzer = ConcurrentAnalyzer(populated_store, max_concurrent=1)
        results = await analyzer.analyze_batch(tasks)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_batch_with_invalid_participant(self, store):
        tasks = [AnalysisTask(
            project_id="proj", participant_id="nonexistent",
            source_ids=["s1"], idempotency_key="k_bad",
        )]
        analyzer = ConcurrentAnalyzer(store)
        results = await analyzer.analyze_batch(tasks)
        assert len(results) == 1
        assert results[0].error is not None

    @pytest.mark.asyncio
    async def test_empty_batch(self, store):
        analyzer = ConcurrentAnalyzer(store)
        results = await analyzer.analyze_batch([])
        assert results == []
