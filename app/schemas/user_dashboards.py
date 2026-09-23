from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UserChartType = Literal["indicator", "bar", "line", "pie"]


class UserDashboardRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)


class UserDashboardPublic(BaseModel):
    id: str
    title: str
    description: str

    @classmethod
    def from_record(cls, dashboard: UserDashboardRecord) -> "UserDashboardPublic":
        return cls.model_validate(dashboard.model_dump())


class UserDashboardListResponse(BaseModel):
    items: list[UserDashboardPublic]


class UserChartSeries(BaseModel):
    field: str = Field(min_length=1)
    label: str = Field(min_length=1, max_length=100)


class UserChartDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    dashboard_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    title: str = Field(min_length=1, max_length=200)
    type: UserChartType
    query_name: str = Field(min_length=1)
    x_field: str | None = None
    label_field: str | None = None
    value_field: str | None = None
    value_suffix: str = Field(default="", max_length=20)
    series: list[UserChartSeries] = Field(default_factory=list)


class UserChartPublic(BaseModel):
    id: str
    title: str
    type: UserChartType


class UserChartListResponse(BaseModel):
    items: list[UserChartPublic]
