from app.api.models import Giveaway, TelegramUser
from app.dao.base import BaseDAO


class UserDAO(BaseDAO):
    model = TelegramUser


class GiveawayDAO(BaseDAO):
    model = Giveaway
