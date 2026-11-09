from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog.stdlib
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from grpclib.server import Stream

type UnaryHandler[T, I: Message, O: Message] = Callable[[T, I], Awaitable[O]]

log = structlog.stdlib.get_logger("hharon.grpc.handler")


def unary[T, I: Message, O: Message](handler: UnaryHandler[T, I, O]):
    # Возвращаемое значение специально не типизировано, потому что
    # mypy недостаточно умный, чтобы понимать что CoroutineType == Coroutine,
    # a basedpyright не достаточно умный, чтобы я мог писать функцию как протокол:
    # class GrpcHandler[T, I, O](protocol):
    #     async __call__(_, self: T, stream: Stream[I, O]) -> None: ...
    # по при этом, они оба достаточно умные, чтобы самостоятельно выснять возвращаемый тип
    # при ВЫЗОВЕ этого декоратора (те они анализирует не unary, а unary(some_static_function))
    async def wrapper(self: T, stream: Stream[I, O]) -> None:
        # Добавляем trace_id в контекст логирования
        # trace_id будет автоматичеси вставлен во все логи в этом стеке
        with structlog.contextvars.bound_contextvars(trace_id=uuid4().hex):
            request = await stream.recv_message()
            if request is None:
                log.warning("received None (no request), skipping handlers", handler=wrapper.__qualname__)
                return

            log.debug(
                "grpc handler invoked",
                handler=wrapper.__qualname__,
                request=MessageToDict(request, preserving_proto_field_name=True),
            )

            response = await handler(self, request)

            log.debug(
                "grpc handler response",
                handler=wrapper.__qualname__,
                response=MessageToDict(response, preserving_proto_field_name=True),
            )

            await stream.send_message(response)

    wrapper.__qualname__ = handler.__qualname__
    wrapper.__name__ = handler.__name__
    wrapper.__doc__ = handler.__doc__

    return wrapper
