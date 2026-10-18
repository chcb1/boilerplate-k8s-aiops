"""Validacao da dedup com eventos reais de um cluster kind.

Opt-in: RUN_KIND_TESTS=1 uv run pytest tests/integration/test_kind_dedup.py -s
Requer o contexto kubectl atual apontando para o kind com os manifestos de
`manifestos-k8s/` aplicados, e o PostgreSQL local (`docker compose up -d`).
"""
import os

import pytest
from sqlalchemy import update

from my_agent_app.analysis.handler import AnalysisHandler
from my_agent_app.collector.client import ClusterEvents
from my_agent_app.collector.loop import EventCollector
from my_agent_app.models import Report, ReportStatus

pytestmark = pytest.mark.skipif(os.environ.get("RUN_KIND_TESTS") != "1", reason="defina RUN_KIND_TESTS=1")


async def test_dedup_with_real_cluster_events(sessionmaker):
    batches: list[list[str]] = []

    async def analyzer(report_id, events):
        batches.append([e["uid"] for e in events])
        print(f"analisando {len(events)} evento(s) no relatorio {report_id}")

    collector = EventCollector(
        ClusterEvents().fetch,
        AnalysisHandler(sessionmaker, analyzer, max_attempts=3, stale_minutes=30),
        60,
    )

    async def cycle():
        await collector.run_cycle()
        await collector.drain()

    async def finish_incomplete():
        async with sessionmaker() as session, session.begin():
            await session.execute(
                update(Report).where(Report.status == ReportStatus.EM_ANALISE).values(status=ReportStatus.INCOMPLETO)
            )

    # ciclo 1: tudo que esta vivo e novo
    await cycle()
    assert len(batches) == 1 and len(batches[0]) > 0
    first = set(batches[0])

    # ciclo 2: os mesmos eventos continuam vivos, mas tem relatorio ativo (EM_ANALISE)
    await cycle()
    assert all(not (set(b) & first) for b in batches[1:])

    # analise incompleta -> reanalise por presenca, ate o limite de 3 tentativas
    for attempt in (2, 3):
        await finish_incomplete()
        before = len(batches)
        await cycle()
        assert len(batches) == before + 1, f"tentativa {attempt} deveria reanalisar"
        assert first <= set(batches[-1])

    await finish_incomplete()
    before = len(batches)
    await cycle()
    assert all(not (set(b) & first) for b in batches[before:]), "limite de tentativas deveria bloquear a reanalise"
