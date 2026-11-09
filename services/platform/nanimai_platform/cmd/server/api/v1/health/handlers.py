from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, responses, status

from nanimai_platform.infra.config import PlatformConfig

router = APIRouter(tags=["health"])


@router.get("", status_code=status.HTTP_200_OK, response_class=responses.JSONResponse)
@inject
async def health_handler(
    config: FromDishka[PlatformConfig],
):
    return {
        "status": "ok",
        "version": config.version,
    }
