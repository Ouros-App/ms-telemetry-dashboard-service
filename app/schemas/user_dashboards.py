from datetime import datetime
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


class UserDashboardDataStatus(BaseModel):
    status: Literal["fresh", "stale", "unknown"]
    last_updated_at: datetime | None
    age_seconds: int | None
    stale_after_seconds: int


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
    period_days: int = Field(default=30, ge=1, le=732)
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


class CorporateKpiItem(BaseModel):
    value: float
    formatted: str
    unit: str | None = None
    year: int | None = None


class CorporateKpisResponse(BaseModel):
    spend_previous_year: CorporateKpiItem
    spend_current_year: CorporateKpiItem
    avg_cost_per_bird: CorporateKpiItem
    total_lots: CorporateKpiItem


class CorporateFilterOptionsResponse(BaseModel):
    periods: list[str]
    states: list[str]
    regional_managements: list[str]


class FarmSummaryItem(BaseModel):
    farm_id: int
    farm_name: str
    manager_name: str | None = None
    location: str
    total_consumption: str
    lots_count: int
    avg_lot_cost: float
    avg_cost_per_bird: float


class CorporateFarmsTableResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[FarmSummaryItem]


class CorporateCostBucketItem(BaseModel):
    bucket: str
    label: str
    low: float
    high: float | None = None
    count: int
    value: int
    total_cost: float
    percentage: float


class CorporateCostByLotSizeCohortItem(BaseModel):
    cohort: str
    previous_year_cost: float
    current_year_cost: float
    previous_year_lots: int = 0
    current_year_lots: int = 0


class CorporateCostByRegionItem(BaseModel):
    region: str
    previous_year_cost: float
    current_year_cost: float


class CorporateMonthlyCostItem(BaseModel):
    month: int
    month_label: str
    previous_year_cost: float
    current_year_cost: float
    cost: float
