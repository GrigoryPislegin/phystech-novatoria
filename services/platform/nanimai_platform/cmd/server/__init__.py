import uvicorn

from . import api as api
from . import app as app
from . import dependencies as dependencies
from . import di as di
from . import middlewares as middlewares
from . import utils as utils
from .app import application_factory as application_factory


async def main():
    server = uvicorn.Server(
        uvicorn.Config(
            "nanimai_platform.cmd.server:application_factory",
            host="0.0.0.0",
            port=8080,
            factory=True,
            lifespan="on",
            reload=True,
            use_colors=False,
            access_log=False,
        )
    )
    await server.serve()
