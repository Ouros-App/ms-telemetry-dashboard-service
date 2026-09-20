from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str = Field(description="Human-readable service message")


class HealthResponse(BaseModel):
    status: str = Field(description="Current service health status")


class ReadinessResponse(BaseModel):
    status: str = Field(description="Current service readiness status")
    errors: list[str] = Field(default_factory=list, description="Configuration errors when the service is not ready")


class ErrorResponse(BaseModel):
    detail: str = Field(description="Human-readable error detail")
