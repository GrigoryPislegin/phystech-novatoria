import asyncio
import signal
from uuid import uuid4

import grpclib.server
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from hharon import domain, infra, usecases
from hharon.app.server import di
from hharon.app.server.grpc_handler import HharonServiceHandler
from hharon.app.server.health import create_health_service
from hharon.app.server.utils import configure_logger

log = structlog.stdlib.get_logger("hharon.server")


async def process_task(
    outbox: usecases.OutboxUsecase[AsyncSession],
    handler_manager: usecases.TaskHandlerManager[AsyncSession],
    task: domain.OutboxTask,
) -> None:
    """Process a single outbox task."""
    with structlog.contextvars.bound_contextvars(
        task_id=str(task.id),
        task_attempt=task.attempts,
        task_trace_id=str(uuid4()),
    ):
        try:
            log.debug("Processing task", task_type=task.task_type)
            async with outbox.context(task) as ctx:
                handler = handler_manager.get_handler_for(task.task_type)
                await handler.handle(ctx=ctx, task=task)
            log.info("Task processed successfully")
        except Exception as e:
            log.exception("Error processing task", error=e)


async def run_outbox_worker(
    outbox: usecases.OutboxUsecase[AsyncSession],
    handler_manager: usecases.TaskHandlerManager[AsyncSession],
) -> None:
    """Run outbox task worker loop."""
    prefetch_count = 5
    log.info("Starting outbox worker", prefetch_count=prefetch_count)

    while True:
        try:
            tasks = await outbox.retrieve_ready_tasks(outbox.RetrieveReadyTasksRequest(limit=prefetch_count))
            if not tasks:
                log.debug("No tasks to process, waiting...")
                await asyncio.sleep(5)
                continue

            log.info("Processing tasks", count=len(tasks))
            async with asyncio.TaskGroup() as tg:
                for task in tasks:
                    _ = tg.create_task(process_task(outbox, handler_manager, task))

        except asyncio.CancelledError:
            log.info("Outbox worker cancelled, shutting down")
            break
        except Exception as e:
            log.exception("Error in outbox worker loop", error=e)
            await asyncio.sleep(5)


async def run_grpc_server(
    handler: HharonServiceHandler,
    config: infra.GrpcServerConfig,
) -> None:
    """Run gRPC server."""
    server = grpclib.server.Server([handler, create_health_service()])
    await server.start(config.host, config.port)
    log.info("gRPC server started", host=config.host, port=config.port)

    try:
        await server.wait_closed()
    except asyncio.CancelledError:
        log.info("gRPC server cancelled, shutting down")
        server.close()
        await server.wait_closed()


async def main() -> None:
    """Main entry point."""
    config = await di.container.get(infra.GlobalConfig)

    configure_logger(
        json_mode=False,
        log_level="DEBUG" if config.debug else "INFO",
    )
    log.info("Starting hharon server")

    grpc_handler = await di.container.get(HharonServiceHandler)
    grpc_config = await di.container.get(infra.GrpcServerConfig)
    outbox = await di.container.get(usecases.OutboxUsecase[AsyncSession])
    handler_manager = await di.container.get(usecases.TaskHandlerManager[AsyncSession])

    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        log.info("Shutdown signal received, stopping server")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    grpc_task = asyncio.create_task(run_grpc_server(grpc_handler, grpc_config))
    worker_task = asyncio.create_task(run_outbox_worker(outbox, handler_manager))

    log.info("Server started successfully")

    try:
        _ = await shutdown_event.wait()
    except KeyboardInterrupt:
        log.info("Keyboard interrupt received")
    finally:
        log.info("Stopping server")
        _ = grpc_task.cancel()
        _ = worker_task.cancel()

        _ = await asyncio.gather(grpc_task, worker_task, return_exceptions=True)
        await di.container.close()
        log.info("Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
