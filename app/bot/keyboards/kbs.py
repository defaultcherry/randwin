from aiogram.types import ChatAdministratorRights, InlineKeyboardMarkup, KeyboardButtonRequestChat, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.config import settings


def main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if is_admin:
        builder.button(text="🎁 Создать розыгрыш")
    builder.button(text="ℹ️ Помощь")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Создать розыгрыш", callback_data="giveaway:create")
    builder.button(text="🏠 На главную", callback_data="home:show")
    builder.adjust(1)
    return builder.as_markup()


def confirm_giveaway_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="giveaway:confirm")
    builder.button(text="✏️ Отменить", callback_data="giveaway:cancel")
    builder.adjust(2)
    return builder.as_markup()


def button_color_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    colors = [
        ("🔵 Primary", "primary"),
        ("🟢 Success", "success"),
        ("🔴 Danger", "danger"),
        ("⚪ Default", "default"),
    ]

    for label, color in colors:
        builder.button(text=label, callback_data=f"giveaway:color:{color}")

    builder.adjust(2)
    return builder.as_markup()


def channel_request_keyboard(request_id: int = 1) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(
        text="Выбрать канал",
        request_chat=KeyboardButtonRequestChat(
            request_id=request_id,
            chat_is_channel=True,
            chat_is_forum=None,
            chat_has_username=None,
            chat_is_created=None,
            user_administrator_rights=ChatAdministratorRights(
                is_anonymous=False,
                can_manage_chat=True,
                can_delete_messages=True,
                can_manage_video_chats=False,
                can_restrict_members=False,
                can_promote_members=False,
                can_change_info=True,
                can_invite_users=True,
                can_post_stories=False,
                can_edit_stories=False,
                can_delete_stories=False,
                can_post_messages=True,
                can_edit_messages=True,
                can_pin_messages=False,
                can_manage_topics=False,
                can_manage_direct_messages=False,
                can_manage_tags=False,
            ),
            bot_administrator_rights=ChatAdministratorRights(
                is_anonymous=False,
                can_manage_chat=True,
                can_delete_messages=True,
                can_manage_video_chats=False,
                can_restrict_members=False,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=True,
                can_post_stories=False,
                can_edit_stories=False,
                can_delete_stories=False,
                can_post_messages=True,
                can_edit_messages=True,
                can_pin_messages=False,
                can_manage_topics=False,
                can_manage_direct_messages=False,
                can_manage_tags=False,
            ),
            bot_is_member=True,
            request_title=True,
            request_username=None,
            request_photo=False,
        ),
    )
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def channel_post_keyboard(giveaway_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Участвовать", web_app=WebAppInfo(url=f"{settings.BASE_SITE.rstrip('/')}/giveaways/{giveaway_id}"))
    return builder.as_markup()
