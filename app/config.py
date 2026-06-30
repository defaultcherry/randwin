import os
import uuid
from base64 import b64encode
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    BASE_SITE: str
    ADMIN_ID: int = 0
    HCAPTCHA_SITE_KEY: str = ""
    HCAPTCHA_SECRET: str = ""
    TG_SECRET: str = b64encode(str(uuid.uuid4()).encode()).decode()
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    )

    def get_webhook_url(self) -> str:
        return f"{self.BASE_SITE}/webhook"


settings = Settings()
