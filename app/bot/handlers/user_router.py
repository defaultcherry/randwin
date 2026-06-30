from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.keyboards.kbs import main_keyboard
from app.config import settings
from app.services.giveaways import ensure_user

user_router = Router()


@user_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await ensure_user(
        message.from_user.id,
        message.from_user.first_name,
        message.from_user.full_name,
        message.from_user.username,
    )
    is_admin = message.from_user.id == settings.ADMIN_ID
    text = (
        f"Здравствуйте, <b>{message.from_user.full_name}</b>!\n\n"
        "Это бот для создания и публикации розыгрышей.\n"
        "Администратор может запускать мастер создания розыгрыша прямо в личном чате."
    )
    await message.answer(text, reply_markup=main_keyboard(is_admin=is_admin))


@user_router.message(F.text == "ℹ️ Помощь")
async def help_message(message: Message) -> None:
    await message.answer(
        "Откройте розыгрыш по кнопке в сообщении канала.\n"
        "Для участия потребуется пройти hCaptcha и подтвердить подписку на канал.",
        reply_markup=main_keyboard(is_admin=message.from_user.id == settings.ADMIN_ID),
    )
