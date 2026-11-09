from dataclasses import dataclass

from grpclib.const import Status as GRPCStatus
from grpclib.exceptions import GRPCError


@dataclass
class AdvancedGRPCError(Exception):
    grpc_status: GRPCStatus
    http_code: int
    detail: str
    log: str

    @classmethod
    def from_grpc(cls, grpc_error: GRPCError) -> "AdvancedGRPCError":
        grpc_status = grpc_error.status
        http_code = GRPC_TO_HTTP.get(grpc_status, 500)
        detail = CLIENT_MSG[http_code]
        log = LOG_MSG[http_code]
        return cls(
            grpc_status=grpc_status,
            http_code=http_code,
            detail=detail,
            log=log,
        )

    @classmethod
    def from_adv(cls, adv_error: "AdvancedGRPCError") -> "AdvancedGRPCError":
        return cls(
            grpc_status=adv_error.grpc_status,
            http_code=adv_error.http_code,
            detail=adv_error.detail,
            log=adv_error.log,
        )


GRPC_TO_HTTP = {
    GRPCStatus.INVALID_ARGUMENT: 400,
    GRPCStatus.UNAUTHENTICATED: 401,
    GRPCStatus.PERMISSION_DENIED: 403,
    GRPCStatus.NOT_FOUND: 404,
    GRPCStatus.ALREADY_EXISTS: 409,
    GRPCStatus.RESOURCE_EXHAUSTED: 429,
    GRPCStatus.DEADLINE_EXCEEDED: 504,
    GRPCStatus.UNAVAILABLE: 503,
    GRPCStatus.INTERNAL: 500,
}

CLIENT_MSG = {
    400: "Неверные данные запроса",
    401: "Требуется аутентификация",
    403: "Доступ запрещён",
    404: "Ресурс не найден",
    409: "Конфликт состояния ресурса",
    429: "Превышены лимиты, попробуйте позже",
    503: "Сервис временно недоступен",
    504: "Превышено время ожидания внешнего сервиса",
    500: "Внутренняя ошибка сервиса, попробуйте позже",
}

LOG_MSG = {
    400: "invalid argument",
    401: "unauthenticated",
    403: "permission denied",
    404: "not found",
    409: "conflict",
    429: "rate limited",
    503: "upstream unavailable",
    504: "deadline exceeded (timeout)",
    500: "internal error",
}
