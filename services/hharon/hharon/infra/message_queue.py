from collections.abc import AsyncGenerator

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractRobustConnection
from pydantic import BaseModel


class RabbitMQConfig(BaseModel):
    host: str
    port: int
    username: str
    password: str
    vhost: str = "hharon"
    exchange_name: str
    connection_timeout: float = 10.0
    prefetch_count: int = 1
    max_retries: int = 3


async def provide_rabbitmq_connection(config: RabbitMQConfig) -> AsyncGenerator[AbstractRobustConnection]:
    """Provide a robust RabbitMQ connection with automatic reconnection."""
    connection = await aio_pika.connect_robust(
        host=config.host,
        port=config.port,
        login=config.username,
        password=config.password,
        virtualhost=config.vhost,
        timeout=config.connection_timeout,
    )
    try:
        yield connection
    finally:
        await connection.close()


async def provide_rabbitmq_channel(connection: AbstractConnection) -> AsyncGenerator[AbstractChannel]:
    """Provide a RabbitMQ channel."""
    channel = await connection.channel()
    try:
        yield channel
    finally:
        await channel.close()


async def setup_rabbitmq_topology(
    channel: AbstractChannel,
    exchange_name: str,
    queue_name: str,
) -> None:
    """Setup RabbitMQ exchange and queue with proper bindings.

    Args:
        channel: RabbitMQ channel
        exchange_name: Name of the direct exchange
        queue_name: Name of the queue (also used as routing/binding key)
    """
    # Declare direct exchange
    exchange = await channel.declare_exchange(
        exchange_name,
        ExchangeType.DIRECT,
        durable=True,
    )

    # Declare persistent queue
    queue = await channel.declare_queue(
        queue_name,
        durable=True,
    )

    # Bind queue with routing_key = queue_name
    _ = await queue.bind(exchange, routing_key=queue_name)
