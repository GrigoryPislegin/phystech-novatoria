from typing import final, override

import aio_pika
from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractRobustConnection

from hharon.infra.message_queue import RabbitMQConfig, setup_rabbitmq_topology
from hharon.protocols.message_queue.push_protocol import (
    PushingProtocol,
    PushingProtocolError,
    PushingProtocolPublishError,
    PushingProtocolQueueConnectionError,
)


@final
class RabbitMQPushAdapter(PushingProtocol):
    def __init__(self, connection: AbstractRobustConnection, config: RabbitMQConfig):
        self._connection = connection
        self._config = config

    @override
    async def push(self, message: PushingProtocol.Message, queue_name: str) -> None:
        try:
            async with self._connection.channel() as channel:
                await setup_rabbitmq_topology(channel, self._config.exchange_name, queue_name)
                exchange = await channel.get_exchange(self._config.exchange_name)

                amqp_message = Message(
                    body=message.payload,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/x-protobuf",
                    message_id=message.id,
                    timestamp=message.timestamp,
                )
                _ = await exchange.publish(amqp_message, routing_key=queue_name)
        except aio_pika.exceptions.AMQPError as e:
            raise PushingProtocolPublishError from e
        except ConnectionError as e:
            raise PushingProtocolQueueConnectionError from e
        except Exception as e:
            raise PushingProtocolError from e
