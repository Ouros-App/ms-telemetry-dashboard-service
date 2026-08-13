from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DashboardRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    provider: Literal["databricks"]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    dashboard_id: str = Field(min_length=1, max_length=200)
    enabled: bool = True


class DashboardPublic(BaseModel):
    id: str
    title: str
    description: str
    provider: str

    @classmethod
    def from_record(cls, dashboard: DashboardRecord) -> "DashboardPublic":
        return cls.model_validate(dashboard.model_dump(include={"id", "title", "description", "provider"}))


class DashboardListResponse(BaseModel):
    items: list[DashboardPublic]


class EmbedRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    external_viewer_id: str | None = Field(default=None, min_length=1, max_length=512, pattern=r"^[A-Za-z0-9._:-]+$")
    external_value: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_external_context(self) -> "EmbedRequest":
        if any(ord(char) < 32 for char in (self.external_value or "")):
            raise ValueError("external_value contains control characters")
        size = sum(len(value.encode("utf-8")) for value in (self.external_viewer_id or "", self.external_value or ""))
        if size > 1024:
            raise ValueError("external context must not exceed 1 KB")
        return self


class EmbedConfig(BaseModel):
    instance_url: str
    workspace_id: str
    dashboard_id: str
    token: str
    expires_at: datetime


class EmbedResponse(BaseModel):
    dashboard_id: str
    provider: str
    embed: EmbedConfig


class DatabricksTokenResponse(BaseModel):
    access_token: str = Field(min_length=1)
    expires_in: int | None = Field(default=None, ge=1)


class DatabricksTokenInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    authorization_details: Any
