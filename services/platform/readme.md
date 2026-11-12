# NanimAI Platform

<div align = center><img src=".github/assets/banner.png"><br><br>

&ensp;[<kbd> <br> Overview <br> </kbd>](#overview)&ensp;
&ensp;[<kbd> <br> Technologies <br> </kbd>](#technologies)&ensp;
&ensp;[<kbd> <br> Deploy <br> </kbd>](#deploy)&ensp;
<br><br><br><br></div>

## Overview
Modular monolith application for serving [NanimAI](https://nanimai.tech) HR platform built in python with hexagonal architecture approach.


## Technologies
- [Python 3.12](https://www.python.org/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Structlog](https://www.structlog.org/en/stable/)
- [MongoDB](https://www.mongodb.com/)
- [Beanie](https://github.com/roman-right/beanie)
- [Poetry](https://python-poetry.org/)

## Deploy
1. You can launch the server in **development** mode using:
```bash
# using just
just dev-server
# or using executable python module
poetry run python3 -m nanimai_platform.cmd.server
# or using launcher
poetry run python3 -m nanimai_platform server
# or using uvicorn
poetry run uvicorn \
    --reload \
    --host localhost \
    --port 8080 \
    --lifespan on \
    --factory nanimai_platform.cmd.server:application_factory
```
Each of these methods use `uvicorn` to launch the application.

2. You can launch the worker in **development** mode using:
```bash
# using just
just dev-llm-worker
# or using executable python module
poetry run python3 -m nanimai_platform.cmd.llm_worker
# or using launcher
poetry run python3 -m nanimai_platform llm-worker
```


### Production
For production usage consider building [dockerfile](./dockerfile) and configuring it using `config.toml` file (see [example config](./example.config.toml)) (or env variables see [configuration class](./nanimai_platform/cmd/server/config.py))

## File Structure
```plaintext
platform
├── nanimai_platform
│   ├── adapters                    # implementations of protocols
│   │   ├── external                # parsers, scrapers, http request handlers, message queues (read only)
│   │   └── internal                # databases, caches, message queues (write only)
│   ├── cmd                         # executable python modules (commands)
│   │   └── server                  # fastapi server implementation
│   ├── core
│   │   └── domain
│   │       ├── models              # domain business models - define what data each logical data type stores
│   │       └── services            # implemented business logic on only logical level, uses protocols as restriction for dependency injection of adapters 
│   └── protocols
│       ├── external                # interfaces (ports) for external adapters
│       └── internal                # interfaces (ports) for interal adapters
├── dockerfile                      # http server dockerfile
├── poetry.lock                     # dependecies hashes
├── poetry.toml                     # poetry config
├── pyproject.toml                  # package config, depenencies and utilities configurations
└── readme.md                       # project readme
```