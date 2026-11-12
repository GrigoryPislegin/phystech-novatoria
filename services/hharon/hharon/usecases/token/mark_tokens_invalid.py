from typing import final

import pydantic
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from hharon.protocols import token as token_protocol

log = structlog.stdlib.get_logger("hharon.usecases.token.MarkTokensInvalid")


class MarkTokensInvalidError(Exception):
    """Base exception class for MarkTokensInvalid errors."""


class MarkTokensInvalidNotFoundError(MarkTokensInvalidError):
    """Tokens not found error."""


@final
class MarkTokensInvalid:
    def __init__(
        self,
        *,
        token_repository: token_protocol.HeadHunterTokenRepositoryProtocol[AsyncSession],
    ) -> None:
        self._token_repository = token_repository

    class MarkTokensInvalidRequest(pydantic.BaseModel):
        """Request to mark tokens as invalid."""

        user_id: str

    class MarkTokensInvalidResponse(pydantic.BaseModel):
        """Response after marking tokens as invalid."""

        success: bool = True

    async def mark_tokens_invalid(self, request: MarkTokensInvalidRequest) -> MarkTokensInvalidResponse:
        """Mark tokens as invalid in the repository."""
        try:
            log.debug("Marking tokens as invalid", user_id=request.user_id)

            async with self._token_repository.context() as session:
                _ = await self._token_repository.mark_tokens_invalid(
                    session,
                    token_protocol.HeadHunterTokenRepositoryProtocol.MarkTokensInvalidRequest(user_id=request.user_id),
                )

            log.info("Successfully marked tokens as invalid", user_id=request.user_id)

            return self.MarkTokensInvalidResponse(success=True)
        except token_protocol.HeadHunterTokenRepositoryNotFoundError as e:
            log.warning("Tokens not found", user_id=request.user_id)
            error_msg = f"Tokens not found for user_id: {request.user_id}"
            raise MarkTokensInvalidNotFoundError(error_msg) from e
        except Exception as e:
            log.exception("unexpected error in mark tokens invalid", user_id=request.user_id)
            raise MarkTokensInvalidError("unexpected error") from e
