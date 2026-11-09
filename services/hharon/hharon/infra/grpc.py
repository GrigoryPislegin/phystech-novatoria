from pydantic import BaseModel, Field


class GrpcServerConfig(BaseModel):
    """Configuration for gRPC server."""

    host: str = Field(default="0.0.0.0", description="gRPC server host")  # noqa: S104
    port: int = Field(default=50051, description="gRPC server port")

    log_requests: bool = Field(default=False, description="Log incoming requests")
    log_responses: bool = Field(default=False, description="Log outgoing responses")
