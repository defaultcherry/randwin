from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from urllib.request import urlopen

from app.api.models import GiveawayStatus
from app.api.schemas import GiveawayPublicResponse, GiveawayViewResponse, JoinGiveawayPayload
from app.config import settings
from app.services.giveaways import get_giveaway, get_view_state, join_giveaway, refresh_giveaway_message, serialize_giveaway
from app.services.giveaways import ensure_user
from app.services.telegram import TelegramDataError, verify_hcaptcha, verify_telegram_init_data
from app.bot.create_bot import bot

router = APIRouter(prefix="/api", tags=["API"])


@router.get("/giveaways/{giveaway_id}", response_class=JSONResponse)
async def read_giveaway(
    giveaway_id: int,
    telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
):
    try:
        identity = verify_telegram_init_data(telegram_init_data)
    except TelegramDataError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        view_state = await get_view_state(giveaway_id, identity.telegram_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Giveaway not found") from exc
    giveaway = view_state["giveaway"]

    if giveaway["status"] == GiveawayStatus.FINISHED.value:
        viewer_state = "finished"
    elif giveaway["status"] == GiveawayStatus.ACTIVE.value:
        viewer_state = "already_joined" if view_state["viewer_state"] == "already_joined" else "can_join"
    elif giveaway["status"] == GiveawayStatus.SCHEDULED.value:
        viewer_state = "scheduled"
    else:
        viewer_state = view_state["viewer_state"]

    return GiveawayViewResponse(
        giveaway=GiveawayPublicResponse(**giveaway),
        viewer_state=viewer_state,
        viewer_telegram_id=identity.telegram_id,
        viewer_name=identity.first_name,
        subscription_status="unknown",
    ).model_dump()


@router.post("/giveaways/{giveaway_id}/join", response_class=JSONResponse)
async def participate(
    giveaway_id: int,
    payload: JoinGiveawayPayload,
    request: Request,
):
    try:
        identity = verify_telegram_init_data(payload.init_data)
    except TelegramDataError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    giveaway = await get_giveaway(giveaway_id)
    if giveaway is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Giveaway not found")

    if giveaway.require_captcha:
        if not payload.hcaptcha_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Captcha token is required")
        if not await verify_hcaptcha(payload.hcaptcha_token, request.client.host if request.client else None):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Captcha verification failed")

    user = await ensure_user(identity.telegram_id, identity.first_name, identity.first_name, identity.username)

    if giveaway.status == GiveawayStatus.FINISHED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Розыгрыш уже завершён")

    chat_member = await bot.get_chat_member(giveaway.channel_id, identity.telegram_id)
    if chat_member.status not in {"member", "administrator", "creator"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы должны быть подписаны на канал")

    state, updated = await join_giveaway(giveaway_id=giveaway_id, telegram_user_id=user.telegram_id)
    await refresh_giveaway_message(bot, giveaway_id)
    return {
        "state": state,
        "giveaway": serialize_giveaway(updated),
        "subscription_status": chat_member.status,
    }


@router.get("/giveaways/{giveaway_id}/results", response_class=JSONResponse)
async def giveaway_results(giveaway_id: int, telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data")):
    try:
        verify_telegram_init_data(telegram_init_data)
    except TelegramDataError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    giveaway = await get_giveaway(giveaway_id)
    if giveaway is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Giveaway not found")

    return {
        "id": giveaway.id,
        "title": giveaway.title,
        "status": giveaway.status.value,
        "winner_ids": giveaway.winner_ids or [],
        "winner_snapshots": giveaway.winner_snapshots or [],
        "participants_count": len(giveaway.participants),
        "prize_places": giveaway.prize_places,
        "ends_at": giveaway.ends_at.isoformat(),
    }


@router.get("/avatars/{telegram_id}")
async def avatar_proxy(telegram_id: int):
    photos = await bot.get_user_profile_photos(telegram_id, limit=1)
    if not photos.photos:
        return Response(status_code=204)

    file_id = photos.photos[0][-1].file_id
    file_info = await bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_info.file_path}"

    def file_stream():
        with urlopen(file_url, timeout=10) as response:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    media_type = "image/jpeg"
    if file_info.file_path.lower().endswith(".png"): # type: ignore
        media_type = "image/png"
    elif file_info.file_path.lower().endswith(".webp"): # type: ignore
        media_type = "image/webp"

    return StreamingResponse(file_stream(), media_type=media_type)
