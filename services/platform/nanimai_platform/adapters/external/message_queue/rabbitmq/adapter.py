from collections.abc import AsyncGenerator
from typing import Any, override

import aio_pika
import aio_pika.abc
import structlog

import nanimai_platform.protocols.external.message_queue as protocol

log = structlog.stdlib.get_logger("app.adapters.RabbitMQAdapter")


class RabbitMQAdapter(protocol.MessageQueueProtocol):
    """RabbitMQ implementation of MessageQueueProtocol"""

    dsn: str
    _connection: aio_pika.abc.AbstractRobustConnection | None
    _channels: dict[str, aio_pika.abc.AbstractChannel]

    def __init__(self, dsn: str):
        """Initialize RabbitMQ adapter

        Args:
            dsn: Data source name for RabbitMQ connection (e.g., "amqp://user:pass@host:port/")
        """
        self.dsn = dsn
        self._connection = None
        self._channels = {}

    @override
    async def connect(self) -> None:
        """Establish connection to RabbitMQ"""
        try:
            log.info("connecting to rabbitmq", dsn=self._mask_dsn(self.dsn))
            self._connection = await aio_pika.connect_robust(self.dsn)
            log.info("successfully connected to rabbitmq")
        except Exception as e:
            log.error("failed to connect to rabbitmq", error=str(e))
            raise protocol.MessageQueueConnectionError(f"Failed to connect to RabbitMQ: {e}") from e

    @override
    async def disconnect(self) -> None:
        """Close connection to RabbitMQ"""
        try:
            log.info("disconnecting from rabbitmq")

            for queue_name, channel in self._channels.items():
                try:
                    if not channel.is_closed:
                        await channel.close()
                        log.debug("closed channel for queue", queue_name=queue_name)
                except Exception as e:
                    log.warning("error closing channel for queue", queue_name=queue_name, error=str(e))
            self._channels.clear()

            if self._connection and not self._connection.is_closed:
                await self._connection.close()
                self._connection = None

            log.info("successfully disconnected from rabbitmq")
        except Exception as e:
            log.error("error during rabbitmq disconnection", error=str(e))
            raise protocol.MessageQueueError(f"Error during disconnection: {e}") from e

    async def _get_channel(
        self,
        queue_name: str,
        prefetch_count: int,
    ) -> aio_pika.abc.AbstractChannel:
        """Get or create a dedicated channel for a queue.

        Each queue gets its own channel so that QoS (prefetch_count) settings
        are isolated and don't interfere with other queues.

        Args:
            queue_name: Name of the queue this channel is for
            prefetch_count: Number of messages to prefetch on this channel

        Returns:
            A channel configured with the requested QoS
        """
        if not self._connection or self._connection.is_closed:
            raise protocol.MessageQueueConnectionError("Not connected to RabbitMQ")

        existing = self._channels.get(queue_name)
        if existing is not None and not existing.is_closed:
            return existing

        log.debug("creating new channel for queue", queue_name=queue_name, prefetch_count=prefetch_count)
        channel = await self._connection.channel()  # type: ignore[assignment]
        _ = await channel.set_qos(prefetch_count=prefetch_count)  # type: ignore[union-attr]
        self._channels[queue_name] = channel
        log.debug("channel created and qos configured", queue_name=queue_name, prefetch_count=prefetch_count)
        return channel

    @override
    async def pull(
        self,
        queue_name: str,
        *,
        prefetch_count: int = 1,
        auto_ack: bool = True,
    ) -> AsyncGenerator[protocol.Message, None]:
        """Pull messages from RabbitMQ queue as async generator

        Each queue gets a dedicated channel so that prefetch_count / QoS settings
        are properly isolated when consuming from multiple queues concurrently.

        When ``auto_ack=False``, the caller is responsible for calling
        :meth:`ack`, :meth:`nack`, or :meth:`reject` on every yielded message.
        The adapter will **not** automatically acknowledge or reject the message.

        Args:
            queue_name: Name of the queue to pull messages from
            prefetch_count: Number of messages to prefetch (default: 1)
            auto_ack: Whether to automatically acknowledge messages (default: True)

        Yields:
            Message: Messages from the queue

        Raises:
            MessageQueueConnectionError: Not connected to RabbitMQ
            MessageQueueChannelError: Failed to create or configure channel
            MessageQueueError: Other errors during message pulling
        """
        if not self._connection or self._connection.is_closed:
            log.error("attempted to pull messages without connection")
            raise protocol.MessageQueueConnectionError("Not connected to RabbitMQ")

        try:
            channel = await self._get_channel(queue_name, prefetch_count)

            # Declare queue (idempotent operation)
            queue = await channel.declare_queue(queue_name, passive=True)  # type: ignore[union-attr]
            log.info("starting to pull messages from queue", queue_name=queue_name, auto_ack=auto_ack)

            # Start consuming messages
            async with queue.iterator() as queue_iter:
                async for incoming_message in queue_iter:
                    log.debug(
                        "received message",
                        queue_name=queue_name,
                        routing_key=incoming_message.routing_key,
                        delivery_tag=incoming_message.delivery_tag,
                        body_size=len(incoming_message.body),
                    )

                    if auto_ack:
                        # Let the context manager handle ack/nack automatically.
                        # ignore_processed=True so that if the caller also acks
                        # (unexpectedly), we don't raise.
                        try:
                            async with incoming_message.process(ignore_processed=True):
                                message = self._to_message(incoming_message)
                                yield message
                        except aio_pika.exceptions.MessageProcessError as e:
                            log.error("failed to process message", error=str(e), queue_name=queue_name)
                            continue
                    else:
                        # Manual ack mode: do NOT wrap in process() so the
                        # caller has full control over ack / nack / reject.
                        message = self._to_message(incoming_message)
                        yield message

        except aio_pika.exceptions.ChannelClosed as e:
            # Remove the stale channel reference so the next pull() creates a fresh one.
            _ = self._channels.pop(queue_name, None)
            log.error("channel closed unexpectedly", error=str(e), queue_name=queue_name)
            raise protocol.MessageQueueChannelError(f"Channel closed: {e}") from e
        except aio_pika.exceptions.QueueEmpty as e:
            log.warning("queue is empty", queue_name=queue_name)
            raise protocol.MessageQueueTimeout(f"Queue empty: {e}") from e
        except Exception as e:
            log.error("error while pulling messages", error=str(e), queue_name=queue_name)
            raise protocol.MessageQueueError(f"Error pulling messages: {e}") from e

    @override
    async def ack(self, message: protocol.Message) -> None:
        """Acknowledge message processing

        Args:
            message: Message to acknowledge

        Raises:
            MessageQueueChannelError: Failed to acknowledge message
        """
        try:
            aio_pika_message = self._get_aio_pika_ref(message)
            await aio_pika_message.ack()
            log.debug("message acknowledged", delivery_tag=message.delivery_tag)
        except Exception as e:
            log.error("failed to acknowledge message", error=str(e), delivery_tag=message.delivery_tag)
            raise protocol.MessageQueueChannelError(f"Failed to acknowledge message: {e}") from e

    @override
    async def nack(self, message: protocol.Message, *, requeue: bool = True) -> None:
        """Negative acknowledge message (reject)

        Args:
            message: Message to reject
            requeue: Whether to requeue the message (default: True)

        Raises:
            MessageQueueChannelError: Failed to reject message
        """
        try:
            aio_pika_message = self._get_aio_pika_ref(message)
            await aio_pika_message.nack(requeue=requeue)
            log.debug("message nacked", delivery_tag=message.delivery_tag, requeue=requeue)
        except Exception as e:
            log.error("failed to nack message", error=str(e), delivery_tag=message.delivery_tag)
            raise protocol.MessageQueueChannelError(f"Failed to nack message: {e}") from e

    @override
    async def reject(self, message: protocol.Message, *, requeue: bool = False) -> None:
        """Reject message

        Args:
            message: Message to reject
            requeue: Whether to requeue the message (default: False)

        Raises:
            MessageQueueChannelError: Failed to reject message
        """
        try:
            aio_pika_message = self._get_aio_pika_ref(message)
            await aio_pika_message.reject(requeue=requeue)
            log.debug("message rejected", delivery_tag=message.delivery_tag, requeue=requeue)
        except Exception as e:
            log.error("failed to reject message", error=str(e), delivery_tag=message.delivery_tag)
            raise protocol.MessageQueueChannelError(f"Failed to reject message: {e}") from e

    @staticmethod
    def _to_message(incoming_message: aio_pika.abc.AbstractIncomingMessage) -> protocol.Message:
        """Convert an aio_pika incoming message to a protocol Message."""
        message = protocol.Message(
            body=incoming_message.body,
            delivery_tag=incoming_message.delivery_tag,
            routing_key=incoming_message.routing_key or "",
            exchange=incoming_message.exchange or "",
            headers=dict(incoming_message.headers) if incoming_message.headers else None,
            content_type=incoming_message.content_type,
            content_encoding=incoming_message.content_encoding,
        )
        # Store reference to aio_pika message for ack/nack operations
        message.aio_pika_message_ref = incoming_message
        return message

    @staticmethod
    def _get_aio_pika_ref(message: protocol.Message) -> Any:
        """Extract the underlying aio_pika message reference.

        Raises:
            MessageQueueChannelError: If the reference is missing.
        """
        ref = getattr(message, "aio_pika_message_ref", None)
        if ref is None:
            log.error("message does not have aio_pika reference")
            raise protocol.MessageQueueChannelError("Invalid message: missing internal reference")
        return ref

    def _mask_dsn(self, dsn: str) -> str:
        """Mask sensitive parts of DSN for logging

        Args:
            dsn: Data source name

        Returns:
            Masked DSN string
        """
        try:
            # Simple masking: hide password if present
            if "@" in dsn and "://" in dsn:
                protocol_part, rest = dsn.split("://", 1)
                if "@" in rest:
                    credentials, host_part = rest.split("@", 1)
                    if ":" in credentials:
                        user, _ = credentials.split(":", 1)
                        return f"{protocol_part}://{user}:***@{host_part}"
            return dsn
        except Exception:
            return "***"
