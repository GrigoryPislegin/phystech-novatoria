from __future__ import annotations

import asyncio
from typing import final

import structlog

from nanimai_platform.protocols.external.message_queue import (
    Message,
    MessageQueueError,
    MessageQueueProtocol,
)
from nanimai_platform.services.message_consumer.handlers.base import (
    MessageHandler,
    MessageHandlerError,
    MessageHandlerInvalidDataError,
)
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.MessageConsumerService")


class MessageConsumerServiceError(Exception): ...


@final
class MessageConsumerService:
    def __init__(
        self,
        message_queue_adapter: MessageQueueProtocol,
        handlers: list[MessageHandler],
    ):
        self._message_queue = message_queue_adapter
        self._handlers = {handler.queue_name: handler for handler in handlers}
        self._running = False
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def active_queues(self) -> list[str]:
        return list(self._handlers.keys())

    @span(op="message_consumer_service", name="start")
    async def start(self) -> None:
        if self._running:
            log.warning("message consumer service already running")
            return

        log.info(
            "starting message consumer service",
            queues=list(self._handlers.keys()),
        )

        self._running = True

        try:
            await self._message_queue.connect()
            log.info("connected to message queue")

            for queue_name, handler in self._handlers.items():
                task = asyncio.create_task(
                    self._consume_queue(handler),
                    name=f"consumer_{queue_name}",
                )
                self._tasks[queue_name] = task
                log.info(
                    "started consumer for queue",
                    queue_name=queue_name,
                    handler=handler.name,
                )

            log.info(
                "message consumer service started",
                active_consumers=len(self._tasks),
            )

        except Exception as e:
            log.error("failed to start message consumer service", error=str(e))
            self._running = False
            raise MessageConsumerServiceError(f"Failed to start: {e}") from e

    @span(op="message_consumer_service", name="stop")
    async def stop(self) -> None:
        if not self._running:
            log.warning("message consumer service not running")
            return

        log.info("stopping message consumer service")
        self._running = False

        for queue_name, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                log.debug("consumer task cancelled", queue_name=queue_name)

        self._tasks.clear()

        try:
            await self._message_queue.disconnect()
            log.info("disconnected from message queue")
        except Exception as e:
            log.error("error disconnecting from message queue", error=str(e))

        log.info("message consumer service stopped")

    async def _consume_queue(self, handler: MessageHandler) -> None:
        retry_delay = 5

        while self._running:
            try:
                await self._process_queue_messages(handler)
            except asyncio.CancelledError:
                log.debug("queue consumer cancelled", queue_name=handler.queue_name)
                raise
            except MessageQueueError as e:
                log.error(
                    "message queue error, retrying",
                    queue_name=handler.queue_name,
                    error=str(e),
                    retry_delay=retry_delay,
                )
            except Exception as e:
                log.error(
                    "unexpected error in queue consumer, retrying",
                    queue_name=handler.queue_name,
                    error=str(e),
                    exc_info=True,
                    retry_delay=retry_delay,
                )

            if self._running:
                await asyncio.sleep(retry_delay)

    async def _process_queue_messages(self, handler: MessageHandler) -> None:
        async for message in self._message_queue.pull(
            handler.queue_name,
            prefetch_count=handler.prefetch_count,
            auto_ack=False,
        ):
            await self._handle_message(message, handler)

    @span(op="message_consumer_service", name="handle_message")
    async def _handle_message(self, message: Message, handler: MessageHandler) -> None:
        log.debug(
            "received message",
            queue_name=handler.queue_name,
            handler=handler.name,
            delivery_tag=message.delivery_tag,
            routing_key=message.routing_key,
        )

        try:
            await handler.handle(message)
            await self._message_queue.ack(message)
            log.info(
                "message acknowledged after success",
                queue_name=handler.queue_name,
                delivery_tag=message.delivery_tag,
            )
        except MessageHandlerInvalidDataError as e:
            log.warning(
                "invalid message data, rejecting without requeue",
                queue_name=handler.queue_name,
                delivery_tag=message.delivery_tag,
                error=str(e),
            )
            try:
                await self._message_queue.reject(message, requeue=False)
            except Exception as reject_error:
                log.error(
                    "failed to reject invalid message",
                    queue_name=handler.queue_name,
                    delivery_tag=message.delivery_tag,
                    error=str(reject_error),
                )
        except MessageHandlerError as e:
            log.error(
                "handler error processing message, nacking for requeue",
                queue_name=handler.queue_name,
                delivery_tag=message.delivery_tag,
                error=str(e),
            )
            try:
                await self._message_queue.nack(message, requeue=True)
                log.debug(
                    "message nacked for requeue",
                    queue_name=handler.queue_name,
                    delivery_tag=message.delivery_tag,
                )
            except Exception as nack_error:
                log.error(
                    "failed to nack message",
                    queue_name=handler.queue_name,
                    delivery_tag=message.delivery_tag,
                    error=str(nack_error),
                )
        except Exception as e:
            log.error(
                "unexpected error processing message, nacking for requeue",
                queue_name=handler.queue_name,
                delivery_tag=message.delivery_tag,
                error=str(e),
                exc_info=True,
            )
            try:
                await self._message_queue.nack(message, requeue=True)
                log.debug(
                    "message nacked for requeue",
                    queue_name=handler.queue_name,
                    delivery_tag=message.delivery_tag,
                )
            except Exception as nack_error:
                log.error(
                    "failed to nack message",
                    queue_name=handler.queue_name,
                    delivery_tag=message.delivery_tag,
                    error=str(nack_error),
                )
