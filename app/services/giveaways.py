import logging
import random
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.models import Giveaway, GiveawayStatus, TelegramUser
from app.database import async_session_maker
from app.config import settings

MSK_TZ = ZoneInfo("Europe/Moscow")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_db_utc(value: datetime) -> datetime:
    return normalize_datetime(value).replace(tzinfo=None)


async def ensure_user(
    telegram_id: int,
    first_name: str,
    full_name: str,
    username: str | None,
    photo_file_id: str | None = None,
) -> TelegramUser:
    async with async_session_maker() as session:
        user = await session.get(TelegramUser, telegram_id)
        if user:
            user.first_name = first_name
            user.full_name = full_name
            user.username = username
            if photo_file_id:
                user.photo_file_id = photo_file_id
        else:
            user = TelegramUser(
                telegram_id=telegram_id,
                first_name=first_name,
                full_name=full_name,
                username=username,
                photo_file_id=photo_file_id,
            )
            session.add(user)

        await session.commit()
        await session.refresh(user)
        return user


def user_display_name(user: TelegramUser) -> str:
    return (user.full_name or user.first_name or "Пользователь").strip() or "Пользователь"


def winner_mention(user: TelegramUser) -> str:
    name = escape(user_display_name(user))
    return f'<a href="tg://user?id={user.telegram_id}">{name}</a>'


async def build_user_avatar_url(bot: Bot, telegram_id: int) -> str | None:
    photos = await bot.get_user_profile_photos(telegram_id, limit=1)
    if not photos.photos:
        return None

    return f"/api/avatars/{telegram_id}"


async def build_winner_snapshot(bot: Bot, user: TelegramUser) -> dict:
    avatar_url = await build_user_avatar_url(bot, user.telegram_id)
    return {
        "telegram_id": user.telegram_id,
        "full_name": user_display_name(user),
        "username": user.username,
        "mention_html": winner_mention(user),
        "avatar_url": avatar_url,
    }


async def get_giveaway(giveaway_id: int) -> Giveaway | None:
    async with async_session_maker() as session:
        query = (
            select(Giveaway)
            .options(selectinload(Giveaway.participants), selectinload(Giveaway.creator))
            .where(Giveaway.id == giveaway_id)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()


def build_giveaway_url(giveaway_id: int) -> str:
    return f"{settings.BASE_SITE.rstrip('/')}/giveaways/{giveaway_id}"


def build_tg_launch_url(bot_username: str, giveaway_id: int) -> str:
    return f"https://t.me/{bot_username}?startapp=giveaway_{giveaway_id}"


def resolve_button_style(style: str | None) -> str | None:
    if style in {None, "", "default"}:
        return None
    if style in {"primary", "success", "danger"}:
        return style
    return None


def build_join_keyboard(
    giveaway_id: int,
    button_style: str | None = None,
    *,
    prefer_web_app: bool = True,
    launch_url: str | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    kwargs = {
        "text": "Участвовать",
        "style": resolve_button_style(button_style),
    }
    if prefer_web_app:
        kwargs["web_app"] = WebAppInfo(url=build_giveaway_url(giveaway_id))
    else:
        kwargs["url"] = launch_url or build_giveaway_url(giveaway_id)
    builder.button(**kwargs)
    return builder.as_markup()


def serialize_giveaway(giveaway: Giveaway) -> dict:
    participants_count = len(giveaway.participants)
    starts_at = normalize_datetime(giveaway.starts_at)
    ends_at = normalize_datetime(giveaway.ends_at)
    return {
        "id": giveaway.id,
        "title": giveaway.title,
        "announcement_message": giveaway.announcement_message,
        "button_color": giveaway.button_color,
        "require_captcha": giveaway.require_captcha,
        "prize_places": giveaway.prize_places,
        "channel_id": giveaway.channel_id,
        "channel_title": giveaway.channel_title,
        "channel_username": giveaway.channel_username,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "status": giveaway.status.value,
        "participants_count": participants_count,
        "winner_ids": giveaway.winner_ids,
        "winner_snapshots": giveaway.winner_snapshots or [],
    }


async def publish_due_giveaways(bot: Bot) -> None:
    current_time = to_db_utc(now_utc())
    bot_username = (await bot.get_me()).username
    async with async_session_maker() as session:
        query = (
            select(Giveaway)
            .options(selectinload(Giveaway.participants), selectinload(Giveaway.creator))
            .where(Giveaway.status == GiveawayStatus.SCHEDULED, Giveaway.starts_at <= current_time)
            .order_by(Giveaway.starts_at.asc())
        )
        result = await session.execute(query)
        giveaways = result.scalars().all()

        for giveaway in giveaways:
            try:
                message = await bot.send_message(
                    chat_id=giveaway.channel_id,
                    text=build_channel_post_text(giveaway),
                    reply_markup=build_join_keyboard(
                        giveaway.id,
                        giveaway.button_color,
                        prefer_web_app=True,
                        launch_url=build_tg_launch_url(bot_username, giveaway.id), # type: ignore
                    ),
                )
            except TelegramBadRequest:
                logging.warning("Channel web_app button failed for giveaway %s, retrying with URL button", giveaway.id)
                try:
                    message = await bot.send_message(
                        chat_id=giveaway.channel_id,
                        text=build_channel_post_text(giveaway),
                        reply_markup=build_join_keyboard(
                            giveaway.id,
                            giveaway.button_color,
                            prefer_web_app=False,
                            launch_url=build_tg_launch_url(bot_username, giveaway.id), # type: ignore
                        ),
                    )
                except Exception:
                    logging.exception("Failed to publish giveaway %s", giveaway.id)
                    continue
            except Exception:
                logging.exception("Failed to publish giveaway %s", giveaway.id)
                continue

            giveaway.status = GiveawayStatus.ACTIVE
            giveaway.published_at = current_time
            giveaway.message_id = message.message_id

        await session.commit()


async def refresh_active_giveaways(bot: Bot) -> None:
    current_time = to_db_utc(now_utc())
    bot_username = (await bot.get_me()).username
    async with async_session_maker() as session:
        query = (
            select(Giveaway)
            .options(selectinload(Giveaway.participants), selectinload(Giveaway.creator))
            .where(Giveaway.status == GiveawayStatus.ACTIVE, Giveaway.message_id.isnot(None), Giveaway.ends_at > current_time)
            .order_by(Giveaway.starts_at.asc())
        )
        result = await session.execute(query)
        giveaways = result.scalars().all()

        for giveaway in giveaways:
            try:
                await bot.edit_message_text(
                    chat_id=giveaway.channel_id,
                    message_id=giveaway.message_id,
                    text=build_channel_post_text(giveaway),
                    reply_markup=build_join_keyboard(
                        giveaway.id,
                        giveaway.button_color,
                        prefer_web_app=True,
                        launch_url=build_tg_launch_url(bot_username, giveaway.id), # type: ignore
                    ),
                )
            except TelegramBadRequest:
                try:
                    await bot.edit_message_text(
                        chat_id=giveaway.channel_id,
                        message_id=giveaway.message_id,
                        text=build_channel_post_text(giveaway),
                        reply_markup=build_join_keyboard(
                            giveaway.id,
                            giveaway.button_color,
                            prefer_web_app=False,
                            launch_url=build_tg_launch_url(bot_username, giveaway.id), # type: ignore
                        ),
                    )
                except Exception:
                    logging.exception("Failed to refresh active giveaway %s", giveaway.id)
            except Exception:
                logging.exception("Failed to refresh active giveaway %s", giveaway.id)

        await session.commit()


async def finish_due_giveaways(bot: Bot) -> None:
    current_time = to_db_utc(now_utc())
    bot_username = (await bot.get_me()).username
    async with async_session_maker() as session:
        query = (
            select(Giveaway)
            .options(selectinload(Giveaway.participants), selectinload(Giveaway.creator))
            .where(Giveaway.status == GiveawayStatus.ACTIVE, Giveaway.ends_at <= current_time)
            .order_by(Giveaway.ends_at.asc())
        )
        result = await session.execute(query)
        giveaways = result.scalars().all()

        for giveaway in giveaways:
            participants = list(giveaway.participants)
            winners = random.sample(participants, k=min(giveaway.prize_places, len(participants)))
            winner_ids = [user.telegram_id for user in winners] # TODO: recheck sub status
            winner_snapshots = [await build_winner_snapshot(bot, user) for user in winners]
            giveaway.winner_ids = winner_ids
            giveaway.winner_snapshots = winner_snapshots
            giveaway.status = GiveawayStatus.FINISHED
            giveaway.finished_at = current_time

            try:
                await bot.edit_message_text(
                    chat_id=giveaway.channel_id,
                    message_id=giveaway.message_id,
                    text=build_finished_channel_post_text(giveaway, winner_snapshots),
                    reply_markup=build_results_keyboard(
                        giveaway.id,
                        giveaway.button_color,
                        prefer_web_app=True,
                        launch_url=build_tg_launch_url(bot_username, giveaway.id), # type: ignore
                    ),
                )
            except TelegramBadRequest:
                try:
                    await bot.send_message(
                        chat_id=giveaway.channel_id,
                        text=build_finished_channel_post_text(giveaway, winner_snapshots),
                        reply_markup=build_results_keyboard(
                            giveaway.id,
                            giveaway.button_color,
                            prefer_web_app=False,
                            launch_url=build_tg_launch_url(bot_username, giveaway.id), # type: ignore
                        ),
                    )
                except Exception:
                    logging.exception("Failed to send finished giveaway fallback for %s", giveaway.id)
            except Exception:
                logging.exception("Failed to finish giveaway %s", giveaway.id)
                try:
                    await bot.send_message(
                        chat_id=giveaway.channel_id,
                        text=build_finished_channel_post_text(giveaway, winner_snapshots),
                        reply_markup=build_results_keyboard(
                            giveaway.id,
                            giveaway.button_color,
                            prefer_web_app=False,
                            launch_url=build_tg_launch_url(bot_username, giveaway.id), # type: ignore
                        ),
                    )
                except Exception:
                    logging.exception("Failed to send finished giveaway fallback for %s", giveaway.id)

        await session.commit()


def build_channel_post_text(giveaway: Giveaway) -> str:
    return (
        f"{giveaway.announcement_message}\n\n"
        f"🏆 Призовых мест: <b>{giveaway.prize_places}</b>\n"
        f"👥 Участников: <b>{len(giveaway.participants)}</b>\n"
        f"⏳ Завершение: <b>{normalize_datetime(giveaway.ends_at).astimezone(MSK_TZ).strftime('%Y-%m-%d %H:%M MSK')}</b>\n\n"
        "Нажмите кнопку ниже, чтобы принять участие в розыгрыше."
    )


def build_results_keyboard(
    giveaway_id: int,
    button_style: str | None = None,
    *,
    prefer_web_app: bool = True,
    launch_url: str | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    kwargs = {
        "text": "Результаты",
        "style": resolve_button_style(button_style),
    }
    if prefer_web_app:
        kwargs["web_app"] = WebAppInfo(url=build_giveaway_url(giveaway_id))
    else:
        kwargs["url"] = launch_url or build_giveaway_url(giveaway_id)
    builder.button(**kwargs)
    return builder.as_markup()


def build_finished_channel_post_text(giveaway: Giveaway, winner_snapshots: list[dict]) -> str:
    if not winner_snapshots:
        winners = "Победители не определены: нет участников."
    else:
        winners = "\n".join(f"• {winner['mention_html']}" for winner in winner_snapshots)

    return (
        f"🏁 <b>Розыгрыш завершён:</b> {escape(giveaway.title)}\n\n"
        f"{winners}\n\n"
        f"Всего участников: <b>{len(giveaway.participants)}</b>"
    )


async def join_giveaway(*, giveaway_id: int, telegram_user_id: int) -> tuple[str, Giveaway]:
    async with async_session_maker() as session:
        query = (
            select(Giveaway)
            .options(selectinload(Giveaway.participants))
            .where(Giveaway.id == giveaway_id)
        )
        result = await session.execute(query)
        giveaway = result.scalar_one_or_none()
        if giveaway is None:
            raise ValueError("Giveaway not found")

        if telegram_user_id in {participant.telegram_id for participant in giveaway.participants}:
            return "already_joined", giveaway

        if giveaway.status != GiveawayStatus.ACTIVE:
            return "not_active", giveaway

        user = await session.get(TelegramUser, telegram_user_id)
        if user is None:
            raise ValueError("Telegram user not found")

        giveaway.participants.append(user)
        await session.commit()
        await session.refresh(giveaway)
        return "joined", giveaway


async def refresh_giveaway_message(bot: Bot, giveaway_id: int) -> None:
    giveaway = await get_giveaway(giveaway_id)
    if giveaway is None or giveaway.status != GiveawayStatus.ACTIVE or giveaway.message_id is None:
        return

    bot_username = (await bot.get_me()).username
    try:
        await bot.edit_message_text(
            chat_id=giveaway.channel_id,
            message_id=giveaway.message_id,
            text=build_channel_post_text(giveaway),
            reply_markup=build_join_keyboard(
                giveaway.id,
                giveaway.button_color,
                prefer_web_app=True,
                launch_url=build_tg_launch_url(bot_username, giveaway.id), # type: ignore
            ),
        )
    except TelegramBadRequest:
        try:
            await bot.edit_message_text(
                chat_id=giveaway.channel_id,
                message_id=giveaway.message_id,
                text=build_channel_post_text(giveaway),
                reply_markup=build_join_keyboard(
                    giveaway.id,
                    giveaway.button_color,
                    prefer_web_app=False,
                    launch_url=build_tg_launch_url(bot_username, giveaway.id), # type: ignore
                ),
            )
        except Exception:
            logging.exception("Failed to refresh giveaway %s after join", giveaway.id)
    except Exception:
        logging.exception("Failed to refresh giveaway %s after join", giveaway.id)


async def get_view_state(giveaway_id: int, telegram_id: int | None) -> dict:
    giveaway = await get_giveaway(giveaway_id)
    if giveaway is None:
        raise ValueError("Giveaway not found")

    viewer_state = "guest"
    subscription_status = None
    viewer_name = None

    if telegram_id is not None:
        async with async_session_maker() as session:
            query = select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
            result = await session.execute(query)
            user = result.scalar_one_or_none()
            if user:
                viewer_name = user_display_name(user)
                if telegram_id in {participant.telegram_id for participant in giveaway.participants}:
                    viewer_state = "already_joined"

    return {
        "giveaway": serialize_giveaway(giveaway),
        "viewer_state": viewer_state,
        "viewer_telegram_id": telegram_id,
        "viewer_name": viewer_name,
        "subscription_status": subscription_status,
    }
