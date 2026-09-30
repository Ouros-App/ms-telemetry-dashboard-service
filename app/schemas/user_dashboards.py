from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UserChartType = Literal["indicator", "bar", "line", "pie"]
UserChartRenderType = str


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
    render_options: list[UserChartRenderType] = Field(default_factory=list)


class UserChartPublic(BaseModel):
    id: str
    title: str
    type: UserChartType
    default_render_as: UserChartRenderType
    render_options: list[UserChartRenderType]


class UserChartListResponse(BaseModel):
    items: list[UserChartPublic]


class CustomDashboardChartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    render_as: UserChartRenderType = "auto"


class CustomDashboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    period_days: int = Field(default=30, ge=1, le=366)
    charts: list[CustomDashboardChartRequest] = Field(min_length=1, max_length=4)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title cannot be blank")
        return value

    @model_validator(mode="after")
    def unique_chart_ids(self) -> "CustomDashboardRequest":
        chart_ids = [chart.chart_id for chart in self.charts]
        if len(chart_ids) != len(set(chart_ids)):
            raise ValueError("chart_ids must be unique")
        return self


class CustomDashboardChart(BaseModel):
    id: str
    title: str
    render_as: UserChartRenderType
    html: str


class CustomDashboardResponse(BaseModel):
    title: str
    charts: list[CustomDashboardChart]
