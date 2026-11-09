import asyncio

from nanimai_platform.cmd.server import main

if __name__ == "__main__":
    # called when run with `python3 -m nanimai_platform.cmd.server`
    asyncio.run(main())
