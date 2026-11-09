import json
from collections import defaultdict
from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import TYPE_CHECKING, NoReturn, TypedDict, Unpack, final, overload

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from hharon.protocols.resume_search_scan import protocol as resume_search_scan_protocol

if TYPE_CHECKING:
    import httpx._types as httpx_types

    type Params = (
        BaseModel
        | Sequence[BaseModel]
        | httpx.QueryParams
        | Mapping[str, httpx_types.PrimitiveData]
        | Mapping[str, Sequence[httpx_types.PrimitiveData]]
        | Sequence[tuple[str, httpx_types.PrimitiveData]]
        | tuple[tuple[str, httpx_types.PrimitiveData], ...]
        | str
        | bytes
    )

    class RequestKwargs(TypedDict, total=False):
        content: BaseModel | httpx_types.RequestContent
        data: BaseModel | httpx_types.RequestData
        files: httpx_types.RequestFiles
        json: BaseModel | Mapping[str, object]
        params: Params
        headers: httpx_types.HeaderTypes
        cookies: httpx_types.CookieTypes
        timeout: httpx_types.TimeoutTypes
        extensions: httpx_types.RequestExtensions

    class RawRequestKwargs(TypedDict, total=False):
        content: httpx_types.RequestContent
        data: httpx_types.RequestData
        files: httpx_types.RequestFiles
        json: dict[str, object]
        params: httpx_types.QueryParamTypes
        headers: httpx_types.HeaderTypes
        cookies: httpx_types.CookieTypes
        timeout: httpx_types.TimeoutTypes
        extensions: httpx_types.RequestExtensions


log = structlog.stdlib.get_logger("hharon.infra.BaseHHClient")


class HHClientConfig(BaseModel):
    """Configuration for HeadHunter HTTP client."""

    user_agent: str = "hharon/1.0"
    timeout: float = 30.0
    base_url: str = "https://api.hh.ru"


class RawHeadHunterClient(httpx.AsyncClient):
    """Raw Async HTTPX client for HeadHunter API."""


async def provide_headhunter_httpx_client(config: HHClientConfig) -> AsyncGenerator[RawHeadHunterClient]:
    """Provide configured httpx.AsyncClient for HeadHunter API."""

    client = RawHeadHunterClient(
        base_url=config.base_url,
        headers={"User-Agent": config.user_agent},
        timeout=config.timeout,
    )
    yield client

    await client.aclose()


class HHClientError(Exception):
    """Base exception for HH client errors."""


@final
class HHHTTPError(HHClientError):
    """HTTP error in HH API request."""

    def __init__(self, message: str, status_code: int, response_text: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class HHRequestError(HHClientError):
    """Network/request error in HH API call."""


class HHValidationError(HHClientError):
    """Validation error when parsing HH API response."""


def extract_retry_after(response_text: str) -> int | None:
    """Extract retry_after from HH API error response JSON."""
    try:
        data: dict[str, object] = json.loads(response_text)  # pyright: ignore[reportAny]
        retry_after_value = data.get("retry_after")
        if retry_after_value is not None and isinstance(retry_after_value, (int, str)):
            return int(retry_after_value)
    except Exception as e:
        log.debug("failed to extract retry_after from response", error=str(e))
    return None


def handle_hh_http_error(  # noqa: PLR0913
    e: HHHTTPError,
    *,
    operation: str,
    forbid_403_msg: str = "Access denied",
    forbid_404_msg: str | None = "Not found or no access",
    rate_limit_error_cls: type[Exception],
    access_denied_error_cls: type[Exception],
    generic_error_cls: type[Exception],
    **log_extra: object,
) -> NoReturn:
    if e.status_code == httpx.codes.TOO_MANY_REQUESTS:  # pyright: ignore[reportUnnecessaryComparison]
        retry_after = extract_retry_after(e.response_text)
        log.warning("rate limit hit", retry_after=retry_after, operation=operation, **log_extra)
        raise rate_limit_error_cls("Rate limit exceeded", retry_after=retry_after) from e  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]
    if e.status_code == httpx.codes.FORBIDDEN:  # pyright: ignore[reportUnnecessaryComparison]
        log.exception("access denied", status_code=e.status_code, operation=operation, **log_extra)
        raise access_denied_error_cls(forbid_403_msg) from e
    if e.status_code == httpx.codes.NOT_FOUND:  # pyright: ignore[reportUnnecessaryComparison]
        msg = forbid_404_msg if forbid_404_msg is not None else forbid_403_msg
        if forbid_404_msg is None:
            log.exception("access denied", status_code=e.status_code, operation=operation, **log_extra)
        else:
            log.warning("not found or no access", status_code=e.status_code, operation=operation, **log_extra)
        raise access_denied_error_cls(msg) from e
    error_msg = f"HTTP error: {e.status_code}"
    log.exception("HTTP error", status_code=e.status_code, operation=operation, **log_extra)
    raise generic_error_cls(error_msg) from e


def handle_resume_search_http_error(e: HHHTTPError, operation: str, **log_extra: object) -> NoReturn:
    """Handle HH HTTP error for resume search operations (поиск резюме по фильтрам)."""
    handle_hh_http_error(
        e,
        operation=operation,
        forbid_403_msg="Access denied to resume search",
        forbid_404_msg="Resume search not found or no access",
        rate_limit_error_cls=resume_search_scan_protocol.HeadHunterRateLimitError,
        access_denied_error_cls=resume_search_scan_protocol.HeadHunterAccessDeniedError,
        generic_error_cls=resume_search_scan_protocol.HeadHunterResumeSearchScanError,
        **log_extra,
    )


@final
class HeadHunterClient:
    """Base class for all HH API adapters"""

    def __init__(self, client: RawHeadHunterClient) -> None:
        self._client = client

    @overload
    async def get(self, url: str, response_model: None, **kwargs: "Unpack[RequestKwargs]") -> httpx.Response: ...

    @overload
    async def get[T: BaseModel](self, url: str, response_model: type[T], **kwargs: "Unpack[RequestKwargs]") -> T: ...

    async def get[T: BaseModel](
        self, url: str, response_model: type[T] | None, **kwargs: "Unpack[RequestKwargs]"
    ) -> T | httpx.Response:
        return await self._run(
            request=self._client.build_request("GET", url, **_convert_kwargs(kwargs)),
            response_model=response_model,
        )

    @overload
    async def post(self, url: str, response_model: None, **kwargs: "Unpack[RequestKwargs]") -> httpx.Response: ...

    @overload
    async def post[T: BaseModel](self, url: str, response_model: type[T], **kwargs: "Unpack[RequestKwargs]") -> T: ...

    async def post[T: BaseModel](
        self, url: str, response_model: type[T] | None, **kwargs: "Unpack[RequestKwargs]"
    ) -> T | httpx.Response:
        return await self._run(
            request=self._client.build_request("POST", url, **_convert_kwargs(kwargs)),
            response_model=response_model,
        )

    @overload
    async def put(self, url: str, response_model: None, **kwargs: "Unpack[RequestKwargs]") -> httpx.Response: ...

    @overload
    async def put[T: BaseModel](self, url: str, response_model: type[T], **kwargs: "Unpack[RequestKwargs]") -> T: ...

    async def put[T: BaseModel](
        self, url: str, response_model: type[T] | None, **kwargs: "Unpack[RequestKwargs]"
    ) -> T | httpx.Response:
        return await self._run(
            request=self._client.build_request("PUT", url, **_convert_kwargs(kwargs)),
            response_model=response_model,
        )

    @overload
    async def _run(self, request: httpx.Request, response_model: None) -> httpx.Response: ...

    @overload
    async def _run[T: BaseModel](self, request: httpx.Request, response_model: type[T]) -> T: ...

    async def _run[T: BaseModel](self, request: httpx.Request, response_model: type[T] | None) -> T | httpx.Response:
        """Execute HTTP request and validate response.

        Args:
            request: httpx.Request to execute
            response_model: Pydantic model to validate response against

        Returns:
            Validated response as instance of response_model

        Raises:
            HHHTTPError: On HTTP status errors (4xx, 5xx)
            HHRequestError: On network/request errors
            HHValidationError: On response validation errors
        """
        try:
            response = await self._client.send(request)
            _ = response.raise_for_status()

            if response_model is None:
                return response

            try:
                return response_model.model_validate_json(response.content)
            except ValidationError as e:
                response_text = response.text[:500]
                log.exception("failed to validate response", response=response_text, errors=e.errors())
                error_msg = f"Failed to validate JSON response: {response_text}"
                raise HHValidationError(error_msg) from e
            except Exception as e:
                response_text = response.text[:500]
                log.exception("failed to decode response", response=response_text)
                error_msg = f"Failed to parse JSON response: {response_text}"
                raise HHValidationError(error_msg) from e
        except httpx.HTTPStatusError as e:
            r = e.response
            log.exception(
                "HTTP error in HH API request",
                status_code=e.response.status_code,
                error=str(e),
                response_text=e.response.text[:500],
            )
            error_msg = f"HTTP error in HH API: {r.status_code} - {r.text[:500]}"
            raise HHHTTPError(error_msg, r.status_code, r.text[:500]) from e
        except httpx.RequestError as e:
            log.exception(
                "Request error in HH API call",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise HHRequestError("Request error in HH API") from e
        except HHClientError:
            raise
        except Exception as e:
            log.exception(
                "Unexpected error in HH API call",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise HHClientError("Unexpected error in HH API") from e


def _convert_kwargs(kwargs: "RequestKwargs") -> "RawRequestKwargs":  # noqa: C901, PLR0912
    new_kwargs: dict[str, object] = {}

    # content should be serialized as json bytes
    if content := kwargs.get("content"):
        new_content = content
        if isinstance(content, BaseModel):
            new_content = content.model_dump_json(by_alias=True, exclude_defaults=True)
        new_kwargs["content"] = new_content

    # data should be serialized to dict
    if data := kwargs.get("data"):
        new_data = data
        if isinstance(data, BaseModel):
            new_data = data.model_dump(by_alias=True, exclude_defaults=True)
        new_kwargs["data"] = new_data

    # json should be serialized to dict
    if json := kwargs.get("json"):
        new_kwargs["json"] = json
        if isinstance(json, BaseModel):
            new_kwargs["json"] = json.model_dump(by_alias=True, exclude_defaults=True)

    # files are unchanged
    if files := kwargs.get("files"):
        new_kwargs["files"] = files

    # params has complex serialization
    if params := kwargs.get("params"):
        # pass original value (if not original type, it would be overriden later)
        new_params = params

        # if params is BaseModel, serialize as dict
        if isinstance(params, BaseModel):
            new_params = params.model_dump(by_alias=True, exclude_defaults=True)

        # if params is list of BaseModel or tuples
        if isinstance(params, list):
            new_params_build = defaultdict[str, list[str | int | float | bool | None]](list)
            serialized_param_sets: list[dict[str, str | int | float | bool | None]] = []

            for param in params:
                # if tuples - serialize as dict (key: list[values])
                if isinstance(param, tuple):
                    # append to previous values
                    key, value = param
                    new_params_build[key].append(value)
                    continue

                # if pydantic model - serialize as dict and save for merging
                serialized_param_sets.append(param.model_dump(by_alias=True, exclude_defaults=True))

            # merge serialized param sets into a single dict
            # [{"a": "b"}, {"a": "e", "c": "d"}, {}] -> {"a": ["b", "e"], "c": ["d"]}
            for param_set in serialized_param_sets:
                for key, value in param_set.items():
                    new_params_build[key].append(value)

            new_params = dict(new_params_build)  # finalize

        new_kwargs["params"] = new_params

    if headers := kwargs.get("headers"):
        new_kwargs["headers"] = headers

    if cookies := kwargs.get("cookies"):
        new_kwargs["cookies"] = cookies

    if timeout := kwargs.get("timeout"):
        new_kwargs["timeout"] = timeout

    if extensions := kwargs.get("extensions"):
        new_kwargs["extensions"] = extensions

    # actual type is correct, but static type checker is not able to infer it (since its created in runtime)
    return new_kwargs  # type: ignore[return-value] # pyright: ignore[reportReturnType]
