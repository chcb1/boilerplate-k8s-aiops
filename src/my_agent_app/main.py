import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from my_agent_app.analysis.analyzer import RootCauseAnalyzer
from my_agent_app.analysis.dedup import recover_orphans
from my_agent_app.analysis.handler import AnalysisHandler
from my_agent_app.api.router import router as api_router
from my_agent_app.collector.client import ClusterEvents
from my_agent_app.collector.loop import EventCollector
from my_agent_app.database import get_database_url
from my_agent_app.web.router import DATABASE_ERRORS, database_unavailable
from my_agent_app.web.router import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(get_database_url())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    app.state.sessionmaker = sessionmaker

    try:
        await recover_orphans(sessionmaker)
    except Exception:
        logger.exception("Falha ao recuperar relatorios EM_ANALISE orfaos no startup")

    handler = AnalysisHandler(sessionmaker, RootCauseAnalyzer(sessionmaker))
    collector = EventCollector(ClusterEvents().fetch, handler)
    collector_task = asyncio.create_task(collector.run())
    app.state.collector_task = collector_task

    yield

    collector_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await collector_task
    await engine.dispose()


app = FastAPI(title="My Agent App", lifespan=lifespan)
app.include_router(api_router)
app.include_router(web_router)
for error in DATABASE_ERRORS:
    app.add_exception_handler(error, database_unavailable)
