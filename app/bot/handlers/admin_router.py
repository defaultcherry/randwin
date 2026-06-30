import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.api.dao import GiveawayDAO
from app.api.models import GiveawayStatus
from app.bot.create_bot import bot
from app.bot.keyboards.kbs import button_color_keyboard, captcha_requirement_keyboard, channel_request_keyboard, confirm_giveaway_keyboard, main_keyboard
from app.config import settings
from app.services.giveaways import ensure_user, now_utc, normalize_datetime, publish_due_giveaways, to_db_utc

admin_router = Router()
MSK_TZ = ZoneInfo("Europe/Moscow")


class GiveawayCreation(StatesGroup):
    choose_channel = State()
    announcement_message = State()
    button_color = State()
    prize_places = State()
    starts_at = State()
    duration = State()
    captcha_requirement = State()


RELATIVE_TIME_HINT = "2:30 или 1d 02:30"
RELATIVE_TIME_RE = re.compile(r"^(?:(?P<days>\d+)\s*(?:d|д))?\s*(?P<hours>\d{1,3}):(?P<minutes>\d{2})(?::(?P<seconds>\d{2}))?$")


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace(" ", "T")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MSK_TZ)
    else:
        parsed = parsed.astimezone(MSK_TZ)
    return parsed.astimezone(timezone.utc)


def _format_msk(value: datetime) -> str:
    return normalize_datetime(value).astimezone(MSK_TZ).strftime("%Y-%m-%d %H:%M MSK")


def _parse_relative_duration(value: str) -> timedelta:
    text = value.strip().lower().replace("час", "h")
    match = RELATIVE_TIME_RE.match(text)
    if not match:
        raise ValueError("invalid duration")

    days = int(match.group("days") or 0)
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds") or 0)
    if minutes >= 60 or seconds >= 60:
        raise ValueError("invalid duration")
    duration = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    if duration <= timedelta(0):
        raise ValueError("invalid duration")
    return duration


def _resolve_schedule(starts_at: datetime, duration: timedelta, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or now_utc()
    actual_start = max(starts_at, current)
    actual_end = actual_start + duration
    return actual_start, actual_end


def _format_preview(data: dict) -> str:
    channel_link = data.get("channel_username")
    channel_display = f"@{channel_link}" if channel_link else data["channel_title"]
    return (
        "<b>Проверьте данные розыгрыша</b>\n\n"
        f"<b>Канал:</b> {channel_display}\n"
        f"<b>Сообщение:</b> {data['announcement_message']}\n"
        f"<b>Цвет кнопки:</b> {data['button_color']}\n"
        f"<b>Призовых мест:</b> {data['prize_places']}\n"
        f"<b>hCaptcha:</b> {'включена' if data['require_captcha'] else 'отключена'}\n"
        f"<b>Начало:</b> {_format_msk(data['starts_at'])}\n"
        f"<b>Длительность:</b> {data['duration']}\n"
        "<b>Завершение:</b> будет рассчитано при подтверждении"
    )


async def _validate_channel_access(channel_id: int, user_id: int) -> tuple[bool, str | None, str | None]:
    try:
        channel = await bot.get_chat(channel_id)
        if channel.type != "channel":
            return False, None, None

        bot_member = await bot.get_chat_member(channel_id, (await bot.get_me()).id)
        user_member = await bot.get_chat_member(channel_id, user_id)
    except Exception:
        return False, None, None

    allowed = {"administrator", "creator"}
    if bot_member.status not in allowed:
        return False, channel.title, channel.username
    if user_member.status not in allowed:
        return False, channel.title, channel.username
    return True, channel.title, channel.username


@admin_router.message(Command("giveaway"), F.from_user.id == settings.ADMIN_ID)
@admin_router.message(F.text == "🎁 Создать розыгрыш", F.from_user.id == settings.ADMIN_ID)
async def start_creation(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(GiveawayCreation.choose_channel)
    await message.answer(
        "Сначала выберите канал, в котором бот уже добавлен администратором.\n"
        "После выбора я проверю ваши права в этом канале.",
        reply_markup=channel_request_keyboard(),
    )


@admin_router.message(GiveawayCreation.choose_channel, F.chat_shared, F.from_user.id == settings.ADMIN_ID)
async def set_channel(message: Message, state: FSMContext) -> None:
    shared = message.chat_shared
    if shared is None or shared.request_id != 1:
        await message.answer("Не удалось получить выбранный канал. Попробуйте ещё раз.")
        return

    ok, title, username = await _validate_channel_access(shared.chat_id, message.from_user.id)
    if not ok:
        await message.answer(
            "У вас или у бота нет прав администратора в этом канале.\n"
            "Добавьте бота и попробуйте выбрать канал снова.",
            reply_markup=channel_request_keyboard(),
        )
        return

    await state.update_data(
        channel_id=str(shared.chat_id),
        channel_title=title or "Канал",
        channel_username=username,
    )
    await state.set_state(GiveawayCreation.announcement_message)
    await message.answer(
        f"Канал выбран: <b>{title or 'Канал'}</b>.\n"
        "Теперь отправьте текст сообщения розыгрыша.",
        reply_markup=main_keyboard(is_admin=True),
    )


@admin_router.message(GiveawayCreation.announcement_message, F.from_user.id == settings.ADMIN_ID)
async def set_message(message: Message, state: FSMContext) -> None:
    await state.update_data(announcement_message=message.text.strip())
    await state.set_state(GiveawayCreation.button_color)
    await message.answer(
        "Выберите цвет кнопки из доступных вариантов.",
        reply_markup=button_color_keyboard(),
    )


@admin_router.callback_query(GiveawayCreation.button_color, F.data.startswith("giveaway:color:"))
async def set_color(callback: CallbackQuery, state: FSMContext) -> None:
    color = callback.data.removeprefix("giveaway:color:")
    await state.update_data(button_color=color)
    await state.set_state(GiveawayCreation.captcha_requirement)
    await callback.message.edit_text(f"Цвет кнопки выбран: <code>{color}</code>")
    await callback.message.answer("Требовать прохождение hCaptcha?", reply_markup=captcha_requirement_keyboard())
    await callback.answer()


@admin_router.message(GiveawayCreation.button_color, F.from_user.id == settings.ADMIN_ID)
async def set_color_fallback(message: Message) -> None:
    await message.answer("Выберите цвет кнопки через предложенные варианты ниже.", reply_markup=button_color_keyboard())


@admin_router.callback_query(GiveawayCreation.captcha_requirement, F.data.startswith("giveaway:captcha:"))
async def set_captcha_requirement(callback: CallbackQuery, state: FSMContext) -> None:
    require_captcha = callback.data.endswith(":yes")
    await state.update_data(require_captcha=require_captcha)
    await state.set_state(GiveawayCreation.prize_places)
    await callback.message.edit_text(
        f"hCaptcha {'включена' if require_captcha else 'отключена'}."
    )
    await callback.message.answer("Сколько призовых мест будет в розыгрыше?")
    await callback.answer()


@admin_router.message(GiveawayCreation.captcha_requirement, F.from_user.id == settings.ADMIN_ID)
async def set_captcha_requirement_fallback(message: Message) -> None:
    await message.answer("Выберите вариант кнопками ниже.", reply_markup=captcha_requirement_keyboard())


@admin_router.message(GiveawayCreation.prize_places, F.from_user.id == settings.ADMIN_ID)
async def set_places(message: Message, state: FSMContext) -> None:
    try:
        places = int(message.text.strip())
        if places < 1:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число больше 0.")
        return

    await state.update_data(prize_places=places)
    await state.set_state(GiveawayCreation.starts_at)
    await message.answer(
        "Введите время начала в формате `YYYY-MM-DD HH:MM`.\n"
        "Время указывайте по МСК. Например: `2026-07-01 18:30`.",
    )


@admin_router.message(GiveawayCreation.starts_at, F.from_user.id == settings.ADMIN_ID)
async def set_starts_at(message: Message, state: FSMContext) -> None:
    try:
        starts_at = _parse_datetime(message.text)
    except ValueError:
        await message.answer("Не удалось распознать дату. Пример: `2026-07-01 18:30`.")
        return

    await state.update_data(starts_at=starts_at)
    await state.set_state(GiveawayCreation.duration)
    await message.answer(
        f"Теперь введите длительность розыгрыша относительно начала в формате `{RELATIVE_TIME_HINT}`.\n"
        "Например: `2:30` или `1d 02:30`."
    )


@admin_router.message(GiveawayCreation.duration, F.from_user.id == settings.ADMIN_ID)
async def set_duration(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    starts_at = data["starts_at"]

    try:
        duration = _parse_relative_duration(message.text)
    except ValueError:
        await message.answer(
            f"Не удалось распознать длительность. Используйте формат `{RELATIVE_TIME_HINT}`.",
        )
        return

    await state.update_data(duration=duration)
    preview = await state.get_data()
    await message.answer(_format_preview(preview), reply_markup=confirm_giveaway_keyboard())


@admin_router.callback_query(F.data == "giveaway:cancel")
async def cancel_creation(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("Создание розыгрыша отменено.")
    await callback.answer()


@admin_router.callback_query(F.data == "giveaway:confirm")
async def confirm_creation(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("Недостаточно прав", show_alert=True)
        return

    data = await state.get_data()
    title = data["announcement_message"].splitlines()[0][:120]
    actual_start, actual_end = _resolve_schedule(data["starts_at"], data["duration"])
    actual_start_db = to_db_utc(actual_start)
    actual_end_db = to_db_utc(actual_end)

    await ensure_user(
        callback.from_user.id,
        callback.from_user.first_name,
        callback.from_user.full_name,
        callback.from_user.username,
    )

    await GiveawayDAO.add(
        creator_telegram_id=callback.from_user.id,
        channel_id=data["channel_id"],
        channel_title=data.get("channel_title"),
        channel_username=data.get("channel_username"),
        title=title,
        announcement_message=data["announcement_message"],
        button_color=data["button_color"],
        require_captcha=data.get("require_captcha", True),
        prize_places=data["prize_places"],
        starts_at=actual_start_db,
        ends_at=actual_end_db,
        status=GiveawayStatus.SCHEDULED,
    )
    if actual_start_db <= to_db_utc(now_utc()):
        await publish_due_giveaways(bot)
    await state.clear()
    await callback.message.edit_text(
        "Розыгрыш сохранён и будет опубликован автоматически в указанное время.",
    )
    await callback.answer("Готово")


@admin_router.callback_query(F.data == "home:show")
async def show_home(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Возвращаюсь в главное меню.",
        reply_markup=main_keyboard(is_admin=callback.from_user.id == settings.ADMIN_ID),
    )
    await callback.answer()
