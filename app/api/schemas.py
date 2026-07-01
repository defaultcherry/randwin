from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TelegramWebAppPayload(BaseModel):
    init_data: str = Field(min_length=1)


class JoinGiveawayPayload(TelegramWebAppPayload):
    hcaptcha_token: str | None = None


class GiveawayPublicResponse(BaseModel):
    id: int
    title: str
    announcement_message: str
    button_color: str
    require_captcha: bool
    prize_places: int
    channel_id: str
    channel_title: str | None = None
    channel_username: str | None = None
    starts_at: datetime
    ends_at: datetime
    status: str
    participants_count: int
    winner_ids: list[int] | None = None
    winner_snapshots: list[dict] = Field(default_factory=list)


class GiveawayViewResponse(BaseModel):
    giveaway: GiveawayPublicResponse
    viewer_state: str
    viewer_telegram_id: int | None = None
    viewer_name: str | None = None
    subscription_status: str | None = None


class GiveawayCreateDraft(BaseModel):
    announcement_message: str = Field(min_length=1, max_length=4000)
    button_color: str = Field(min_length=4, max_length=32)
    require_captcha: bool = True
    prize_places: int = Field(ge=1, le=50)
    starts_at: datetime
    ends_at: datetime

    @field_validator("button_color")
    @classmethod
    def normalize_button_color(cls, value: str) -> str:
        value = value.strip()
        allowed = {"primary", "success", "danger", "default"}
        if value not in allowed:
            raise ValueError("button_color must be primary, success, danger or default")
        return value

    @field_validator("ends_at")
    @classmethod
    def validate_period(cls, ends_at: datetime, info):
        starts_at = info.data.get("starts_at")
        if starts_at and ends_at <= starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return ends_at


class GiveawayCreateState(BaseModel):
    announcement_message: str
    button_color: str
    prize_places: int
    starts_at: datetime
    ends_at: datetime
