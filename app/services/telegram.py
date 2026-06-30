import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request, urlopen

from app.config import settings


class TelegramDataError(ValueError):
    pass


@dataclass(slots=True)
class TelegramIdentity:
    telegram_id: int
    first_name: str
    username: str | None


def verify_telegram_init_data(init_data: str, *, max_age_seconds: int = 86400) -> TelegramIdentity:
    if not init_data:
        raise TelegramDataError("Missing Telegram init data")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    auth_date = parsed.get("auth_date")
    user_raw = parsed.get("user")

    if not received_hash or not auth_date or not user_raw:
        raise TelegramDataError("Invalid Telegram init data payload")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramDataError("Telegram data signature mismatch")

    try:
        auth_timestamp = int(auth_date)
    except ValueError as exc:
        raise TelegramDataError("Invalid auth date") from exc

    if time.time() - auth_timestamp > max_age_seconds:
        raise TelegramDataError("Telegram data expired")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise TelegramDataError("Invalid Telegram user payload") from exc

    return TelegramIdentity(
        telegram_id=int(user["id"]),
        first_name=str(user.get("first_name") or "Пользователь"),
        username=user.get("username"),
    )


async def verify_hcaptcha(token: str, remoteip: str | None = None) -> bool:
    if not settings.HCAPTCHA_SECRET:
        return True

    if not token:
        return False

    payload = {
        "secret": settings.HCAPTCHA_SECRET,
        "response": token,
    }
    if remoteip:
        payload["remoteip"] = remoteip

    def _request() -> dict:
        request = Request(
            "https://hcaptcha.com/siteverify",
            data=urlencode(payload).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())

    data = await asyncio.to_thread(_request)
    return bool(data.get("success"))
