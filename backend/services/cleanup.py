import logging
from backend.db.models import Session
from sqlalchemy import update as sa_update, select
from backend.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def cleanupStaleStatuses() -> None:
    """Reset leftover active/running statuses from a previous server run."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(Session)
            .where(Session.status.not_in(["new", "switched"]))
            .values(status="switched")
        )
        await db.commit()


async def cleanupOrphanedContainers() -> None:
    """Remove any cua-session-* Docker containers with no matching active session."""
    try:
        import docker
        import docker.errors
        from backend.services.container_manager import container_manager

        client = docker.from_env()
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Session.container_id))
            known_ids = {row[0] for row in result.all() if row[0]}

        for container in client.containers.list(filters={"name": "cua-session-"}):
            if container.id not in known_ids and container.short_id not in known_ids:
                logger.info("Removing orphaned session container %s", container.name)
                try:
                    container.stop(timeout=3)
                    container.remove()
                except Exception as e:
                    logger.warning("Could not remove container %s: %s", container.name, e)
    except Exception as e:
        logger.warning("Container cleanup skipped: %s", e)
