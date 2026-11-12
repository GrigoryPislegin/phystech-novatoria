from typing import override

import aiohttp
import structlog

import nanimai_platform.protocols.external.notification as protocol

log = structlog.stdlib.get_logger("app.adapters.TelegramStaticNotificationAdapter")


class TelegramStaticNotificationAdapter(protocol.NotificationProtocol):
    chat: str
    thread_id: str | None
    base_url: str

    def __init__(self, token: str, report_chat: str):
        self.chat = report_chat
        self.thread_id = report_chat.split("_")[-1] if "_" in report_chat else None
        self.base_url = f"https://api.telegram.org/bot{token}"

    @override
    async def push(self, message: str) -> None:
        log.info("pushing message to telegram", message=message, chat=self.chat)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    data={
                        "chat_id": self.chat,
                        "message_thread_id": self.thread_id,
                        "text": message,
                    },
                ) as response:
                    payload = await response.read()
                    if response.status == 404:
                        log.error("failed to send message to telegram", status=response.status, body=payload)
                        raise protocol.NotificationReceiverUnreachable("chat not found")

                    if response.status == 408:
                        log.error("failed to send message to telegram", status=response.status, body=payload)
                        raise protocol.NotificationTimeout("timeout")

                    if response.status // 100 != 2:
                        log.error("failed to send message to telegram", status=response.status, body=payload)
                        raise protocol.NotificationReceiverUnreachable("unknown error")

        except aiohttp.ClientError as e:
            log.error("failed to send message to telegram", err=e)
            raise protocol.NotificationReceiverUnreachable("chat not found") from e
        except Exception as e:
            log.error("failed to send message to telegram", err=e)
            raise protocol.NotificationError("unknown error") from e
