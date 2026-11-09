import asyncio
import sys

from nanimai_platform.cmd import server

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: nanimai_platform <target>")
        exit(1)

    target = sys.argv[1].lower().strip().replace("-", "_")

    if target == "server":
        asyncio.run(server.main())
    else:
        print(f"unknown target: {target}")
        exit(1)
