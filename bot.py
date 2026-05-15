"""
Telegram Education Bot — selling video courses.

Everything is editable through the admin panel:
- Categories (main sections like "Видеоматериалы", etc.)
- Products within categories
- Welcome message / bot description
- Payment card details, Stars rate, payment providers
- Support contacts
- One-time invite links
"""

import asyncio
import csv
import hashlib
import json
import logging
import math
import os
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, deque
from html import escape, unescape
from urllib.parse import unquote, urljoin, urlparse

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    FSInputFile,
    KeyboardButton,
    KeyboardButtonRequestChat,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

try:
    from aiogram.types import KeyboardButtonRequestUsers
except ImportError:
    KeyboardButtonRequestUsers = None

try:
    from aiogram.types import ChatAdministratorRights
except ImportError:
    ChatAdministratorRights = None

try:
    from aiogram.types import KeyboardButtonRequestUser
except ImportError:
    KeyboardButtonRequestUser = None

import config
import database as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ─── Dynamic settings helpers ────────────────────────────────────────────────

async def S(key: str, default: str = "") -> str:
    return await db.get_setting(key, default)


async def get_stars_rate() -> float:
    try:
        return float(await S("stars_rate", "1.85"))
    except ValueError:
        return 1.85


async def get_usd_rate() -> float:
    try:
        return float(await S("usd_rate", "90"))
    except ValueError:
        return 90.0


async def get_int_setting(key: str, default: int) -> int:
    try:
        return int(float(await S(key, str(default))))
    except (TypeError, ValueError):
        return default


async def get_support_contacts() -> list[dict]:
    try:
        return json.loads(await S("support_contacts", "[]"))
    except (json.JSONDecodeError, TypeError):
        return []


async def get_crypto_client():
    token = await S("cryptobot_token")
    if token:
        try:
            from aiocryptopay import AioCryptoPay, Networks
            return AioCryptoPay(token=token, network=Networks.MAIN_NET)
        except ImportError as e:
            logger.warning("aiocryptopay not installed")
            await db.log_error("payment", str(e), context="CryptoBot import")
    return None


# ─── FSM States ──────────────────────────────────────────────────────────────

class AddProduct(StatesGroup):
    category = State()
    name = State()
    description = State()
    price = State()
    channel_id = State()
    channel_link = State()


class EditProduct(StatesGroup):
    choose_field = State()
    new_value = State()


class EditSetting(StatesGroup):
    waiting_value = State()


class AddContact(StatesGroup):
    name = State()
    username = State()


class GetID(StatesGroup):
    waiting_forward = State()


class AddCategory(StatesGroup):
    emoji = State()
    name = State()
    description = State()


class EditCategory(StatesGroup):
    new_value = State()


class SupportRequest(StatesGroup):
    waiting_message = State()


class AdminSearch(StatesGroup):
    waiting_query = State()


class AdminMessage(StatesGroup):
    waiting_text = State()



class ReviewFlow(StatesGroup):
    waiting_text = State()


class AICompose(StatesGroup):
    waiting_prompt = State()


class AIProductDesc(StatesGroup):
    waiting_product_info = State()


class AIBroadcast(StatesGroup):
    waiting_topic = State()


class AIReply(StatesGroup):
    waiting_context = State()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def rub_to_stars(rub: int, rate: float = 1.85) -> int:
    return max(1, math.ceil(rub / rate))


def html(value) -> str:
    return escape(str(value or "—"), quote=False)


async def is_admin(user_id: int, username: str | None = None) -> bool:
    if config.ADMIN_ID is not None and user_id == config.ADMIN_ID:
        return True
    result = await db.is_admin_in_db(user_id)
    if result and username is not None:
        await db.update_admin_username(user_id, username)
    return result


MESSAGE_BUCKETS = defaultdict(deque)
PAYMENT_BUTTON_PREFIXES = ("pay_", "paid_manual_", "check_crypto_", "access_again_", "remind_pay_")


# ─── AI Helper ───────────────────────────────────────────────────────────────

async def ai_generate(system_prompt: str, user_prompt: str) -> str:
    """Call OpenAI-compatible API (set openai_api_key and optionally openai_base_url in settings)."""
    api_key = await S("openai_api_key")
    if not api_key:
        return "⚠️ API-ключ не настроен. Установите openai_api_key в настройках бота."
    base_url = (await S("openai_base_url", "https://api.openai.com/v1")).rstrip("/")
    model = await S("openai_model", "gpt-4o-mini")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.7,
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    return f"⚠️ Ошибка API: {data['error'].get('message', str(data['error']))}"
                return data["choices"][0]["message"]["content"]
    except ImportError:
        return "⚠️ Библиотека aiohttp не установлена."
    except Exception as e:
        await db.log_error("ai_generate", str(e), context="openai_call")
        return f"⚠️ Ошибка: {e}"


def admin_display_name(user) -> str:
    name = getattr(user, "full_name", None) or "Админ"
    username = getattr(user, "username", None)
    return f"{name} (@{username})" if username else name


async def log_admin_event(user, action: str, details: str = ""):
    try:
        await db.log_admin_action(user.id, admin_display_name(user), action, details)
    except Exception as e:
        logger.warning(f"Admin log error: {e}")


def callback_action_text(data: str) -> tuple[str, str]:
    labels = {
        "adm_settings": "Открыл настройки бота",
        "adm_security": "Открыл антиспам и защиту",
        "adm_errors": "Открыл логи ошибок",
        "adm_admin_logs": "Открыл логи админов",
        "adm_categories": "Открыл категории",
        "adm_products": "Открыл товары",
        "adm_pending": "Открыл ожидающие заказы",
        "adm_all_orders": "Открыл все заказы",
        "adm_users": "Открыл пользователей",
        "adm_search": "Открыл поиск",
        "adm_admins": "Открыл список админов",
        "adm_get_id": "Открыл поиск ID",
        "adm_backups": "Открыл резервные копии",
        "adm_reviews": "Открыл отзывы",
        "adm_ai": "Открыл AI-помощник",
        "ai_broadcast": "Запустил AI-составитель рассылки",
        "ai_product_desc": "Запустил AI-генератор описания товара",
        "ai_reply": "Запустил AI-составитель ответа",
        "ai_sales_analysis": "Запустил AI-анализ продаж",
        "ai_user_summary_start": "Запустил AI-сводку по пользователю",
        "ai_promo_ideas": "Запустил AI-идеи для продвижения",
        "sec_toggle_reissue": "Изменил включение повторной выдачи доступа",
        "sec_banned": "Открыл черный список",
    }
    if data in labels:
        return labels[data], data
    prefixes = (
        ("set_edit_", "Открыл изменение настройки"),
        ("prod_add", "Добавление товара"),
        ("prod_set_", "Открыл изменение товара"),
        ("prod_toggle_", "Переключил видимость товара"),
        ("prod_del", "Удаление товара"),
        ("cat_add", "Добавление категории"),
        ("catset_", "Открыл изменение категории"),
        ("cattoggle_", "Переключил видимость категории"),
        ("catdel", "Удаление категории"),
        ("confirm_", "Подтвердил заказ"),
        ("reject_", "Отклонил заказ"),
        ("adm_order_", "Открыл карточку заказа"),
        ("adm_orders_filter_", "Применил фильтр заказов"),
        ("adm_user_write_", "Открыл отправку сообщения пользователю"),
        ("adm_user_ban_", "Заблокировал пользователя из карточки"),
        ("adm_user_unban_", "Разблокировал пользователя из карточки"),
        ("adm_user_history_", "Открыл историю пользователя"),
        ("adm_user_", "Открыл карточку пользователя"),
        ("sec_unban_", "Разблокировал пользователя из панели"),
        ("err_clear_", "Очистил логи ошибок"),
        ("adm_log_clear", "Очистил логи админов"),
        ("autopub_", "Действие в автовыгрузке товара"),
        ("backup_", "Действие с резервными копиями"),
        ("review_", "Действие с отзывом"),
        ("remind_", "Действие с напоминанием заказа"),
        ("ai_user_summary_", "AI-сводка по пользователю"),
        ("adm_ai_user_", "AI-сводка из карточки"),
    )
    for prefix, label in prefixes:
        if data.startswith(prefix):
            return label, data
    return "Нажал кнопку админ-панели", data


class AdminActionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user") or getattr(event, "from_user", None)
        if user and await is_admin(user.id, getattr(user, "username", None)):
            action = "Действие админа"
            details = ""
            if isinstance(event, CallbackQuery):
                action, details = callback_action_text(event.data or "")
            elif isinstance(event, Message):
                text = event.text or ""
                state = data.get("state")
                state_name = await state.get_state() if state else None
                state_data = await state.get_data() if state else {}
                if text.startswith("/"):
                    action = f"Команда {text.split()[0]}"
                    details = "аргументы скрыты, чтобы не хранить лишние данные"
                elif state_name == EditSetting.waiting_value.state:
                    key = state_data.get("setting_key", "")
                    action = "Изменил настройку бота"
                    details = f"setting={key}; значение не сохраняется в логах"
                elif state_name:
                    action = "Ввод данных в админ-панели"
                    details = f"state={state_name}; текст не сохраняется в логах"
                else:
                    action = "Сообщение админа"
                    details = "текст не сохраняется в логах"
            await log_admin_event(user, action, details)
        return await handler(event, data)


class SecurityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user") or getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        # Admins bypass anti-spam limits and can always use /ban /unban.
        if await is_admin(user.id, getattr(user, "username", None)):
            return await handler(event, data)

        if await db.is_user_banned(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 Вы заблокированы.", show_alert=True)
            elif isinstance(event, Message) and event.chat.type == "private":
                await event.answer("🚫 Вы заблокированы. Обратитесь в поддержку.")
            return None

        if isinstance(event, Message) and event.chat.type == "private":
            limit = await get_int_setting("antispam_message_limit_per_minute", 12)
            if limit > 0:
                now = time.monotonic()
                bucket = MESSAGE_BUCKETS[user.id]
                while bucket and now - bucket[0] > 60:
                    bucket.popleft()
                if len(bucket) >= limit:
                    await event.answer(f"⏳ Антиспам: лимит {limit} сообщений в минуту. Попробуйте чуть позже.")
                    return None
                bucket.append(now)

        if isinstance(event, CallbackQuery) and event.data and event.data.startswith(PAYMENT_BUTTON_PREFIXES):
            cooldown = await get_int_setting("payment_button_cooldown_seconds", 8)
            if cooldown > 0:
                allowed, retry_after = await db.register_button_click(user.id, f"button:{event.data}", cooldown)
                if not allowed:
                    await event.answer(f"⏳ Подождите {retry_after} сек. перед повторным нажатием.", show_alert=True)
                    return None

        return await handler(event, data)


router.message.middleware(SecurityMiddleware())
router.callback_query.middleware(SecurityMiddleware())
router.message.middleware(AdminActionMiddleware())
router.callback_query.middleware(AdminActionMiddleware())


async def notify_admins(text: str, reply_markup=None):
    admin_ids = set()
    if config.ADMIN_ID:
        admin_ids.add(config.ADMIN_ID)
    for adm in await db.get_all_admins():
        admin_ids.add(adm["user_id"])
    for aid in admin_ids:
        try:
            await bot.send_message(aid, text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            await db.log_error("send_message", str(e), user_id=aid, context="notify_admins")


async def generate_invite_link(product: dict) -> str:
    channel_id = product.get("channel_id", "").strip()
    if channel_id:
        try:
            chat_id = int(channel_id) if channel_id.lstrip("-").isdigit() else channel_id
            link = await bot.create_chat_invite_link(chat_id=chat_id, member_limit=1, name=f"Order #{product['id']}")
            return link.invite_link
        except Exception as e:
            logger.error(f"Invite link error {channel_id}: {e}")
            await db.log_error("create_link", str(e), context=f"product_id={product.get('id')} channel_id={channel_id}")
    return product.get("channel_link", "") or "(ссылка не настроена)"


async def get_ticket_group_id() -> int:
    try:
        return int(await S("ticket_group_id", str(config.TICKET_GROUP_ID)))
    except ValueError:
        return config.TICKET_GROUP_ID


async def get_or_create_topic(user_id: int, user_name: str, username: str | None) -> int:
    topic_id = await db.get_topic_id(user_id)
    if topic_id:
        return topic_id
    group_id = await get_ticket_group_id()
    display = f"{user_name}"
    if username:
        display += f" (@{username})"
    display += f" [{user_id}]"
    try:
        topic = await bot.create_forum_topic(chat_id=group_id, name=display[:128])
        await db.save_topic_id(user_id, topic.message_thread_id)
        await bot.send_message(
            chat_id=group_id, message_thread_id=topic.message_thread_id,
            text=f"🆕 <b>Тикет</b>\n\n👤 {user_name}\n📱 @{username or '—'}\n🆔 <code>{user_id}</code>",
            parse_mode="HTML",
        )
        return topic.message_thread_id
    except Exception as e:
        logger.error(f"Topic error: {e}")
        await db.log_error("send_message", str(e), user_id=user_id, context="create_forum_topic")
        return 0


async def forward_to_group(user_id: int, user_name: str, username: str | None, text: str):
    topic_id = await get_or_create_topic(user_id, user_name, username)
    if not topic_id:
        return
    group_id = await get_ticket_group_id()
    try:
        await bot.send_message(chat_id=group_id, message_thread_id=topic_id, text=f"💬 <b>{user_name}:</b>\n{text}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Forward error: {e}")
        await db.log_error("send_message", str(e), user_id=user_id, context="forward_to_group")


async def forward_photo_to_group(user_id: int, user_name: str, username: str | None, photo_id: str, caption: str | None):
    topic_id = await get_or_create_topic(user_id, user_name, username)
    if not topic_id:
        return
    group_id = await get_ticket_group_id()
    try:
        cap = f"📷 <b>{user_name}:</b>\n{caption or ''}" if caption else f"📷 <b>{user_name}</b>"
        await bot.send_photo(chat_id=group_id, message_thread_id=topic_id, photo=photo_id, caption=cap, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Forward photo error: {e}")
        await db.log_error("send_message", str(e), user_id=user_id, context="forward_photo_to_group")


async def auto_confirm_order(order_id: int, payment_method: str):
    order = await db.get_order(order_id)
    if not order or order["status"] != "pending":
        return
    await db.confirm_order(order_id)
    product = await db.get_product(int(order["subcategory"])) if order["subcategory"].isdigit() else None
    if product:
        invite_link = await generate_invite_link(product)
        await db.save_order_invite_link(order_id, invite_link)
        try:
            await bot.send_message(
                order["user_id"],
                f"🎉 <b>Оплата подтверждена!</b>\n\n📦 #{order_id} | {product['name']}\n💳 {payment_method}\n\n"
                f"🔗 Ваша ссылка (одноразовая):\n{invite_link}\n\n⚠️ Ссылка работает 1 раз!\nЕсли потеряете доступ — нажмите «Получить доступ повторно» в заказах.\nСпасибо! 🎓",
                reply_markup=back_to_main_kb(), parse_mode="HTML",
            )
        except Exception as e:
            await db.log_error("send_message", str(e), user_id=order["user_id"], order_id=order_id, context="auto_confirm_order")
    await notify_admins(f"✅ <b>Автоподтверждение</b>\n\n📦 #{order_id} | {payment_method}\n👤 <code>{order['user_id']}</code>\n💰 {order['price']}₽")


# ─── Keyboards ───────────────────────────────────────────────────────────────

async def main_menu_kb() -> InlineKeyboardMarkup:
    categories = await db.get_active_categories()
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=f"{cat['emoji']} {cat['name']}", callback_data=f"cat_{cat['id']}",
        )])
    buttons.append([
        InlineKeyboardButton(text="📋 Мои заказы", callback_data="my_orders"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="faq_menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def products_in_category_kb(category_id: int) -> InlineKeyboardMarkup:
    products = await db.get_active_products(category_id)
    rate = await get_stars_rate()
    buttons = []
    for p in products:
        stars = rub_to_stars(p["price"], rate)
        buttons.append([InlineKeyboardButton(
            text=f"{p['name']} — {p['price']}₽ ({stars}⭐)", callback_data=f"sub_{p['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def payment_method_kb(product_id: int, price: int, category_id: int = 0) -> InlineKeyboardMarkup:
    rate = await get_stars_rate()
    stars_count = rub_to_stars(price, rate)
    yookassa = await S("yookassa_token")
    cryptobot = await S("cryptobot_token")
    robo_login = await S("robokassa_login")
    buttons = [
        [InlineKeyboardButton(text=f"⭐ Telegram Stars ({stars_count}⭐)", callback_data=f"pay_stars_{product_id}")],
    ]
    if yookassa:
        buttons.append([InlineKeyboardButton(text="💳 ЮKassa (карта, СБП)", callback_data=f"pay_yookassa_{product_id}")])
    if cryptobot:
        buttons.append([InlineKeyboardButton(text="🪙 CryptoBot (USDT, TON)", callback_data=f"pay_crypto_{product_id}")])
    if robo_login:
        buttons.append([InlineKeyboardButton(text="🏦 Robokassa", callback_data=f"pay_robokassa_{product_id}")])
    buttons.append([InlineKeyboardButton(text="💳 Перевод на карту", callback_data=f"pay_card_{product_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat_{category_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_order_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{order_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order_id}"),
    ]])


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")],
    ])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Ожидающие заказы", callback_data="adm_pending")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📋 Все заказы", callback_data="adm_all_orders")],
        [InlineKeyboardButton(text="🔎 Поиск", callback_data="adm_search")],
        [InlineKeyboardButton(text="💾 Резервные копии", callback_data="adm_backups")],
        [InlineKeyboardButton(text="⭐ Отзывы", callback_data="adm_reviews")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm_users")],
        [InlineKeyboardButton(text="👮 Админы", callback_data="adm_admins")],
        [InlineKeyboardButton(text="🛡 Антиспам и защита", callback_data="adm_security")],
        [InlineKeyboardButton(text="🧾 Логи ошибок", callback_data="adm_errors")],
        [InlineKeyboardButton(text="📜 Логи админов", callback_data="adm_admin_logs")],
        [InlineKeyboardButton(text="📂 Категории", callback_data="adm_categories")],
        [InlineKeyboardButton(text="🛒 Товары", callback_data="adm_products")],
        [InlineKeyboardButton(text="🔍 Узнать ID", callback_data="adm_get_id")],
        [InlineKeyboardButton(text="🤖 AI-помощник", callback_data="adm_ai")],
        [InlineKeyboardButton(text="⚙️ Настройки бота", callback_data="adm_settings")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_fsm")],
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  FSM CANCEL
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel_fsm")
async def cb_cancel_fsm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if await is_admin(callback.from_user.id):
        await callback.message.edit_text("❌ Отменено.", reply_markup=admin_menu_kb())
    else:
        await callback.message.edit_text("❌ Отменено.", reply_markup=back_to_main_kb())
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  USER COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if message.chat.type != "private":
        return
    await state.clear()
    await db.add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    welcome = await S("welcome_message", "🎓 <b>Добро пожаловать!</b>\n\nВыберите раздел:")
    await message.answer(welcome, reply_markup=await main_menu_kb(), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    if message.chat.type != "private":
        return
    await state.clear()
    welcome = await S("welcome_message", "📌 <b>Главное меню</b>")
    await message.answer(welcome, reply_markup=await main_menu_kb(), parse_mode="HTML")


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Ваш ID: <code>{message.from_user.id}</code>", parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id, message.from_user.username):
        return
    await state.clear()
    await message.answer("⚙️ <b>Панель администратора</b>", reply_markup=admin_menu_kb(), parse_mode="HTML")


@router.message(Command("help_admin"))
async def cmd_help_admin(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await message.answer(
        "📖 <b>Команды</b>\n\n"
        "/admin — Панель\n/stats — Статистика\n/pending — Ожидающие\n"
        "/orders — Заказы\n/confirm ID — Подтвердить\n/reject ID — Отклонить\n"
        "/users — Пользователи\n/backups — Резервные копии\n/reviews — Отзывы\n/broadcast текст — Рассылка\n"
        "/chatid — ID текущего чата\n"
        "/addadmin ID — Добавить\n/deladmin ID — Удалить\n/admins — Список\n\n"
        "🔍 Узнать ID, 📂 Категории, 🛒 Товары, ⚙️ Настройки — через кнопки в /admin",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await _send_stats(message)


async def _send_stats(target, edit: bool = False):
    stats = await db.get_stats()
    products = await db.get_all_products()
    categories = await db.get_all_categories()
    active_p = sum(1 for p in products if p["active"])
    active_c = sum(1 for c in categories if c["active"])
    rate = await get_stars_rate()
    usd_rate = await get_usd_rate()
    revenue_rub = stats["revenue"]
    revenue_stars = rub_to_stars(revenue_rub, rate) if revenue_rub > 0 else 0
    revenue_usd = round(revenue_rub / usd_rate, 2) if revenue_rub > 0 else 0
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"📦 Заказов: <b>{stats['orders']}</b>\n"
        f"✅ Подтверждено: <b>{stats['confirmed']}</b>\n"
        f"⏳ Ожидает: <b>{stats['pending']}</b>\n\n"
        f"💰 <b>Выручка:</b>\n"
        f"   💵 {revenue_rub} ₽\n"
        f"   💲 {revenue_usd} $\n"
        f"   ⭐ {revenue_stars} звёзд\n\n"
        f"📂 Категорий: {active_c}/{len(categories)}\n"
        f"🛒 Товаров: {active_p}/{len(products)}"
    )
    if edit and hasattr(target, "edit_text"):
        await target.edit_text(text, reply_markup=admin_menu_kb(), parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=admin_menu_kb() if await is_admin(target.from_user.id if hasattr(target, "from_user") else 0) else None, parse_mode="HTML")


@router.message(Command("pending"))
async def cmd_pending(message: Message):
    if not await is_admin(message.from_user.id):
        return
    orders = await db.get_pending_orders()
    if not orders:
        await message.answer("📦 Нет ожидающих.")
        return
    for o in orders:
        product = await db.get_product(int(o["subcategory"])) if o["subcategory"].isdigit() else None
        sub_name = product["name"] if product else o["subcategory"]
        await message.answer(
            f"📦 <b>#{o['id']}</b> | <code>{o['user_id']}</code> | {sub_name} | {o['price']}₽",
            reply_markup=admin_order_kb(o["id"]), parse_mode="HTML",
        )


@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if not await is_admin(message.from_user.id):
        return
    orders = await db.get_all_orders(20)
    if not orders:
        await message.answer("📋 Нет заказов.")
        return
    emoji = {"pending": "⏳", "confirmed": "✅", "rejected": "❌"}
    lines = ["📋 <b>Заказы</b>\n"]
    for o in orders:
        product = await db.get_product(int(o["subcategory"])) if o["subcategory"].isdigit() else None
        sub_name = product["name"] if product else o["subcategory"]
        lines.append(f"{emoji.get(o['status'], '❓')} #{o['id']} | {sub_name} | {o['price']}₽")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("users"))
async def cmd_users(message: Message):
    if not await is_admin(message.from_user.id):
        return
    users = await db.get_all_users()
    if not users:
        await message.answer("👥 Нет.")
        return
    lines = [f"👥 <b>{len(users)} пользователей</b>\n"]
    for u in users[:50]:
        lines.append(f"• <code>{u['user_id']}</code> | @{u['username'] or '—'} | {u['full_name']}")
    if len(users) > 50:
        lines.append(f"... +{len(users) - 50}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("confirm"))
async def cmd_confirm(message: Message):
    if not await is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❓ /confirm <code>ID</code>", parse_mode="HTML")
        return
    order_id = int(args[1])
    order = await db.get_order(order_id)
    if not order:
        await message.answer(f"❌ #{order_id} не найден.")
        return
    if order["status"] != "pending":
        await message.answer(f"ℹ️ #{order_id} уже обработан.")
        return
    await _confirm_and_notify(order_id, order, message)


@router.message(Command("reject"))
async def cmd_reject(message: Message):
    if not await is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❓ /reject <code>ID</code>", parse_mode="HTML")
        return
    order_id = int(args[1])
    order = await db.get_order(order_id)
    if not order:
        await message.answer(f"❌ #{order_id} не найден.")
        return
    if order["status"] != "pending":
        await message.answer(f"ℹ️ #{order_id} уже обработан.")
        return
    await _reject_and_notify(order_id, order, message)


@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message):
    if not await is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❓ /addadmin <code>ID</code>", parse_mode="HTML")
        return
    new_id = int(args[1])
    user = await db.get_user(new_id)
    await db.add_admin(new_id, user["username"] if user else None, message.from_user.id)
    await message.answer(f"✅ Админ {new_id} добавлен.")
    await set_commands()


@router.message(Command("deladmin"))
async def cmd_deladmin(message: Message):
    if not await is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❓ /deladmin <code>ID</code>", parse_mode="HTML")
        return
    removed_id = int(args[1])
    await db.remove_admin(removed_id)
    try:
        cmds = [BotCommand(command="start", description="🎓 Главное меню"), BotCommand(command="menu", description="📌 Меню"), BotCommand(command="myid", description="🆔 Мой ID")]
        await bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=removed_id))
    except Exception:
        pass
    await message.answer(f"✅ Админ {removed_id} удалён.")


@router.message(Command("admins"))
async def cmd_admins(message: Message):
    if not await is_admin(message.from_user.id):
        return
    admins = await db.get_all_admins()
    lines = ["👮 <b>Админы</b>\n"]
    if config.ADMIN_ID:
        lines.append(f"👑 <code>{config.ADMIN_ID}</code> — Главный")
    for a in admins:
        lines.append(f"• <code>{a['user_id']}</code> | @{a['username'] or '—'}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not await is_admin(message.from_user.id):
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("❓ /broadcast <code>текст</code>", parse_mode="HTML")
        return
    users = await db.get_all_users()
    sent, failed = 0, 0
    for u in users:
        try:
            await bot.send_message(u["user_id"], f"📢 {text}")
            sent += 1
        except Exception:
            failed += 1
    await message.answer(f"📢 ✅ {sent} | ❌ {failed}")


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN: Settings
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_settings")
async def cb_adm_settings(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer()
    await _show_settings_menu(callback.message)


async def _show_settings_menu(message: Message, edit: bool = True):
    card = await S("payment_card", "—")
    name = await S("payment_name", "—")
    rate = await S("stars_rate", "1.85")
    usd = await S("usd_rate", "90")
    yookassa = "✅" if await S("yookassa_token") else "❌"
    cryptobot_s = "✅" if await S("cryptobot_token") else "❌"
    robo = "✅" if await S("robokassa_login") else "❌"
    contacts = await get_support_contacts()
    contacts_str = ", ".join(c.get("username", "?") for c in contacts) if contacts else "(нет)"
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"💳 Карта: <code>{card}</code> | {name}\n"
        f"⭐ 1⭐ = {rate}₽ | 💲 1$ = {usd}₽\n"
        f"💳 ЮKassa: {yookassa} | 🪙 Crypto: {cryptobot_s} | 🏦 Robo: {robo}\n"
        f"🆘 Поддержка: {contacts_str}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Приветственное сообщение", callback_data="set_edit_welcome_message")],
        [InlineKeyboardButton(text="💳 Реквизиты карты", callback_data="set_card_menu")],
        [InlineKeyboardButton(text="⭐ Курс звёзд", callback_data="set_edit_stars_rate"),
         InlineKeyboardButton(text="💲 Курс доллара", callback_data="set_edit_usd_rate")],
        [InlineKeyboardButton(text="💳 ЮKassa", callback_data="set_edit_yookassa_token"),
         InlineKeyboardButton(text="🪙 CryptoBot", callback_data="set_edit_cryptobot_token")],
        [InlineKeyboardButton(text="🏦 Robokassa", callback_data="set_robo_menu")],
        [InlineKeyboardButton(text="🆘 Контакты поддержки", callback_data="set_contacts_menu")],
        [InlineKeyboardButton(text="💬 Группа тикетов", callback_data="set_edit_ticket_group_id")],
        [InlineKeyboardButton(text="🔔 Напоминание оплаты", callback_data="set_edit_pending_order_reminder_minutes"),
         InlineKeyboardButton(text="⭐ Отзыв через часов", callback_data="set_edit_review_request_delay_hours")],
        [InlineKeyboardButton(text="💾 Автобэкап вкл/выкл", callback_data="set_toggle_daily_backup_enabled"),
         InlineKeyboardButton(text="🗓 Хранить бэкапы дней", callback_data="set_edit_daily_backup_keep_days")],
        [InlineKeyboardButton(text="🏷 Водяной знак", callback_data="set_toggle_watermark_enabled"),
         InlineKeyboardButton(text="📝 Название проекта", callback_data="set_edit_watermark_project_name")],
        [InlineKeyboardButton(text="🤖 AI: API ключ", callback_data="set_edit_openai_api_key"),
         InlineKeyboardButton(text="🤖 AI: Модель", callback_data="set_edit_openai_model")],
        [InlineKeyboardButton(text="🤖 AI: Base URL", callback_data="set_edit_openai_base_url")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back_main")],
    ])
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "set_card_menu")
async def cb_card_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.clear()
    card = await S("payment_card", "—")
    name = await S("payment_name", "—")
    method = await S("payment_method", "—")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Номер карты", callback_data="set_edit_payment_card")],
        [InlineKeyboardButton(text="👤 ФИО", callback_data="set_edit_payment_name")],
        [InlineKeyboardButton(text="💳 Способ", callback_data="set_edit_payment_method")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_settings")],
    ])
    await callback.message.edit_text(
        f"💳 <b>Реквизиты</b>\n\n💳 {card}\n👤 {name}\n💳 {method}",
        reply_markup=kb, parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "set_robo_menu")
async def cb_robo_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.clear()
    login = await S("robokassa_login") or "(нет)"
    test = "Да" if await S("robokassa_test", "1") == "1" else "Нет"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Логин", callback_data="set_edit_robokassa_login")],
        [InlineKeyboardButton(text="🔐 Пароль 1", callback_data="set_edit_robokassa_password1")],
        [InlineKeyboardButton(text="🔐 Пароль 2", callback_data="set_edit_robokassa_password2")],
        [InlineKeyboardButton(text=f"🧪 Тест: {test}", callback_data="set_toggle_robokassa_test")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_settings")],
    ])
    await callback.message.edit_text(f"🏦 <b>Robokassa</b>\n\nЛогин: <code>{login}</code>\nТест: {test}", reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "set_toggle_robokassa_test")
async def cb_toggle_robo_test(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    current = await S("robokassa_test", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("robokassa_test", new_val)
    await callback.answer(f"Тест: {'Вкл' if new_val == '1' else 'Выкл'}")
    # Refresh
    login = await S("robokassa_login") or "(нет)"
    test = "Да" if new_val == "1" else "Нет"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Логин", callback_data="set_edit_robokassa_login")],
        [InlineKeyboardButton(text="🔐 Пароль 1", callback_data="set_edit_robokassa_password1")],
        [InlineKeyboardButton(text="🔐 Пароль 2", callback_data="set_edit_robokassa_password2")],
        [InlineKeyboardButton(text=f"🧪 Тест: {test}", callback_data="set_toggle_robokassa_test")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_settings")],
    ])
    await callback.message.edit_text(f"🏦 <b>Robokassa</b>\n\nЛогин: <code>{login}</code>\nТест: {test}", reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "set_toggle_daily_backup_enabled")
async def cb_toggle_daily_backup(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    current = await S("daily_backup_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("daily_backup_enabled", new_val)
    await callback.answer(f"Автобэкап: {'включён' if new_val == '1' else 'выключен'}")
    await _show_settings_menu(callback.message)


@router.callback_query(F.data == "set_toggle_watermark_enabled")
async def cb_toggle_watermark(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    current = await S("watermark_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("watermark_enabled", new_val)
    await callback.answer(f"Водяной знак: {'включён' if new_val == '1' else 'выключен'}")
    await _show_settings_menu(callback.message)


SETTING_LABELS = {
    "payment_card": "💳 Номер карты",
    "payment_name": "👤 ФИО получателя",
    "payment_method": "💳 Способ перевода",
    "stars_rate": "⭐ Курс звёзд (₽ за 1⭐)",
    "usd_rate": "💲 Курс доллара (₽ за 1$)",
    "yookassa_token": "💳 ЮKassa provider_token",
    "cryptobot_token": "🪙 CryptoBot API токен",
    "robokassa_login": "🏦 Robokassa логин",
    "robokassa_password1": "🏦 Robokassa пароль 1",
    "robokassa_password2": "🏦 Robokassa пароль 2",
    "ticket_group_id": "💬 ID группы тикетов",
    "welcome_message": "📝 Приветственное сообщение",
    "antispam_message_limit_per_minute": "🛡 Лимит сообщений в минуту",
    "payment_button_cooldown_seconds": "🕒 Задержка повторного нажатия оплаты, сек",
    "max_access_reissues_per_order": "🔁 Лимит повторной выдачи ссылки",
    "error_log_limit": "🧾 Количество строк в отчете ошибок",
    "pending_order_reminder_minutes": "🔔 Напоминание о неоплаченном заказе, минут",
    "daily_backup_keep_days": "💾 Сколько дней хранить автобэкапы",
    "review_request_delay_hours": "⭐ Через сколько часов просить отзыв",
    "watermark_project_name": "🏷 Название проекта для водяного знака",
    "openai_api_key": "🤖 OpenAI API ключ",
    "openai_model": "🤖 Модель AI (например gpt-4o-mini)",
    "openai_base_url": "🤖 Base URL API (по умолчанию OpenAI)",
}


@router.callback_query(F.data.startswith("set_edit_"))
async def cb_set_edit(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    key = callback.data.removeprefix("set_edit_")
    label = SETTING_LABELS.get(key, key)
    current = await S(key, "(пусто)")
    if key in ("robokassa_password1", "robokassa_password2", "yookassa_token", "cryptobot_token", "openai_api_key"):
        display = "***" if current else "(пусто)"
    elif key == "welcome_message":
        display = current[:200] + "..." if len(current) > 200 else current
    else:
        display = current or "(пусто)"
    await state.set_state(EditSetting.waiting_value)
    await state.update_data(setting_key=key)
    hint = ""
    if key == "welcome_message":
        hint = "\n\n💡 Поддерживается HTML: <b>жирный</b>, <i>курсив</i>, <code>код</code>"
    await callback.message.edit_text(
        f"✏️ <b>{label}</b>\n\nТекущее:\n<code>{display}</code>{hint}\n\nВведите новое (или <b>-</b> чтобы очистить):",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditSetting.waiting_value, F.text, F.chat.type == "private")
async def fsm_setting_value(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    key = data["setting_key"]
    value = message.text.strip()
    if value == "-":
        value = ""
    if key in ("stars_rate", "usd_rate"):
        try:
            float(value)
        except ValueError:
            await message.answer("❌ Введите число:", reply_markup=cancel_kb())
            return
    if key in ("antispam_message_limit_per_minute", "payment_button_cooldown_seconds", "max_access_reissues_per_order", "error_log_limit", "pending_order_reminder_minutes", "daily_backup_keep_days", "review_request_delay_hours"):
        if not value.isdigit():
            await message.answer("❌ Введите целое число:", reply_markup=cancel_kb())
            return
    await db.set_setting(key, value)
    await state.clear()
    label = SETTING_LABELS.get(key, key)
    await message.answer(f"✅ <b>{label}</b> обновлено!", reply_markup=admin_menu_kb(), parse_mode="HTML")


# ─── Support contacts ────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_contacts_menu")
async def cb_contacts_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.clear()
    contacts = await get_support_contacts()
    lines = ["🆘 <b>Контакты</b>\n"]
    buttons = []
    if not contacts:
        lines.append("(нет)")
    for i, c in enumerate(contacts):
        lines.append(f"{i+1}. {c.get('name','?')} — {c.get('username','?')}")
        buttons.append([InlineKeyboardButton(text=f"🗑 {c.get('name','?')}", callback_data=f"set_del_contact_{i}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="set_add_contact")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_settings")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "set_add_contact")
async def cb_add_contact(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.set_state(AddContact.name)
    await callback.message.edit_text("➕ Введите <b>имя/роль</b>:", reply_markup=cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(AddContact.name, F.text, F.chat.type == "private")
async def fsm_contact_name(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await state.update_data(contact_name=message.text.strip())
    await state.set_state(AddContact.username)
    await message.answer("Введите <b>username</b> (например @support):", reply_markup=cancel_kb(), parse_mode="HTML")


@router.message(AddContact.username, F.text, F.chat.type == "private")
async def fsm_contact_username(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    contacts = await get_support_contacts()
    contacts.append({"name": data["contact_name"], "username": message.text.strip()})
    await db.set_setting("support_contacts", json.dumps(contacts, ensure_ascii=False))
    await state.clear()
    await message.answer("✅ Контакт добавлен!", reply_markup=admin_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data.startswith("set_del_contact_"))
async def cb_del_contact(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    idx = int(callback.data.removeprefix("set_del_contact_"))
    contacts = await get_support_contacts()
    if 0 <= idx < len(contacts):
        contacts.pop(idx)
        await db.set_setting("support_contacts", json.dumps(contacts, ensure_ascii=False))
    await callback.answer("Удалён")
    # Refresh
    lines = ["🆘 <b>Контакты</b>\n"]
    buttons = []
    if not contacts:
        lines.append("(нет)")
    for i, c in enumerate(contacts):
        lines.append(f"{i+1}. {c.get('name','?')} — {c.get('username','?')}")
        buttons.append([InlineKeyboardButton(text=f"🗑 {c.get('name','?')}", callback_data=f"set_del_contact_{i}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="set_add_contact")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_settings")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN: Category Management
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_categories")
async def cb_adm_categories(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer()
    await _show_categories_menu(callback.message)


async def _show_categories_menu(message: Message, edit: bool = True):
    categories = await db.get_all_categories()
    lines = ["📂 <b>Категории</b>\n"]
    if not categories:
        lines.append("Нет категорий.")
    buttons = []
    for c in categories:
        status = "✅" if c["active"] else "❌"
        lines.append(f"{status} #{c['id']} {c['emoji']} {c['name']}")
        buttons.append([InlineKeyboardButton(text=f"✏️ {c['emoji']} {c['name'][:20]}", callback_data=f"catedit_{c['id']}")])
    buttons.append([InlineKeyboardButton(text="➕ Новая категория", callback_data="cat_add")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "cat_add")
async def cb_cat_add(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.set_state(AddCategory.emoji)
    await callback.message.edit_text(
        "➕ <b>Новая категория</b>\n\nШаг 1/3: Отправьте <b>эмодзи</b> (например 🎬):",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddCategory.emoji, F.text, F.chat.type == "private")
async def fsm_cat_emoji(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await state.update_data(emoji=message.text.strip()[:4])
    await state.set_state(AddCategory.name)
    await message.answer("Шаг 2/3: <b>Название</b> категории:", reply_markup=cancel_kb(), parse_mode="HTML")


@router.message(AddCategory.name, F.text, F.chat.type == "private")
async def fsm_cat_name(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await state.update_data(cat_name=message.text.strip())
    await state.set_state(AddCategory.description)
    await message.answer("Шаг 3/3: <b>Описание</b> (или <b>-</b> без описания):", reply_markup=cancel_kb(), parse_mode="HTML")


@router.message(AddCategory.description, F.text, F.chat.type == "private")
async def fsm_cat_desc(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    desc = message.text.strip()
    if desc == "-":
        desc = ""
    cat_id = await db.add_category(name=data["cat_name"], description=desc, emoji=data["emoji"])
    await state.clear()
    await message.answer(
        f"✅ Категория #{cat_id} создана!\n\n{data['emoji']} <b>{data['cat_name']}</b>\n{desc}",
        reply_markup=admin_menu_kb(), parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("catedit_"))
async def cb_cat_edit(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    cat_id = int(callback.data.removeprefix("catedit_"))
    await _show_cat_edit(callback, cat_id)


async def _show_cat_edit(callback: CallbackQuery, cat_id: int):
    cat = await db.get_category(cat_id)
    if not cat:
        await callback.answer("Не найдена", show_alert=True)
        return
    status = "✅ Активна" if cat["active"] else "❌ Скрыта"
    toggle = "❌ Скрыть" if cat["active"] else "✅ Показать"
    products = await db.get_active_products(cat_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Эмодзи", callback_data=f"catset_{cat_id}_emoji"),
         InlineKeyboardButton(text="✏️ Название", callback_data=f"catset_{cat_id}_name")],
        [InlineKeyboardButton(text="📝 Описание", callback_data=f"catset_{cat_id}_description")],
        [InlineKeyboardButton(text=toggle, callback_data=f"cattoggle_{cat_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"catdel_{cat_id}")],
        [InlineKeyboardButton(text="⬅️ К категориям", callback_data="adm_categories")],
    ])
    await callback.message.edit_text(
        f"✏️ <b>Категория #{cat_id}</b>\n\n"
        f"{cat['emoji']} <b>{cat['name']}</b>\n"
        f"📝 {cat['description'] or '(нет описания)'}\n"
        f"📊 {status} | 🛒 {len(products)} товаров",
        reply_markup=kb, parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cattoggle_"))
async def cb_cat_toggle(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    cat_id = int(callback.data.removeprefix("cattoggle_"))
    cat = await db.get_category(cat_id)
    if not cat:
        await callback.answer("Не найдена", show_alert=True)
        return
    await db.update_category(cat_id, active=0 if cat["active"] else 1)
    await _show_cat_edit(callback, cat_id)


@router.callback_query(F.data.startswith("catdel_"))
async def cb_cat_del(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    cat_id = int(callback.data.removeprefix("catdel_"))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"catdelok_{cat_id}")],
        [InlineKeyboardButton(text="⬅️ Нет", callback_data=f"catedit_{cat_id}")],
    ])
    await callback.message.edit_text(f"❓ Удалить категорию #{cat_id}?\n⚠️ Товары в ней останутся без категории.", reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("catdelok_"))
async def cb_cat_del_ok(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    cat_id = int(callback.data.removeprefix("catdelok_"))
    await db.delete_category(cat_id)
    await callback.answer("Удалена!")
    await _show_categories_menu(callback.message)


@router.callback_query(F.data.startswith("catset_"))
async def cb_cat_set(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    parts = callback.data.removeprefix("catset_").split("_", 1)
    cat_id = int(parts[0])
    field = parts[1]
    labels = {"emoji": "эмодзи", "name": "название", "description": "описание"}
    await state.set_state(EditCategory.new_value)
    await state.update_data(cat_id=cat_id, cat_field=field)
    await callback.message.edit_text(f"✏️ Введите новое <b>{labels.get(field, field)}</b>:", reply_markup=cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(EditCategory.new_value, F.text, F.chat.type == "private")
async def fsm_cat_edit_value(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    value = message.text.strip()
    if value == "-":
        value = ""
    await db.update_category(data["cat_id"], **{data["cat_field"]: value})
    await state.clear()
    await message.answer("✅ Обновлено!", reply_markup=admin_menu_kb(), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN: Product Management
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_products")
async def cb_adm_products(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer()
    await _show_products_menu(callback.message)


async def _show_products_menu(message: Message, edit: bool = True):
    products = await db.get_all_products()
    categories = {c["id"]: c for c in await db.get_all_categories()}
    lines = ["🛒 <b>Товары</b>\n"]
    if not products:
        lines.append("Нет товаров.")
    buttons = []
    for p in products:
        status = "✅" if p["active"] else "❌"
        cat = categories.get(p["category_id"])
        cat_name = f"{cat['emoji']}" if cat else "❓"
        lines.append(f"{status} #{p['id']} {cat_name} {p['name']} — {p['price']}₽")
        buttons.append([InlineKeyboardButton(text=f"✏️ #{p['id']} {p['name'][:20]}", callback_data=f"prod_edit_{p['id']}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить товар", callback_data="prod_add")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back_main")])
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_back_main")
async def cb_adm_back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await is_admin(callback.from_user.id, callback.from_user.username)
    await callback.message.edit_text("⚙️ <b>Панель</b>", reply_markup=admin_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "prod_add")
async def cb_prod_add(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    categories = await db.get_all_categories()
    if not categories:
        await callback.answer("Сначала создайте категорию!", show_alert=True)
        return
    buttons = []
    for c in categories:
        buttons.append([InlineKeyboardButton(text=f"{c['emoji']} {c['name']}", callback_data=f"prod_add_cat_{c['id']}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="adm_products")])
    await callback.message.edit_text("➕ Выберите <b>категорию</b> для нового товара:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("prod_add_cat_"))
async def cb_prod_add_cat(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    cat_id = int(callback.data.removeprefix("prod_add_cat_"))
    await state.update_data(category_id=cat_id)
    await state.set_state(AddProduct.name)
    await callback.message.edit_text("Шаг 1/5: <b>Название</b> товара:", reply_markup=cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(AddProduct.name, F.text, F.chat.type == "private")
async def fsm_add_name(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProduct.description)
    await message.answer("Шаг 2/5: <b>Описание</b>:", reply_markup=cancel_kb(), parse_mode="HTML")


@router.message(AddProduct.description, F.text, F.chat.type == "private")
async def fsm_add_desc(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(AddProduct.price)
    await message.answer("Шаг 3/5: <b>Цена</b> в рублях:", reply_markup=cancel_kb(), parse_mode="HTML")


@router.message(AddProduct.price, F.text, F.chat.type == "private")
async def fsm_add_price(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    text = message.text.strip().replace(" ", "")
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ Число > 0:", reply_markup=cancel_kb())
        return
    await state.update_data(price=int(text))
    await state.set_state(AddProduct.channel_id)
    await message.answer(
        "Шаг 4/5: <b>ID канала</b> для ссылок:\n<code>-100XXXXXXXXXX</code> или <code>@channel</code>\nИли <b>-</b>",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )


@router.message(AddProduct.channel_id, F.text, F.chat.type == "private")
async def fsm_add_chid(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    text = message.text.strip()
    await state.update_data(channel_id="" if text == "-" else text)
    await state.set_state(AddProduct.channel_link)
    await message.answer("Шаг 5/5: <b>Запасная ссылка</b> (или <b>-</b>):", reply_markup=cancel_kb(), parse_mode="HTML")


@router.message(AddProduct.channel_link, F.text, F.chat.type == "private")
async def fsm_add_link(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    link = message.text.strip()
    if link == "-":
        link = ""
    data = await state.get_data()
    pid = await db.add_product(
        name=data["name"], description=data["description"], price=data["price"],
        channel_link=link, channel_id=data.get("channel_id", ""), category_id=data.get("category_id", 0),
    )
    await state.clear()
    rate = await get_stars_rate()
    stars = rub_to_stars(data["price"], rate)
    await message.answer(
        f"✅ Товар #{pid} добавлен!\n{data['name']} — {data['price']}₽ ({stars}⭐)",
        reply_markup=admin_menu_kb(), parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("prod_edit_"))
async def cb_prod_edit(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    pid = int(callback.data.removeprefix("prod_edit_"))
    await _show_product_edit(callback, pid)


async def _show_product_edit(callback: CallbackQuery, pid: int):
    p = await db.get_product(pid)
    if not p:
        await callback.answer("Не найден", show_alert=True)
        return
    rate = await get_stars_rate()
    status = "✅" if p["active"] else "❌"
    stars = rub_to_stars(p["price"], rate)
    toggle = "❌ Скрыть" if p["active"] else "✅ Показать"
    cat = await db.get_category(p["category_id"]) if p["category_id"] else None
    cat_name = f"{cat['emoji']} {cat['name']}" if cat else "(без категории)"
    ch = p.get("channel_id", "") or "(нет)"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"prod_set_{pid}_name")],
        [InlineKeyboardButton(text="📝 Описание", callback_data=f"prod_set_{pid}_description")],
        [InlineKeyboardButton(text="💰 Цена", callback_data=f"prod_set_{pid}_price")],
        [InlineKeyboardButton(text="📂 Категория", callback_data=f"prod_setcat_{pid}")],
        [InlineKeyboardButton(text="📺 ID канала", callback_data=f"prod_set_{pid}_channel_id")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"prod_set_{pid}_channel_link")],
        [InlineKeyboardButton(text=toggle, callback_data=f"prod_toggle_{pid}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"prod_del_{pid}")],
        [InlineKeyboardButton(text="⬅️ К товарам", callback_data="adm_products")],
    ])
    await callback.message.edit_text(
        f"✏️ <b>Товар #{pid}</b>\n\n📦 {p['name']}\n📝 {p['description'][:100] or '—'}\n"
        f"💰 {p['price']}₽ ({stars}⭐)\n📂 {cat_name}\n📺 <code>{ch}</code>\n"
        f"🔗 {p['channel_link'] or '(нет)'}\n{status}",
        reply_markup=kb, parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prod_setcat_"))
async def cb_prod_setcat(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    pid = int(callback.data.removeprefix("prod_setcat_"))
    categories = await db.get_all_categories()
    buttons = []
    for c in categories:
        buttons.append([InlineKeyboardButton(text=f"{c['emoji']} {c['name']}", callback_data=f"prod_setcatok_{pid}_{c['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"prod_edit_{pid}")])
    await callback.message.edit_text("Выберите новую категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("prod_setcatok_"))
async def cb_prod_setcat_ok(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    parts = callback.data.removeprefix("prod_setcatok_").split("_")
    pid, cat_id = int(parts[0]), int(parts[1])
    await db.update_product(pid, category_id=cat_id)
    await callback.answer("Категория обновлена!")
    await _show_product_edit(callback, pid)


@router.callback_query(F.data.startswith("prod_toggle_"))
async def cb_prod_toggle(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    pid = int(callback.data.removeprefix("prod_toggle_"))
    p = await db.get_product(pid)
    if not p:
        await callback.answer("Не найден", show_alert=True)
        return
    await db.update_product(pid, active=0 if p["active"] else 1)
    await _show_product_edit(callback, pid)


@router.callback_query(F.data.startswith("prod_del_"))
async def cb_prod_del(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    pid = int(callback.data.removeprefix("prod_del_"))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Да", callback_data=f"prod_del_ok_{pid}")],
        [InlineKeyboardButton(text="⬅️ Нет", callback_data=f"prod_edit_{pid}")],
    ])
    await callback.message.edit_text(f"❓ Удалить товар #{pid}?", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("prod_del_ok_"))
async def cb_prod_del_ok(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    pid = int(callback.data.removeprefix("prod_del_ok_"))
    await db.delete_product(pid)
    await callback.answer("Удалён!")
    await _show_products_menu(callback.message)


@router.callback_query(F.data.startswith("prod_set_"))
async def cb_prod_set(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    parts = callback.data.removeprefix("prod_set_").split("_", 1)
    pid = int(parts[0])
    field = parts[1]
    labels = {"name": "название", "description": "описание", "price": "цену", "channel_id": "ID канала", "channel_link": "ссылку"}
    await state.set_state(EditProduct.new_value)
    await state.update_data(product_id=pid, field=field)
    await callback.message.edit_text(f"✏️ Введите <b>{labels.get(field, field)}</b>:", reply_markup=cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(EditProduct.new_value, F.text, F.chat.type == "private")
async def fsm_edit_value(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    field = data["field"]
    value = message.text.strip()
    if value == "-":
        value = ""
    if field == "price":
        clean = value.replace(" ", "")
        if not clean.isdigit() or int(clean) <= 0:
            await message.answer("❌ Число > 0:", reply_markup=cancel_kb())
            return
        value = int(clean)
    await db.update_product(data["product_id"], **{field: value})
    await state.clear()
    await message.answer("✅ Обновлено!", reply_markup=admin_menu_kb(), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
#  PAYMENTS
# ══════════════════════════════════════════════════════════════════════════════

@router.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    payment = message.successful_payment
    parts = payment.invoice_payload.split("_")
    if len(parts) >= 3 and parts[0] == "order" and parts[1].isdigit():
        method = "⭐ Stars" if parts[2] == "stars" else "💳 ЮKassa"
        await auto_confirm_order(int(parts[1]), method)


# ══════════════════════════════════════════════════════════════════════════════
#  GROUP HANDLER
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.message_thread_id, F.chat.type.in_({"group", "supergroup"}))
async def group_reply_handler(message: Message):
    if message.from_user.id == bot.id:
        return
    if message.text and message.text.startswith("/"):
        return
    group_id = await get_ticket_group_id()
    if message.chat.id != group_id:
        return
    user_id = await db.get_user_by_topic(message.message_thread_id)
    if not user_id:
        return
    try:
        if message.text:
            await bot.send_message(user_id, f"💬 {message.text}")
        elif message.photo:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption=f"💬 {message.caption}" if message.caption else None)
        elif message.document:
            await bot.send_document(user_id, message.document.file_id, caption=f"💬 {message.caption}" if message.caption else None)
        elif message.video:
            await bot.send_video(user_id, message.video.file_id, caption=f"💬 {message.caption}" if message.caption else None)
        elif message.sticker:
            await bot.send_sticker(user_id, message.sticker.file_id)
        elif message.voice:
            await bot.send_voice(user_id, message.voice.file_id)
    except Exception as e:
        await message.reply(f"❌ {e}")



# ══════════════════════════════════════════════════════════════════════════════
#  ID LOOKUP
# ══════════════════════════════════════════════════════════════════════════════

GETID_REQUEST_GROUP = 7101
GETID_REQUEST_CHANNEL = 7102
GETID_REQUEST_USER = 7103


@router.message(Command("chatid"))
async def cmd_chatid(message: Message):
    """Works in any chat — shows the chat ID. For groups/channels: add bot and send /chatid there."""
    chat = message.chat
    chat_type_label = {
        "private": "👤 Личный чат",
        "group": "💬 Группа",
        "supergroup": "💬 Супергруппа",
        "channel": "📺 Канал",
    }.get(chat.type, chat.type)
    text = (
        f"🔍 <b>{chat_type_label}</b>\n\n"
        f"🆔 ID: <code>{chat.id}</code>\n"
        f"📛 Название: {html(chat.title or chat.full_name)}\n"
        f"📱 Username: @{html(chat.username)}"
    )
    if chat.type == "private":
        text += f"\n\n👤 Ваш ID: <code>{message.from_user.id}</code>"
    await message.answer(text, parse_mode="HTML")


def _getid_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Ещё", callback_data="adm_get_id")],
        [InlineKeyboardButton(text="⬅️ Панель", callback_data="adm_back_main")],
    ])


def _publish_admin_rights(chat_is_channel: bool):
    if ChatAdministratorRights is None:
        return None
    kwargs = {
        "is_anonymous": False,
        "can_manage_chat": True,
        "can_delete_messages": False,
        "can_manage_video_chats": False,
        "can_restrict_members": False,
        "can_promote_members": False,
        "can_change_info": False,
        "can_invite_users": True,
        "can_post_stories": False,
        "can_edit_stories": False,
        "can_delete_stories": False,
    }
    if chat_is_channel:
        kwargs.update({"can_post_messages": True, "can_edit_messages": False})
    else:
        kwargs.update({"can_pin_messages": False, "can_manage_topics": False})
    try:
        return ChatAdministratorRights(**kwargs)
    except Exception:
        try:
            return ChatAdministratorRights(can_manage_chat=True, can_post_messages=chat_is_channel)
        except Exception:
            return None


def _make_request_chat(chat_is_channel: bool, request_id: int, for_publish: bool = False) -> KeyboardButtonRequestChat:
    """Build a request_chat object while staying compatible with older aiogram/Bot API schemas."""
    rich_kwargs = {
        "request_id": request_id,
        "chat_is_channel": chat_is_channel,
        "request_title": True,
        "request_username": True,
        "request_photo": False,
    }
    if for_publish:
        rich_kwargs["bot_is_member"] = True
        rights = _publish_admin_rights(chat_is_channel)
        if rights is not None:
            rich_kwargs["bot_administrator_rights"] = rights
            rich_kwargs["user_administrator_rights"] = rights
    try:
        return KeyboardButtonRequestChat(**rich_kwargs)
    except Exception:
        fallback_kwargs = {
            "request_id": request_id,
            "chat_is_channel": chat_is_channel,
        }
        if for_publish:
            fallback_kwargs["bot_is_member"] = True
        try:
            return KeyboardButtonRequestChat(**fallback_kwargs)
        except Exception:
            return KeyboardButtonRequestChat(request_id=request_id, chat_is_channel=chat_is_channel)


def _make_request_user_button() -> KeyboardButton:
    """Build a user picker button for both old singular and newer plural Bot API schemas."""
    if KeyboardButtonRequestUsers is not None:
        rich_kwargs = {
            "request_id": GETID_REQUEST_USER,
            "max_quantity": 1,
            "request_name": True,
            "request_username": True,
            "request_photo": False,
        }
        try:
            request_users = KeyboardButtonRequestUsers(**rich_kwargs)
        except Exception:
            request_users = KeyboardButtonRequestUsers(request_id=GETID_REQUEST_USER, max_quantity=1)
        return KeyboardButton(text="👤 Выбрать человека", request_users=request_users)

    if KeyboardButtonRequestUser is not None:
        return KeyboardButton(
            text="👤 Выбрать человека",
            request_user=KeyboardButtonRequestUser(request_id=GETID_REQUEST_USER),
        )

    # Extremely old aiogram builds should not normally get here.
    return KeyboardButton(text="👤 Отправьте @username или пересланное сообщение")


def getid_reply_keyboard(id_type: str) -> ReplyKeyboardMarkup:
    if id_type == "group":
        button = KeyboardButton(
            text="💬 Выбрать группу",
            request_chat=_make_request_chat(chat_is_channel=False, request_id=GETID_REQUEST_GROUP),
        )
        placeholder = "Нажмите «Выбрать группу»"
    elif id_type == "channel":
        button = KeyboardButton(
            text="📺 Выбрать канал",
            request_chat=_make_request_chat(chat_is_channel=True, request_id=GETID_REQUEST_CHANNEL),
        )
        placeholder = "Нажмите «Выбрать канал»"
    else:
        button = _make_request_user_button()
        placeholder = "Нажмите «Выбрать человека»"

    return ReplyKeyboardMarkup(
        keyboard=[[button], [KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=placeholder,
    )


@router.message(F.text == "❌ Отмена", F.chat.type == "private")
async def msg_cancel_reply_keyboard(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("❌ Отменено.", reply_markup=ReplyKeyboardRemove())
    await message.answer("⚙️ <b>Панель администратора</b>", reply_markup=admin_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "adm_get_id")
async def cb_get_id_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 ID человека", callback_data="getid_user")],
        [InlineKeyboardButton(text="💬 ID группы", callback_data="getid_group")],
        [InlineKeyboardButton(text="📺 ID канала", callback_data="getid_channel")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back_main")],
    ])
    await callback.message.edit_text(
        "🔍 <b>Узнать ID</b>\n\n"
        "Теперь работает как у @userinfo3bot:\n"
        "1️⃣ выберите тип — человек, группа или канал;\n"
        "2️⃣ бот покажет кнопку выбора;\n"
        "3️⃣ Telegram откроет список ваших чатов и спросит подтверждение отправки;\n"
        "4️⃣ после отправки бот сразу покажет ID.\n\n"
        "💡 Резервный способ тоже остался: можно переслать сообщение, отправить @username или числовой ID.",
        reply_markup=kb, parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.in_({"getid_user", "getid_group", "getid_channel"}))
async def cb_getid_type(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    id_type = callback.data.removeprefix("getid_")
    labels = {"user": "👤 человека", "group": "💬 группы", "channel": "📺 канала"}
    button_labels = {"user": "👤 Выбрать человека", "group": "💬 Выбрать группу", "channel": "📺 Выбрать канал"}
    hints = {
        "user": "Telegram откроет выбор пользователя. После подтверждения бот получит его ID.",
        "group": "Telegram откроет ваши группы. Выберите нужную группу и подтвердите отправку чата боту.",
        "channel": "Telegram откроет ваши каналы. Выберите нужный канал и подтвердите отправку чата боту.",
    }
    await state.set_state(GetID.waiting_forward)
    await state.update_data(id_type=id_type)
    await callback.message.edit_text(
        f"🔍 <b>Узнать ID {labels[id_type]}</b>\n\n"
        f"{hints[id_type]}\n\n"
        f"👇 Ниже появилась кнопка <b>{button_labels[id_type]}</b>.\n\n"
        "Резервно можно отправить сюда пересланное сообщение, @username или числовой ID.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К выбору типа", callback_data="adm_get_id")],
            [InlineKeyboardButton(text="⬅️ Панель", callback_data="adm_back_main")],
        ]),
        parse_mode="HTML",
    )
    await callback.message.answer(
        f"Нажмите кнопку ниже, чтобы выбрать {labels[id_type]} из списка Telegram:",
        reply_markup=getid_reply_keyboard(id_type),
        parse_mode="HTML",
    )
    await callback.answer()


async def _enrich_chat_shared(chat_id: int) -> dict:
    try:
        chat_info = await bot.get_chat(chat_id)
        return {
            "id": chat_info.id,
            "type": chat_info.type,
            "title": chat_info.title or chat_info.full_name or "—",
            "username": chat_info.username,
        }
    except Exception as e:
        await db.log_error("bot", str(e), context=f"getid_shared_chat chat_id={chat_id}")
        return {"id": chat_id, "type": "chat", "title": "—", "username": None}


def _chat_type_label(chat_type: str, request_id: int | None = None) -> str:
    if request_id == GETID_REQUEST_GROUP:
        return "💬 Группа"
    if request_id == GETID_REQUEST_CHANNEL:
        return "📺 Канал"
    return {
        "private": "👤 Пользователь",
        "group": "💬 Группа",
        "supergroup": "💬 Супергруппа",
        "channel": "📺 Канал",
    }.get(chat_type, "💬 Чат")


@router.message(F.chat_shared, F.chat.type == "private")
async def getid_chat_shared(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    shared = message.chat_shared
    request_id = getattr(shared, "request_id", None)
    chat_id = getattr(shared, "chat_id", None)
    if chat_id is None:
        await message.answer("❌ Telegram не передал ID чата.", reply_markup=ReplyKeyboardRemove())
        return

    info = await _enrich_chat_shared(chat_id)
    title = getattr(shared, "title", None) or info.get("title") or "—"
    username = getattr(shared, "username", None) or info.get("username")
    label = _chat_type_label(info.get("type", "chat"), request_id)

    await state.clear()
    await message.answer("✅ Чат получен.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "🔍 <b>Результат</b>\n\n"
        f"{label}\n"
        f"🆔 ID: <code>{chat_id}</code>\n"
        f"📛 Название: {html(title)}\n"
        f"📱 Username: @{html(username)}\n\n"
        "💡 Нажмите на ID, чтобы скопировать.",
        reply_markup=_getid_back_kb(),
        parse_mode="HTML",
    )


@router.message(F.users_shared, F.chat.type == "private")
async def getid_users_shared(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    shared = message.users_shared
    users = getattr(shared, "users", None) or []
    if not users:
        await message.answer("❌ Telegram не передал пользователя.", reply_markup=ReplyKeyboardRemove())
        return

    lines = ["🔍 <b>Результат</b>\n"]
    for u in users[:5]:
        user_id = getattr(u, "user_id", None)
        first_name = getattr(u, "first_name", None)
        last_name = getattr(u, "last_name", None)
        username = getattr(u, "username", None)
        full_name = " ".join(x for x in [first_name, last_name] if x) or "—"
        lines.append(
            "👤 <b>Пользователь</b>\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"📛 Имя: {html(full_name)}\n"
            f"📱 Username: @{html(username)}"
        )

    await state.clear()
    await message.answer("✅ Пользователь получен.", reply_markup=ReplyKeyboardRemove())
    await message.answer("\n\n".join(lines) + "\n\n💡 Нажмите на ID, чтобы скопировать.", reply_markup=_getid_back_kb(), parse_mode="HTML")


@router.message(F.user_shared, F.chat.type == "private")
async def getid_user_shared(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    shared = message.user_shared
    user_id = getattr(shared, "user_id", None)
    if user_id is None:
        await message.answer("❌ Telegram не передал ID пользователя.", reply_markup=ReplyKeyboardRemove())
        return

    await state.clear()
    await message.answer("✅ Пользователь получен.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "🔍 <b>Результат</b>\n\n"
        "👤 <b>Пользователь</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n\n"
        "💡 Нажмите на ID, чтобы скопировать.",
        reply_markup=_getid_back_kb(),
        parse_mode="HTML",
    )


@router.message(GetID.waiting_forward, F.chat.type == "private")
async def fsm_get_id_forward(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    results = []

    # Try forwarded message first
    origin = message.forward_origin
    if origin:
        otype = origin.type if hasattr(origin, "type") else ""
        if hasattr(origin, "sender_user") and origin.sender_user:
            u = origin.sender_user
            results.append(f"👤 <b>Пользователь</b>\n🆔 <code>{u.id}</code>\n📛 {html(u.full_name)}\n📱 @{html(u.username)}")
        if hasattr(origin, "sender_chat") and origin.sender_chat:
            c = origin.sender_chat
            t = {"group": "💬 Группа", "supergroup": "💬 Группа", "channel": "📺 Канал"}.get(c.type, "💬")
            results.append(f"{t}\n🆔 <code>{c.id}</code>\n📛 {html(c.title or '—')}\n📱 @{html(c.username)}")
        if otype == "channel" and hasattr(origin, "chat") and origin.chat:
            c = origin.chat
            results.append(f"📺 <b>Канал</b>\n🆔 <code>{c.id}</code>\n📛 {html(c.title or '—')}\n📱 @{html(c.username)}")
        if otype == "hidden_user":
            results.append("⚠️ Пользователь скрыл профиль при пересылке.")
    if not results and message.forward_from:
        u = message.forward_from
        results.append(f"👤 <b>Пользователь</b>\n🆔 <code>{u.id}</code>\n📛 {html(u.full_name)}\n📱 @{html(u.username)}")
    if not results and message.forward_from_chat:
        c = message.forward_from_chat
        t = {"group": "💬 Группа", "supergroup": "💬 Группа", "channel": "📺 Канал"}.get(c.type, "💬")
        results.append(f"{t}\n🆔 <code>{c.id}</code>\n📛 {html(c.title or '—')}\n📱 @{html(c.username)}")

    # If not forwarded, try @username or numeric ID
    if not results and message.text:
        text = message.text.strip()
        username = text.lstrip("@") if text.startswith("@") else None
        if not username and text.lstrip("-").isdigit():
            try:
                chat_info = await bot.get_chat(int(text))
                t = {"group": "💬 Группа", "supergroup": "💬 Группа", "channel": "📺 Канал", "private": "👤 Пользователь"}.get(chat_info.type, "💬")
                name = chat_info.title or chat_info.full_name or "—"
                results.append(f"{t}\n🆔 <code>{chat_info.id}</code>\n📛 {html(name)}\n📱 @{html(chat_info.username)}")
            except Exception as e:
                await db.log_error("bot", str(e), context=f"getid numeric {text}")
                results.append(f"❌ Не удалось найти чат с ID <code>{html(text)}</code>")
        elif username:
            try:
                chat_info = await bot.get_chat(f"@{username}")
                t = {"group": "💬 Группа", "supergroup": "💬 Группа", "channel": "📺 Канал", "private": "👤 Пользователь"}.get(chat_info.type, "💬")
                name = chat_info.title or chat_info.full_name or "—"
                results.append(f"{t}\n🆔 <code>{chat_info.id}</code>\n📛 {html(name)}\n📱 @{html(chat_info.username)}")
            except Exception as e:
                await db.log_error("bot", str(e), context=f"getid username @{username}")
                results.append(f"❌ Не найден: @{html(username)}\n\n💡 Бот может найти только публичные каналы/группы по @username.\nДля приватных используйте кнопку выбора Telegram или добавьте бота туда и отправьте /chatid")

    if not results:
        await message.answer(
            "❌ Не удалось определить ID.\n\n"
            "Попробуйте:\n"
            "• Нажать кнопку выбора Telegram ниже\n"
            "• Переслать сообщение\n"
            "• Отправить @username\n"
            "• Добавить бота в чат → /chatid",
            reply_markup=cancel_kb(), parse_mode="HTML",
        )
        return

    await state.clear()
    await message.answer("✅ Готово.", reply_markup=ReplyKeyboardRemove())
    await message.answer("🔍 <b>Результат</b>\n\n" + "\n\n".join(results) + "\n\n💡 Нажмите на ID чтобы скопировать", reply_markup=_getid_back_kb(), parse_mode="HTML")



# ══════════════════════════════════════════════════════════════════════════════
#  FAQ / SUPPORT MENU
# ══════════════════════════════════════════════════════════════════════════════

SUPPORT_REASON_LABELS = {
    "payment": "💳 Проблема с оплатой",
    "link": "🔗 Не работает ссылка",
    "order": "📦 Вопрос по заказу",
    "other": "🧑‍💻 Другое",
}

FAQ_TEXTS = {
    "pay": (
        "💳 <b>Как оплатить?</b>\n\n"
        "1. Выберите раздел и товар.\n"
        "2. Нажмите удобный способ оплаты.\n"
        "3. Если это перевод на карту или Robokassa с ручной проверкой — после оплаты нажмите «Я оплатил(а)».\n"
        "4. Админ проверит оплату и бот отправит доступ."
    ),
    "link": (
        "🔗 <b>Где ссылка?</b>\n\n"
        "Ссылка приходит в личные сообщения после подтверждения оплаты.\n"
        "Также откройте <b>📋 Мои заказы</b> → нужный заказ → <b>Получить доступ повторно</b>, если заказ уже подтверждён."
    ),
    "link_problem": (
        "⚠️ <b>Ссылка не открывается</b>\n\n"
        "Проверьте, что вы открываете ссылку из того же Telegram-аккаунта.\n"
        "Если ссылка была одноразовая или срок доступа истёк — откройте заказ и нажмите <b>Получить доступ повторно</b>.\n"
        "Если не помогло — напишите в поддержку через кнопку ниже."
    ),
    "time": (
        "⏳ <b>Сколько ждать подтверждение?</b>\n\n"
        "Обычно проверка занимает до 30 минут.\n"
        "Если оплатили с другого имени, карты или аккаунта — напишите в поддержку и укажите номер заказа."
    ),
    "support": (
        "🆘 <b>Как написать поддержке?</b>\n\n"
        "Нажмите <b>🆘 Поддержка</b> или кнопку ниже, выберите тему и отправьте сообщение.\n"
        "Бот создаст тикет для админов, и ответ придёт сюда в личный чат."
    ),
}


def support_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Проблема с оплатой", callback_data="support_reason_payment")],
        [InlineKeyboardButton(text="🔗 Не работает ссылка", callback_data="support_reason_link")],
        [InlineKeyboardButton(text="📦 Вопрос по заказу", callback_data="support_reason_order")],
        [InlineKeyboardButton(text="🧑‍💻 Другое", callback_data="support_reason_other")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")],
    ])


def faq_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Как оплатить", callback_data="faq_pay")],
        [InlineKeyboardButton(text="🔗 Где ссылка", callback_data="faq_link")],
        [InlineKeyboardButton(text="⚠️ Ссылка не открывается", callback_data="faq_link_problem")],
        [InlineKeyboardButton(text="⏳ Сколько ждать", callback_data="faq_time")],
        [InlineKeyboardButton(text="🆘 Написать поддержку", callback_data="faq_support")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")],
    ])


async def _show_support_menu(message: Message, edit: bool = True):
    contacts = await get_support_contacts()
    lines = [
        "🆘 <b>Поддержка</b>",
        "Выберите тему обращения — так админы быстрее поймут, что случилось.",
    ]
    if contacts:
        lines.append("\n<b>Контакты:</b>")
        for c in contacts:
            lines.append(f"• {html(c.get('name', '?'))}: {html(c.get('username', '?'))}")
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=support_menu_kb(), parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=support_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "faq_menu")
async def cb_faq_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❓ <b>Помощь</b>\n\nВыберите вопрос:",
        reply_markup=faq_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("faq_"))
async def cb_faq_item(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    key = callback.data.removeprefix("faq_")
    if key == "menu":
        await cb_faq_menu(callback, state)
        return
    if key == "support":
        await _show_support_menu(callback.message)
        await callback.answer()
        return
    text = FAQ_TEXTS.get(key)
    if not text:
        await callback.answer("Раздел не найден", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆘 Написать поддержку", callback_data="faq_support")],
        [InlineKeyboardButton(text="⬅️ К вопросам", callback_data="faq_menu")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("support_reason_"))
async def cb_support_reason(callback: CallbackQuery, state: FSMContext):
    reason = callback.data.removeprefix("support_reason_")
    label = SUPPORT_REASON_LABELS.get(reason)
    if not label:
        await callback.answer("Тема не найдена", show_alert=True)
        return
    await state.set_state(SupportRequest.waiting_message)
    await state.update_data(support_reason=reason)
    await callback.message.edit_text(
        f"{label}\n\n"
        "Опишите проблему одним сообщением.\n"
        "Если вопрос по заказу — укажите номер заказа.\n\n"
        "Например: <code>Заказ #12, оплатил с другой карты, доступ не пришёл.</code>",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(SupportRequest.waiting_message, F.chat.type == "private")
async def fsm_support_message(message: Message, state: FSMContext):
    if await is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    reason = data.get("support_reason", "other")
    label = SUPPORT_REASON_LABELS.get(reason, SUPPORT_REASON_LABELS["other"])
    await db.add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    text = message.text or message.caption or "(без текста)"
    ticket_text = (
        f"🆘 <b>Обращение в поддержку</b>\n"
        f"🏷 Тема: <b>{html(label)}</b>\n\n"
        f"{html(text)}"
    )
    await forward_to_group(message.from_user.id, message.from_user.full_name, message.from_user.username, ticket_text)
    await state.clear()
    await message.answer(
        "✅ Обращение отправлено. Администратор ответит здесь в личном чате.",
        reply_markup=back_to_main_kb(), parse_mode="HTML",
    )



@router.message(AdminSearch.waiting_query, F.text, F.chat.type == "private")
async def fsm_admin_search_query(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    query = message.text.strip()
    await state.clear()
    await _send_admin_search_results(message, query)


@router.message(AdminMessage.waiting_text, F.text, F.chat.type == "private")
async def fsm_admin_message_to_user(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    target_user_id = int(data.get("target_user_id", 0))
    await state.clear()
    if not target_user_id:
        await message.answer("❌ Пользователь не выбран.", reply_markup=admin_menu_kb(), parse_mode="HTML")
        return
    text = message.text.strip()
    try:
        await bot.send_message(target_user_id, f"💬 <b>Сообщение от администратора:</b>\n\n{html(text)}", parse_mode="HTML")
        await message.answer(f"✅ Сообщение отправлено пользователю <code>{target_user_id}</code>.", reply_markup=admin_menu_kb(), parse_mode="HTML")
        await log_admin_event(message.from_user, "Отправил сообщение пользователю", f"user_id={target_user_id}")
    except Exception as e:
        await db.log_error("send_message", str(e), user_id=target_user_id, context="admin_message_to_user")
        await message.answer(f"❌ Не удалось отправить сообщение: <code>{html(e)}</code>", reply_markup=admin_menu_kb(), parse_mode="HTML")

# ══════════════════════════════════════════════════════════════════════════════
#  PRIVATE MESSAGES → group
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.photo, F.chat.type == "private")
async def user_photo_handler(message: Message):
    if await is_admin(message.from_user.id):
        return
    await db.add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await forward_photo_to_group(message.from_user.id, message.from_user.full_name, message.from_user.username, message.photo[-1].file_id, message.caption)
    await message.answer("✅ Отправлено. Ожидайте ответа!")


@router.message(F.text, F.chat.type == "private", lambda msg: not msg.text.startswith("/"))
async def user_text_handler(message: Message):
    if await is_admin(message.from_user.id):
        return
    await db.add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await forward_to_group(message.from_user.id, message.from_user.full_name, message.from_user.username, message.text)
    await message.answer("✅ Отправлено администратору!")


# ══════════════════════════════════════════════════════════════════════════════
#  USER FLOW CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    welcome = await S("welcome_message", "📌 <b>Главное меню</b>")
    await callback.message.edit_text(welcome, reply_markup=await main_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("cat_"))
async def cb_category(callback: CallbackQuery):
    cat_id_str = callback.data.removeprefix("cat_")
    if not cat_id_str.isdigit():
        await callback.answer("Ошибка", show_alert=True)
        return
    cat_id = int(cat_id_str)
    cat = await db.get_category(cat_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    products = await db.get_active_products(cat_id)
    if not products:
        # Support category gets a separate menu with themes. Other empty categories stay compact.
        if "поддерж" in (cat.get("name") or "").lower():
            await _show_support_menu(callback.message)
        else:
            contacts = await get_support_contacts()
            lines = [f"{cat['emoji']} <b>{cat['name']}</b>"]
            desc = (cat.get("description") or "").strip()
            if desc:
                lines.append(f"📝 {desc}")
            if contacts:
                lines.append("🆘 <b>Контакты:</b>")
                for c in contacts:
                    lines.append(f"• {html(c.get('name', '?'))}: {html(c.get('username', '?'))}")
            lines.append("✍️ Напишите сообщение — мы получим его!")
            await callback.message.edit_text("\n".join(lines), reply_markup=back_to_main_kb(), parse_mode="HTML")
    else:
        desc = f"\n\n{cat['description']}" if cat["description"] else ""
        await callback.message.edit_text(
            f"{cat['emoji']} <b>{cat['name']}</b>{desc}\n\nВыберите:",
            reply_markup=await products_in_category_kb(cat_id), parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("sub_"))
async def cb_subcategory(callback: CallbackQuery):
    pid = callback.data.removeprefix("sub_")
    if not pid.isdigit():
        await callback.answer("Ошибка", show_alert=True)
        return
    product = await db.get_product(int(pid))
    if not product or not product["active"]:
        await callback.answer("Не найден", show_alert=True)
        return
    rate = await get_stars_rate()
    stars = rub_to_stars(product["price"], rate)
    await callback.message.edit_text(
        f"{product['name']}\n\n📝 {product['description']}\n\n💰 <b>{product['price']}₽</b> ({stars}⭐)\n\nСпособ оплаты:",
        reply_markup=await payment_method_kb(product["id"], product["price"], product.get("category_id", 0)),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Stars ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_stars_"))
async def cb_pay_stars(callback: CallbackQuery):
    pid = int(callback.data.removeprefix("pay_stars_"))
    product = await db.get_product(pid)
    if not product:
        await callback.answer("Ошибка", show_alert=True)
        return
    order_id = await db.create_order(callback.from_user.id, callback.from_user.username, str(pid), product["price"], "stars")
    rate = await get_stars_rate()
    stars = rub_to_stars(product["price"], rate)
    try:
        await callback.message.delete()
    except Exception:
        pass
    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id, title=product["name"], description=f"Доступ: {product['name']}",
            payload=f"order_{order_id}_stars", provider_token="", currency="XTR",
            prices=[LabeledPrice(label=product["name"], amount=stars)],
        )
    except Exception as e:
        await db.log_error("payment", str(e), user_id=callback.from_user.id, order_id=order_id, context="send_invoice_stars")
        await callback.message.answer("❌ Не удалось создать оплату Stars. Попробуйте позже или напишите в поддержку.", reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("pay_yookassa_"))
async def cb_pay_yookassa(callback: CallbackQuery):
    pid = int(callback.data.removeprefix("pay_yookassa_"))
    product = await db.get_product(pid)
    if not product:
        await callback.answer("Ошибка", show_alert=True)
        return
    token = await S("yookassa_token")
    if not token:
        await callback.answer("ЮKassa не настроена", show_alert=True)
        return
    order_id = await db.create_order(callback.from_user.id, callback.from_user.username, str(pid), product["price"], "yookassa")
    try:
        await callback.message.delete()
    except Exception:
        pass
    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id, title=product["name"], description=f"Доступ: {product['name']}",
            payload=f"order_{order_id}_yookassa", provider_token=token, currency="RUB",
            prices=[LabeledPrice(label=product["name"], amount=product["price"] * 100)],
        )
    except Exception as e:
        await db.log_error("payment", str(e), user_id=callback.from_user.id, order_id=order_id, context="send_invoice_yookassa")
        await callback.message.answer("❌ Не удалось создать оплату ЮKassa. Попробуйте позже или напишите в поддержку.", reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("pay_crypto_"))
async def cb_pay_crypto(callback: CallbackQuery):
    pid = int(callback.data.removeprefix("pay_crypto_"))
    product = await db.get_product(pid)
    if not product:
        await callback.answer("Ошибка", show_alert=True)
        return
    client = await get_crypto_client()
    if not client:
        await callback.answer("CryptoBot не настроен", show_alert=True)
        return
    order_id = await db.create_order(callback.from_user.id, callback.from_user.username, str(pid), product["price"], "cryptobot")
    try:
        invoice = await client.create_invoice(amount=product["price"], fiat="RUB", currency_type="fiat", description=f"#{order_id}: {product['name']}", payload=str(order_id))
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Оплатить", url=invoice.bot_invoice_url)],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_crypto_{order_id}_{invoice.invoice_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
        ])
        await callback.message.edit_text(f"🪙 <b>CryptoBot</b>\n\n📦 #{order_id} | {product['name']} | {product['price']}₽\n\nОплатите и нажмите «Я оплатил».", reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await db.log_error("payment", str(e), user_id=callback.from_user.id, order_id=order_id, context="create_crypto_invoice")
        await callback.message.edit_text(f"❌ CryptoBot: {e}", reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("check_crypto_"))
async def cb_check_crypto(callback: CallbackQuery):
    parts = callback.data.removeprefix("check_crypto_").split("_")
    if len(parts) < 2:
        await callback.answer("Ошибка", show_alert=True)
        return
    order_id, invoice_id = int(parts[0]), int(parts[1])
    client = await get_crypto_client()
    if not client:
        await callback.answer("Недоступен", show_alert=True)
        return
    try:
        invoices = await client.get_invoices(invoice_ids=invoice_id)
        if invoices and invoices.status == "paid":
            await auto_confirm_order(order_id, "🪙 CryptoBot")
            await callback.message.edit_text("✅ Оплачено!", reply_markup=back_to_main_kb())
        else:
            await callback.answer("⏳ Ещё не оплачено", show_alert=True)
    except Exception as e:
        await db.log_error("payment", str(e), user_id=callback.from_user.id, order_id=order_id, context="check_crypto_invoice")
        await callback.answer(f"Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("pay_robokassa_"))
async def cb_pay_robokassa(callback: CallbackQuery):
    pid = int(callback.data.removeprefix("pay_robokassa_"))
    product = await db.get_product(pid)
    if not product:
        await callback.answer("Ошибка", show_alert=True)
        return
    merchant = await S("robokassa_login")
    if not merchant:
        await callback.answer("Robokassa не настроена", show_alert=True)
        return
    order_id = await db.create_order(callback.from_user.id, callback.from_user.username, str(pid), product["price"], "robokassa")
    password1 = await S("robokassa_password1")
    amount = f"{product['price']:.2f}"
    sig = hashlib.md5(f"{merchant}:{amount}:{order_id}:{password1}".encode()).hexdigest()
    test = "&IsTest=1" if await S("robokassa_test", "1") == "1" else ""
    url = f"https://auth.robokassa.ru/Merchant/Index.aspx?MerchantLogin={merchant}&OutSum={amount}&InvId={order_id}&SignatureValue={sig}{test}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=url)],
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_manual_{order_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])
    await callback.message.edit_text(f"🏦 <b>Robokassa</b>\n\n📦 #{order_id} | {product['name']} | {product['price']}₽", reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("pay_card_"))
async def cb_pay_card(callback: CallbackQuery):
    pid = int(callback.data.removeprefix("pay_card_"))
    product = await db.get_product(pid)
    if not product:
        await callback.answer("Ошибка", show_alert=True)
        return
    order_id = await db.create_order(callback.from_user.id, callback.from_user.username, str(pid), product["price"], "карта")
    card = await S("payment_card", "—")
    name = await S("payment_name", "—")
    method = await S("payment_method", "—")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_manual_{order_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])
    await callback.message.edit_text(
        f"💳 <b>Перевод на карту</b>\n\n📦 #{order_id} | {product['name']} | {product['price']}₽\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n💳 <code>{card}</code>\n👤 {name}\n💳 {method}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 В комментарии: <code>{callback.from_user.id}</code>",
        reply_markup=kb, parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("paid_manual_"))
async def cb_paid_manual(callback: CallbackQuery):
    order_id = int(callback.data.removeprefix("paid_manual_"))
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Не найден", show_alert=True)
        return
    product = await db.get_product(int(order["subcategory"])) if order["subcategory"].isdigit() else None
    sub_name = product["name"] if product else order["subcategory"]
    await callback.message.edit_text(
        f"⏳ <b>Заявка отправлена!</b>\n\n"
        f"📦 Заказ #{order_id} | {sub_name}\n\n"
        "Обычно проверка занимает до 30 минут.\n"
        "Если оплатили с другого имени, карты или аккаунта — напишите в поддержку и укажите номер заказа.",
        reply_markup=back_to_main_kb(), parse_mode="HTML",
    )
    await callback.answer()
    await notify_admins(
        f"🔔 <b>Заказ!</b>\n\n📦 #{order_id}\n👤 {callback.from_user.full_name} | <code>{callback.from_user.id}</code>\n📚 {sub_name} | 💰 {order['price']}₽ | 💳 {order.get('payment_method','карта')}",
        reply_markup=admin_order_kb(order_id),
    )
    topic_id = await get_or_create_topic(callback.from_user.id, callback.from_user.full_name, callback.from_user.username)
    group_id = await get_ticket_group_id()
    if topic_id:
        try:
            await bot.send_message(chat_id=group_id, message_thread_id=topic_id, text=f"🔔 #{order_id} | {sub_name} | {order['price']}₽ | ⏳", reply_markup=admin_order_kb(order_id), parse_mode="HTML")
        except Exception as e:
            await db.log_error("send_message", str(e), user_id=callback.from_user.id, order_id=order_id, context="manual_payment_topic")


# ─── Confirm / Reject ────────────────────────────────────────────────────────

async def _confirm_and_notify(order_id: int, order: dict, source):
    await db.confirm_order(order_id)
    product = await db.get_product(int(order["subcategory"])) if order["subcategory"].isdigit() else None
    if isinstance(source, CallbackQuery):
        await source.message.edit_text(f"✅ #{order_id} подтверждён!", parse_mode="HTML")
        await source.answer("Подтверждено!")
    else:
        await source.answer(f"✅ #{order_id} подтверждён!", parse_mode="HTML")
    if product:
        invite_link = await generate_invite_link(product)
        await db.save_order_invite_link(order_id, invite_link)
        try:
            await bot.send_message(
                order["user_id"],
                f"🎉 <b>Оплата подтверждена!</b>\n\n📦 #{order_id} | {product['name']}\n\n"
                f"🔗 Ссылка (одноразовая):\n{invite_link}\n\n⚠️ Работает 1 раз!\nЕсли потеряете доступ — нажмите «Получить доступ повторно» в заказах.\nСпасибо! 🎓",
                reply_markup=back_to_main_kb(), parse_mode="HTML",
            )
        except Exception as e:
            await db.log_error("send_message", str(e), user_id=order["user_id"], order_id=order_id, context="confirm_order_notify_user")


async def _reject_and_notify(order_id: int, order: dict, source):
    await db.reject_order(order_id)
    product = await db.get_product(int(order["subcategory"])) if order["subcategory"].isdigit() else None
    sub_name = product["name"] if product else order["subcategory"]
    if isinstance(source, CallbackQuery):
        await source.message.edit_text(f"❌ #{order_id} отклонён.", parse_mode="HTML")
        await source.answer("Отклонено")
    else:
        await source.answer(f"❌ #{order_id} отклонён.", parse_mode="HTML")
    try:
        await bot.send_message(order["user_id"], f"❌ <b>Заказ #{order_id} отклонён</b>\n\n{sub_name}\n\nСвяжитесь с поддержкой.", reply_markup=back_to_main_kb(), parse_mode="HTML")
    except Exception as e:
        await db.log_error("send_message", str(e), user_id=order["user_id"], order_id=order_id, context="reject_order_notify_user")


@router.callback_query(F.data.startswith("confirm_"))
async def cb_confirm(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Только для админов", show_alert=True)
        return
    order_id = int(callback.data.removeprefix("confirm_"))
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Не найден", show_alert=True)
        return
    if order["status"] != "pending":
        await callback.answer("Уже обработан", show_alert=True)
        return
    await _confirm_and_notify(order_id, order, callback)


@router.callback_query(F.data.startswith("reject_"))
async def cb_reject(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Только для админов", show_alert=True)
        return
    order_id = int(callback.data.removeprefix("reject_"))
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Не найден", show_alert=True)
        return
    if order["status"] != "pending":
        await callback.answer("Уже обработан", show_alert=True)
        return
    await _reject_and_notify(order_id, order, callback)


STATUS_LABELS = {"pending": "⏳ ожидает", "confirmed": "✅ подтверждён", "rejected": "❌ отклонён", "cancelled": "🚫 отменён"}
STATUS_EMOJI = {"pending": "⏳", "confirmed": "✅", "rejected": "❌", "cancelled": "🚫"}


def order_method_label(method: str | None) -> str:
    labels = {
        "карта": "💳 Перевод на карту",
        "stars": "⭐ Telegram Stars",
        "yookassa": "💳 ЮKassa",
        "cryptobot": "🪙 CryptoBot",
        "robokassa": "🏦 Robokassa",
    }
    return labels.get(method or "", method or "—")


async def product_name_for_order(order: dict) -> str:
    product = await db.get_product(int(order["subcategory"])) if str(order.get("subcategory", "")).isdigit() else None
    return product["name"] if product else str(order.get("subcategory") or "—")


async def buyer_watermark_text(user_id: int, username: str | None, order_id: int | None = None) -> str:
    if await S("watermark_enabled", "1") != "1":
        return ""
    project = await S("watermark_project_name", "Edu Store")
    uname = f"@{username}" if username else "—"
    today = datetime.now().strftime("%d.%m.%Y")
    order_part = f"\n📦 Заказ: #{order_id}" if order_id else ""
    return (
        "\n\n🏷 <b>Ваш персональный водяной знак</b>"
        f"\nПроект: <b>{html(project)}</b>"
        f"\nПокупатель: <code>{user_id}</code> | {html(uname)}"
        f"{order_part}"
        f"\nДата: <code>{today}</code>"
    )


@router.callback_query(F.data == "my_orders")
async def cb_my_orders(callback: CallbackQuery):
    orders = await db.get_user_orders(callback.from_user.id)
    if not orders:
        await callback.message.edit_text("📋 Заказов нет.", reply_markup=back_to_main_kb(), parse_mode="HTML")
        await callback.answer()
        return
    lines = [
        "📋 <b>Мои заказы</b>",
        "Нажмите на заказ, чтобы открыть подробности, статус и повторную выдачу доступа.",
    ]
    buttons = []
    for o in orders[:15]:
        sub_name = await product_name_for_order(o)
        status = STATUS_EMOJI.get(o["status"], "❓")
        buttons.append([InlineKeyboardButton(
            text=f"{status} #{o['id']} • {sub_name[:28]} • {o['price']}₽",
            callback_data=f"my_order_{o['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("my_order_"))
async def cb_my_order_detail(callback: CallbackQuery):
    order_id = int(callback.data.removeprefix("my_order_"))
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    sub_name = await product_name_for_order(order)
    created = order.get("created_at") or "—"
    confirmed = order.get("confirmed_at") or "—"
    status = STATUS_LABELS.get(order["status"], "❓ неизвестно")
    method = order_method_label(order.get("payment_method"))
    lines = [
        f"📦 <b>Заказ #{order['id']}</b>",
        f"📚 Товар: <b>{html(sub_name)}</b>",
        f"💰 Цена: <b>{order['price']}₽</b>",
        f"💳 Оплата: {html(method)}",
        f"📌 Статус: <b>{status}</b>",
        f"🗓 Создан: <code>{created}</code>",
        f"✅ Подтверждён: <code>{confirmed}</code>",
    ]
    if order.get("access_reissued_count") is not None:
        lines.append(f"🔁 Повторных выдач: <b>{order.get('access_reissued_count', 0)}</b>")
    buttons = []
    if order["status"] == "confirmed":
        buttons.append([InlineKeyboardButton(text="🔁 Получить доступ повторно", callback_data=f"access_again_{order_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ К моим заказам", callback_data="my_orders")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


# ─── Admin panel callbacks ───────────────────────────────────────────────────

@router.callback_query(F.data == "adm_pending")
async def cb_adm_pending(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    orders = await db.get_pending_orders()
    if not orders:
        await callback.message.edit_text("📦 Нет ожидающих.", reply_markup=admin_menu_kb(), parse_mode="HTML")
        return
    await callback.message.edit_text(f"📦 <b>Ожидающие ({len(orders)})</b>", parse_mode="HTML")
    for o in orders:
        product = await db.get_product(int(o["subcategory"])) if o["subcategory"].isdigit() else None
        sub_name = product["name"] if product else o["subcategory"]
        await callback.message.answer(f"📦 #{o['id']} | <code>{o['user_id']}</code> | {sub_name} | {o['price']}₽", reply_markup=admin_order_kb(o["id"]), parse_mode="HTML")


@router.callback_query(F.data == "adm_stats")
async def cb_adm_stats(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    await _send_stats(callback.message, edit=True)


ORDER_FILTERS = {
    "all": {"title": "Все заказы", "status": None, "methods": None},
    "pending": {"title": "Ожидают", "status": "pending", "methods": None},
    "confirmed": {"title": "Подтверждённые", "status": "confirmed", "methods": None},
    "rejected": {"title": "Отклонённые", "status": "rejected", "methods": None},
    "card": {"title": "Карта", "status": None, "methods": ["карта", "yookassa"]},
    "stars": {"title": "Stars", "status": None, "methods": ["stars"]},
    "crypto": {"title": "CryptoBot", "status": None, "methods": ["cryptobot"]},
    "robo": {"title": "Robokassa", "status": None, "methods": ["robokassa"]},
}


def admin_orders_filter_kb(active: str = "all") -> InlineKeyboardMarkup:
    def mark(key: str, title: str) -> str:
        return f"✅ {title}" if active == key else title
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=mark("all", "📋 Все"), callback_data="adm_orders_filter_all")],
        [InlineKeyboardButton(text=mark("pending", "⏳ Ожидают"), callback_data="adm_orders_filter_pending"),
         InlineKeyboardButton(text=mark("confirmed", "✅ Подтверждённые"), callback_data="adm_orders_filter_confirmed")],
        [InlineKeyboardButton(text=mark("rejected", "❌ Отклонённые"), callback_data="adm_orders_filter_rejected")],
        [InlineKeyboardButton(text=mark("card", "💳 Карта"), callback_data="adm_orders_filter_card"),
         InlineKeyboardButton(text=mark("stars", "⭐ Stars"), callback_data="adm_orders_filter_stars")],
        [InlineKeyboardButton(text=mark("crypto", "🪙 Crypto"), callback_data="adm_orders_filter_crypto"),
         InlineKeyboardButton(text=mark("robo", "🏦 Robokassa"), callback_data="adm_orders_filter_robo")],
        [InlineKeyboardButton(text="🔎 Поиск", callback_data="adm_search")],
        [InlineKeyboardButton(text="⬅️ Панель", callback_data="adm_back_main")],
    ])


async def _show_admin_orders(message: Message, filter_key: str = "all", edit: bool = True):
    data = ORDER_FILTERS.get(filter_key, ORDER_FILTERS["all"])
    orders = await db.get_orders_filtered(20, status=data["status"], payment_methods=data["methods"])
    lines = [f"📋 <b>Заказы — {html(data['title'])}</b>", "Нажмите на заказ, чтобы открыть карточку."]
    buttons = []
    if not orders:
        lines.append("\nНет заказов по этому фильтру.")
    for o in orders:
        sub_name = await product_name_for_order(o)
        status = STATUS_EMOJI.get(o["status"], "❓")
        method = order_method_label(o.get("payment_method"))
        lines.append(f"\n{status} <b>#{o['id']}</b> | <code>{o['user_id']}</code> | {html(sub_name)} | {o['price']}₽ | {html(method)}")
        buttons.append([InlineKeyboardButton(text=f"{status} #{o['id']} • {sub_name[:28]}", callback_data=f"adm_order_{o['id']}")])
    # Keep filter buttons at the bottom, after clickable order cards.
    buttons.extend(admin_orders_filter_kb(filter_key).inline_keyboard)
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


async def _show_admin_order_card(message: Message, order_id: int, edit: bool = True):
    order = await db.get_order(order_id)
    if not order:
        text = f"❌ Заказ #{order_id} не найден."
        if edit:
            try:
                await message.edit_text(text, reply_markup=admin_menu_kb(), parse_mode="HTML")
                return
            except Exception:
                pass
        await message.answer(text, reply_markup=admin_menu_kb(), parse_mode="HTML")
        return
    sub_name = await product_name_for_order(order)
    user = await db.get_user(order["user_id"])
    lines = [
        f"📦 <b>Заказ #{order['id']}</b>",
        f"👤 Пользователь: <code>{order['user_id']}</code> | @{html((user or {}).get('username') or order.get('username') or '—')}",
        f"📛 Имя: {html((user or {}).get('full_name') or '—')}",
        f"📚 Товар: <b>{html(sub_name)}</b>",
        f"💰 Цена: <b>{order['price']}₽</b>",
        f"💳 Оплата: {html(order_method_label(order.get('payment_method')))}",
        f"📌 Статус: <b>{STATUS_LABELS.get(order['status'], order['status'])}</b>",
        f"🗓 Создан: <code>{order.get('created_at') or '—'}</code>",
        f"✅ Подтверждён: <code>{order.get('confirmed_at') or '—'}</code>",
        f"🔁 Повторных выдач: <b>{order.get('access_reissued_count', 0)}</b>",
    ]
    buttons = []
    if order["status"] == "pending":
        buttons.append([
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{order_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order_id}"),
        ])
    buttons.append([InlineKeyboardButton(text="👤 Карточка пользователя", callback_data=f"adm_user_{order['user_id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Все заказы", callback_data="adm_all_orders")])
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data == "adm_all_orders")
async def cb_adm_all_orders(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    await _show_admin_orders(callback.message, "all")


@router.callback_query(F.data.startswith("adm_orders_filter_"))
async def cb_adm_orders_filter(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    key = callback.data.removeprefix("adm_orders_filter_")
    await _show_admin_orders(callback.message, key)
    await callback.answer()


@router.callback_query(F.data.startswith("adm_order_"))
async def cb_adm_order_card(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    order_id = int(callback.data.removeprefix("adm_order_"))
    await _show_admin_order_card(callback.message, order_id)
    await callback.answer()


@router.callback_query(F.data == "adm_search")
async def cb_adm_search(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.set_state(AdminSearch.waiting_query)
    await callback.message.edit_text(
        "🔎 <b>Поиск</b>\n\n"
        "Введите ID заказа, ID пользователя, @username или название товара.",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )
    await callback.answer()


async def _send_admin_search_results(message: Message, query: str):
    if not query:
        await message.answer("❌ Пустой запрос.", reply_markup=admin_menu_kb(), parse_mode="HTML")
        return
    result = await db.search_admin_items(query, limit=10)
    orders = result.get("orders", [])
    users = result.get("users", [])
    lines = [f"🔎 <b>Результаты поиска:</b> <code>{html(query)}</code>"]
    buttons = []
    if users:
        lines.append("\n👥 <b>Пользователи:</b>")
        for u in users:
            lines.append(f"• <code>{u['user_id']}</code> | @{html(u.get('username') or '—')} | {html(u.get('full_name') or '—')}")
            uname = u.get("username")
            dm_url = f"https://t.me/{uname}" if uname else f"tg://user?id={u['user_id']}"
            buttons.append([
                InlineKeyboardButton(text=f"👤 {u.get('full_name') or u['user_id']}", callback_data=f"adm_user_{u['user_id']}"),
                InlineKeyboardButton(text="💬", url=dm_url),
            ])
    if orders:
        lines.append("\n📦 <b>Заказы:</b>")
        for o in orders:
            sub_name = await product_name_for_order(o)
            status = STATUS_EMOJI.get(o["status"], "❓")
            lines.append(f"• {status} <b>#{o['id']}</b> | <code>{o['user_id']}</code> | {html(sub_name)} | {o['price']}₽")
            buttons.append([InlineKeyboardButton(text=f"📦 Заказ #{o['id']}", callback_data=f"adm_order_{o['id']}")])
    if not users and not orders:
        lines.append("\nНичего не найдено.")
    buttons.append([InlineKeyboardButton(text="🔎 Новый поиск", callback_data="adm_search")])
    buttons.append([InlineKeyboardButton(text="⬅️ Панель", callback_data="adm_back_main")])
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


async def _show_admin_user_card(message: Message, user_id: int, edit: bool = True):
    user = await db.get_user(user_id)
    stats = await db.get_user_order_stats(user_id)
    security = await db.get_user_security(user_id)
    is_banned = bool(security and security.get("is_banned"))
    orders = await db.get_user_orders(user_id)
    lines = [
        f"👤 <b>Карточка пользователя</b>",
        f"🆔 ID: <code>{user_id}</code>",
        f"📱 Username: @{html((user or {}).get('username') or '—')}",
        f"📛 Имя: {html((user or {}).get('full_name') or '—')}",
        f"🗓 Регистрация: <code>{html((user or {}).get('joined_at') or '—')}</code>",
        f"🚫 Бан: {'да' if is_banned else 'нет'}",
        "\n📊 <b>Заказы:</b>",
        f"Всего: <b>{stats['total']}</b> | ✅ {stats['confirmed']} | ⏳ {stats['pending']} | ❌ {stats['rejected']}",
        f"💰 Подтверждено на сумму: <b>{stats['revenue']}₽</b>",
    ]
    if is_banned:
        lines.append(f"Причина: {html(security.get('ban_reason') or 'без причины')}")
    if orders:
        lines.append("\n🧾 <b>Последние заказы:</b>")
        for o in orders[:5]:
            sub_name = await product_name_for_order(o)
            lines.append(f"• {STATUS_EMOJI.get(o['status'], '❓')} #{o['id']} | {html(sub_name)} | {o['price']}₽")
    username = (user or {}).get("username")
    if username:
        dm_url = f"https://t.me/{username}"
    else:
        dm_url = f"tg://user?id={user_id}"
    buttons = [
        [InlineKeyboardButton(text="💬 Личное сообщение", url=dm_url)],
        [InlineKeyboardButton(text="✉️ Написать от бота", callback_data=f"adm_user_write_{user_id}"),
         InlineKeyboardButton(text="📜 История", callback_data=f"adm_user_history_{user_id}")],
        [InlineKeyboardButton(text="🤖 AI-сводка", callback_data=f"ai_user_summary_{user_id}")],
    ]
    if is_banned:
        buttons.append([InlineKeyboardButton(text="✅ Разбанить", callback_data=f"adm_user_unban_{user_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="🚫 Забанить", callback_data=f"adm_user_ban_{user_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Пользователи", callback_data="adm_users")])
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data == "adm_users")
async def cb_adm_users(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    users = await db.get_all_users()
    if not users:
        await callback.message.edit_text("👥 Нет.", reply_markup=admin_menu_kb(), parse_mode="HTML")
        return
    lines = [f"👥 <b>{len(users)} пользователей</b>", "Нажмите на пользователя, чтобы открыть карточку."]
    buttons = []
    for u in users[:30]:
        lines.append(f"• <code>{u['user_id']}</code> | @{html(u.get('username') or '—')} | {html(u.get('full_name') or '—')}")
        title = u.get("full_name") or u.get("username") or str(u["user_id"])
        uname = u.get("username")
        dm_url = f"https://t.me/{uname}" if uname else f"tg://user?id={u['user_id']}"
        buttons.append([
            InlineKeyboardButton(text=f"👤 {title[:35]}", callback_data=f"adm_user_{u['user_id']}"),
            InlineKeyboardButton(text="💬", url=dm_url),
        ])
    if len(users) > 30:
        lines.append(f"... +{len(users) - 30}")
    buttons.append([InlineKeyboardButton(text="🔎 Поиск", callback_data="adm_search")])
    buttons.append([InlineKeyboardButton(text="⬅️ Панель", callback_data="adm_back_main")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_user_history_"))
async def cb_adm_user_history(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.removeprefix("adm_user_history_"))
    orders = await db.get_user_orders(user_id)
    lines = [f"📜 <b>История пользователя</b> <code>{user_id}</code>"]
    buttons = []
    if not orders:
        lines.append("\nЗаказов нет.")
    for o in orders[:15]:
        sub_name = await product_name_for_order(o)
        lines.append(f"\n{STATUS_EMOJI.get(o['status'], '❓')} <b>#{o['id']}</b> | {html(sub_name)} | {o['price']}₽\n<code>{o.get('created_at') or '—'}</code> | {html(order_method_label(o.get('payment_method')))}")
        buttons.append([InlineKeyboardButton(text=f"📦 Заказ #{o['id']}", callback_data=f"adm_order_{o['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Карточка пользователя", callback_data=f"adm_user_{user_id}")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_write_"))
async def cb_adm_user_write(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.removeprefix("adm_user_write_"))
    await state.set_state(AdminMessage.waiting_text)
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text(
        f"✉️ <b>Сообщение пользователю</b> <code>{user_id}</code>\n\nВведите текст одним сообщением:",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_ban_"))
async def cb_adm_user_ban(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.removeprefix("adm_user_ban_"))
    if await is_admin(user_id):
        await callback.answer("Нельзя заблокировать администратора", show_alert=True)
        return
    await db.set_user_ban(user_id, True, "бан через карточку пользователя")
    await callback.answer("Пользователь заблокирован")
    await _show_admin_user_card(callback.message, user_id)


@router.callback_query(F.data.startswith("adm_user_unban_"))
async def cb_adm_user_unban(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.removeprefix("adm_user_unban_"))
    await db.set_user_ban(user_id, False)
    await callback.answer("Пользователь разблокирован")
    await _show_admin_user_card(callback.message, user_id)


@router.callback_query(F.data.startswith("adm_user_"))
async def cb_adm_user_card(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.removeprefix("adm_user_"))
    await _show_admin_user_card(callback.message, user_id)
    await callback.answer()


@router.callback_query(F.data == "adm_admins")
async def cb_adm_admins(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    admins = await db.get_all_admins()
    lines = ["👮 <b>Админы</b>\n"]
    if config.ADMIN_ID:
        lines.append(f"👑 <code>{config.ADMIN_ID}</code> — Главный")
    for a in admins:
        lines.append(f"• <code>{a['user_id']}</code> | @{a['username'] or '—'}")
    lines.append("\n/addadmin ID | /deladmin ID")
    await callback.message.edit_text("\n".join(lines), reply_markup=admin_menu_kb(), parse_mode="HTML")



# ══════════════════════════════════════════════════════════════════════════════
#  AI ADMIN TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_ai")
async def cb_adm_ai(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer()
    api_key = await S("openai_api_key")
    status = "✅ Подключён" if api_key else "❌ Не настроен (установите API ключ в настройках)"
    model = await S("openai_model", "gpt-4o-mini")
    text = (
        "🤖 <b>AI-помощник администратора</b>\n\n"
        f"Статус: {status}\n"
        f"Модель: <code>{html(model)}</code>\n\n"
        "Выберите инструмент:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Составить текст рассылки", callback_data="ai_broadcast")],
        [InlineKeyboardButton(text="📝 Сгенерировать описание товара", callback_data="ai_product_desc")],
        [InlineKeyboardButton(text="💬 Составить ответ клиенту", callback_data="ai_reply")],
        [InlineKeyboardButton(text="📊 AI-анализ продаж", callback_data="ai_sales_analysis")],
        [InlineKeyboardButton(text="📋 AI-сводка по пользователю", callback_data="ai_user_summary_start")],
        [InlineKeyboardButton(text="🎯 AI-идеи для продвижения", callback_data="ai_promo_ideas")],
        [InlineKeyboardButton(text="⬅️ Панель", callback_data="adm_back_main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


def ai_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 AI-помощник", callback_data="adm_ai")],
        [InlineKeyboardButton(text="⬅️ Панель", callback_data="adm_back_main")],
    ])


# --- AI: Broadcast text composer ---

@router.callback_query(F.data == "ai_broadcast")
async def cb_ai_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.set_state(AIBroadcast.waiting_topic)
    await callback.message.edit_text(
        "✍️ <b>AI-составитель рассылки</b>\n\n"
        "Опишите тему и цель рассылки. Например:\n"
        "<i>«Скидка 30% на все курсы до конца недели»</i>\n"
        "<i>«Напоминание о новом курсе по Python»</i>\n\n"
        "Введите тему:",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(AIBroadcast.waiting_topic)
async def on_ai_broadcast_topic(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    topic = message.text or ""
    if not topic.strip():
        await message.answer("Введите тему рассылки.")
        return
    await message.answer("⏳ Генерирую текст рассылки...")
    stats = await db.get_stats()
    result = await ai_generate(
        system_prompt=(
            "Ты — копирайтер для Telegram-бота по продаже обучающих видеокурсов. "
            "Напиши текст рассылки для пользователей бота. "
            "Используй эмодзи, делай текст кратким и привлекательным. "
            "Формат: готовый текст для Telegram (HTML-разметка: <b>, <i>, <code>). "
            "Не используй markdown. Максимум 500 символов."
        ),
        user_prompt=f"Тема рассылки: {topic}\nКоличество пользователей бота: {stats['users']}",
    )
    await state.clear()
    await message.answer(
        f"✍️ <b>Готовый текст рассылки:</b>\n\n{result}\n\n"
        "💡 Скопируйте текст и используйте /broadcast для отправки.",
        reply_markup=ai_back_kb(), parse_mode="HTML",
    )


# --- AI: Product description generator ---

@router.callback_query(F.data == "ai_product_desc")
async def cb_ai_product_desc(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.set_state(AIProductDesc.waiting_product_info)
    await callback.message.edit_text(
        "📝 <b>AI-генератор описания товара</b>\n\n"
        "Опишите товар: название, тема, что включено.\n"
        "Например: <i>«Курс по веб-дизайну, Figma, 20 уроков, от начального до продвинутого уровня»</i>\n\n"
        "Введите информацию о товаре:",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(AIProductDesc.waiting_product_info)
async def on_ai_product_desc(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    info = message.text or ""
    if not info.strip():
        await message.answer("Введите информацию о товаре.")
        return
    await message.answer("⏳ Генерирую описание...")
    result = await ai_generate(
        system_prompt=(
            "Ты — маркетолог для Telegram-бота по продаже обучающих видеокурсов. "
            "Напиши привлекательное описание товара для карточки в боте. "
            "Используй эмодзи и структуру: что включено, для кого, преимущества. "
            "Формат: HTML для Telegram (<b>, <i>). Максимум 600 символов."
        ),
        user_prompt=f"Информация о товаре: {info}",
    )
    await state.clear()
    await message.answer(
        f"📝 <b>Готовое описание:</b>\n\n{result}\n\n"
        "💡 Скопируйте текст при добавлении/редактировании товара.",
        reply_markup=ai_back_kb(), parse_mode="HTML",
    )


# --- AI: Reply composer ---

@router.callback_query(F.data == "ai_reply")
async def cb_ai_reply(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.set_state(AIReply.waiting_context)
    await callback.message.edit_text(
        "💬 <b>AI-составитель ответа клиенту</b>\n\n"
        "Опишите ситуацию или вставьте сообщение клиента.\n"
        "Например: <i>«Клиент спрашивает, можно ли вернуть деньги за курс»</i>\n\n"
        "Введите контекст:",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(AIReply.waiting_context)
async def on_ai_reply(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    context = message.text or ""
    if not context.strip():
        await message.answer("Введите контекст сообщения.")
        return
    await message.answer("⏳ Составляю ответ...")
    result = await ai_generate(
        system_prompt=(
            "Ты — оператор поддержки Telegram-бота по продаже обучающих видеокурсов. "
            "Составь вежливый, профессиональный ответ клиенту. "
            "Будь дружелюбным и помогай решить проблему. "
            "Формат: обычный текст для Telegram. Максимум 400 символов."
        ),
        user_prompt=f"Ситуация/сообщение клиента: {context}",
    )
    await state.clear()
    await message.answer(
        f"💬 <b>Предложенный ответ:</b>\n\n{result}\n\n"
        "💡 Скопируйте и отправьте через «Написать от бота» в карточке пользователя.",
        reply_markup=ai_back_kb(), parse_mode="HTML",
    )


# --- AI: Sales analysis ---

@router.callback_query(F.data == "ai_sales_analysis")
async def cb_ai_sales_analysis(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer("⏳ Анализирую данные...")
    stats = await db.get_stats()
    products = await db.get_all_products()
    categories = await db.get_all_categories()
    orders = await db.get_all_orders(50)
    product_sales = {}
    for o in orders:
        if o["status"] == "confirmed":
            pid = o.get("subcategory", "?")
            product_sales[pid] = product_sales.get(pid, 0) + 1
    top_products = []
    for p in products:
        count = product_sales.get(str(p["id"]), 0)
        top_products.append(f"- {p['name']}: {count} продаж, цена {p['price']}₽")
    data_text = (
        f"Пользователей: {stats['users']}\n"
        f"Всего заказов: {stats['orders']}\n"
        f"Подтверждённых: {stats['confirmed']}\n"
        f"Ожидающих: {stats['pending']}\n"
        f"Выручка: {stats['revenue']}₽\n"
        f"Категорий: {len(categories)}\n"
        f"Товаров: {len(products)}\n"
        f"Товары:\n" + "\n".join(top_products[:10])
    )
    result = await ai_generate(
        system_prompt=(
            "Ты — бизнес-аналитик для Telegram-бота по продаже видеокурсов. "
            "Проанализируй данные о продажах и дай краткие рекомендации: "
            "что продаётся хорошо, что можно улучшить, какие есть возможности роста. "
            "Формат: HTML для Telegram. Кратко и по делу, максимум 800 символов."
        ),
        user_prompt=f"Данные магазина:\n{data_text}",
    )
    await callback.message.edit_text(
        f"📊 <b>AI-анализ продаж</b>\n\n{result}",
        reply_markup=ai_back_kb(), parse_mode="HTML",
    )


# --- AI: User summary ---

@router.callback_query(F.data == "ai_user_summary_start")
async def cb_ai_user_summary_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AICompose.waiting_prompt)
    await state.update_data(ai_mode="user_summary")
    await callback.message.edit_text(
        "📋 <b>AI-сводка по пользователю</b>\n\n"
        "Введите ID пользователя:",
        reply_markup=cancel_kb(), parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("ai_user_summary_"))
async def cb_ai_user_summary(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.removeprefix("ai_user_summary_"))
    await callback.answer("⏳ Анализирую...")
    await _generate_user_summary(callback.message, user_id, edit=True)


async def _generate_user_summary(message: Message, user_id: int, edit: bool = False):
    user = await db.get_user(user_id)
    if not user:
        text = f"⚠️ Пользователь <code>{user_id}</code> не найден."
        if edit:
            await message.edit_text(text, reply_markup=ai_back_kb(), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=ai_back_kb(), parse_mode="HTML")
        return
    stats = await db.get_user_order_stats(user_id)
    orders = await db.get_user_orders(user_id)
    security = await db.get_user_security(user_id)
    order_details = []
    for o in orders[:10]:
        prod = await db.get_product(int(o["subcategory"])) if str(o.get("subcategory", "")).isdigit() else None
        pname = prod["name"] if prod else o.get("subcategory", "?")
        order_details.append(f"- #{o['id']} {pname} {o['price']}₽ статус:{o['status']} дата:{o.get('created_at', '?')}")
    data_text = (
        f"ID: {user_id}\n"
        f"Username: @{user.get('username') or 'нет'}\n"
        f"Имя: {user.get('full_name') or 'нет'}\n"
        f"Регистрация: {user.get('joined_at') or '?'}\n"
        f"Заказов: {stats['total']} (подтв: {stats['confirmed']}, ожид: {stats['pending']}, откл: {stats['rejected']})\n"
        f"Выручка: {stats['revenue']}₽\n"
        f"Бан: {'да' if security and security.get('is_banned') else 'нет'}\n"
        f"Заказы:\n" + "\n".join(order_details) if order_details else "Заказов нет"
    )
    result = await ai_generate(
        system_prompt=(
            "Ты — аналитик CRM для Telegram-бота по продаже видеокурсов. "
            "Составь краткую сводку по пользователю: тип клиента (новый/активный/VIP), "
            "покупательское поведение, рекомендации по взаимодействию. "
            "Формат: HTML для Telegram. Кратко, максимум 600 символов."
        ),
        user_prompt=f"Данные пользователя:\n{data_text}",
    )
    text = f"📋 <b>AI-сводка: {html(user.get('full_name') or str(user_id))}</b>\n\n{result}"
    buttons = [
        [InlineKeyboardButton(text="👤 Карточка пользователя", callback_data=f"adm_user_{user_id}")],
        [InlineKeyboardButton(text="🤖 AI-помощник", callback_data="adm_ai")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# --- AI: Promo ideas ---

@router.callback_query(F.data == "ai_promo_ideas")
async def cb_ai_promo_ideas(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer("⏳ Генерирую идеи...")
    products = await db.get_all_products()
    stats = await db.get_stats()
    product_list = "\n".join(f"- {p['name']}: {p['price']}₽" for p in products[:15])
    result = await ai_generate(
        system_prompt=(
            "Ты — маркетолог для Telegram-бота по продаже обучающих видеокурсов. "
            "Предложи 5 конкретных идей для продвижения и увеличения продаж. "
            "Учитывай специфику Telegram: рассылки, акции, реферальные программы, контент. "
            "Формат: HTML для Telegram, нумерованный список. Кратко и практично."
        ),
        user_prompt=(
            f"Данные магазина:\n"
            f"Пользователей: {stats['users']}\n"
            f"Выручка: {stats['revenue']}₽\n"
            f"Товары:\n{product_list}"
        ),
    )
    await callback.message.edit_text(
        f"🎯 <b>AI-идеи для продвижения</b>\n\n{result}",
        reply_markup=ai_back_kb(), parse_mode="HTML",
    )


# --- AI: Generic FSM handler for user summary by ID ---

@router.message(AICompose.waiting_prompt)
async def on_ai_compose_prompt(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    data = await state.get_data()
    mode = data.get("ai_mode")
    text = (message.text or "").strip()
    if mode == "user_summary":
        if not text.isdigit():
            await message.answer("Введите числовой ID пользователя.")
            return
        await state.clear()
        await message.answer("⏳ Анализирую пользователя...")
        await _generate_user_summary(message, int(text))
        return
    await state.clear()
    await message.answer("⚠️ Неизвестный режим.", reply_markup=ai_back_kb())


# --- AI: User summary button in user card ---

@router.callback_query(F.data.startswith("adm_ai_user_"))
async def cb_ai_user_card_summary(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.removeprefix("adm_ai_user_"))
    await callback.answer("⏳ Анализирую...")
    await _generate_user_summary(callback.message, user_id, edit=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ACCESS REISSUE
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("access_again_"))
async def cb_access_again(callback: CallbackQuery):
    order_id = int(callback.data.removeprefix("access_again_"))
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order["status"] != "confirmed":
        await callback.answer("Доступ можно выдать повторно только после подтверждения оплаты", show_alert=True)
        return
    if await S("access_reissue_enabled", "1") != "1":
        await callback.answer("Повторная выдача временно отключена", show_alert=True)
        return
    max_count = await get_int_setting("max_access_reissues_per_order", 3)
    if max_count >= 0 and int(order.get("access_reissued_count", 0) or 0) >= max_count:
        await callback.answer(f"Лимит повторной выдачи: {max_count}", show_alert=True)
        return
    product = await db.get_product(int(order["subcategory"])) if order["subcategory"].isdigit() else None
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    try:
        invite_link = await generate_invite_link(product)
        await db.increment_order_reissue(order_id, invite_link)
        await callback.message.answer(
            f"🔁 <b>Доступ выдан повторно</b>\n\n📦 #{order_id} | {product['name']}\n\n🔗 Ссылка:\n{invite_link}\n\n⚠️ Ссылка одноразовая.",
            reply_markup=back_to_main_kb(), parse_mode="HTML",
        )
        await callback.answer("Ссылка отправлена")
    except Exception as e:
        await db.log_error("create_link", str(e), user_id=callback.from_user.id, order_id=order_id, context="access_again")
        await callback.answer("Ошибка выдачи ссылки. Админ увидит это в логах.", show_alert=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN: SECURITY / BLACKLIST / ERROR LOGS
# ══════════════════════════════════════════════════════════════════════════════

ERROR_TYPE_LABELS = {
    "payment": "💳 ошибки платежей",
    "create_link": "🔗 ошибки создания ссылок",
    "send_message": "✉️ ошибки отправки сообщений",
    "database": "🗄 ошибки базы",
}


async def _show_security_menu(message: Message, edit: bool = True):
    limit = await S("antispam_message_limit_per_minute", "12")
    delay = await S("payment_button_cooldown_seconds", "8")
    reissue = "✅ включена" if await S("access_reissue_enabled", "1") == "1" else "❌ отключена"
    max_reissue = await S("max_access_reissues_per_order", "3")
    banned = await db.get_banned_users(5)
    lines = [
        "🛡 <b>Антиспам и защита</b>\n",
        f"💬 Лимит сообщений: <b>{limit}</b> / мин.",
        f"🕒 Задержка кнопок оплаты: <b>{delay}</b> сек.",
        f"🔁 Повторная выдача доступа: <b>{reissue}</b>",
        f"🔢 Лимит повторной выдачи: <b>{max_reissue}</b>",
        "\n🚫 <b>Черный список:</b>",
    ]
    if banned:
        for u in banned:
            lines.append(f"• <code>{u['user_id']}</code> | @{u.get('username') or '—'} | {u.get('ban_reason') or 'без причины'}")
    else:
        lines.append("пусто")
    lines.append("\n💡 Команды: <code>/ban ID причина</code> и <code>/unban ID</code>")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Лимит сообщений", callback_data="set_edit_antispam_message_limit_per_minute")],
        [InlineKeyboardButton(text="🕒 Задержка оплаты", callback_data="set_edit_payment_button_cooldown_seconds")],
        [InlineKeyboardButton(text="🔁 Вкл/выкл повторную выдачу", callback_data="sec_toggle_reissue")],
        [InlineKeyboardButton(text="🔢 Лимит повторной выдачи", callback_data="set_edit_max_access_reissues_per_order")],
        [InlineKeyboardButton(text="🚫 Черный список", callback_data="sec_banned")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back_main")],
    ])
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_security")
async def cb_adm_security(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        return
    await state.clear()
    await _show_security_menu(callback.message)
    await callback.answer()


@router.callback_query(F.data == "sec_toggle_reissue")
async def cb_sec_toggle_reissue(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    current = await S("access_reissue_enabled", "1")
    await db.set_setting("access_reissue_enabled", "0" if current == "1" else "1")
    await callback.answer("Обновлено")
    await _show_security_menu(callback.message)


@router.callback_query(F.data == "sec_banned")
async def cb_sec_banned(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    banned = await db.get_banned_users(50)
    lines = ["🚫 <b>Черный список</b>\n"]
    buttons = []
    if not banned:
        lines.append("Пусто")
    for u in banned:
        lines.append(f"• <code>{u['user_id']}</code> | @{u.get('username') or '—'} | {u.get('ban_reason') or 'без причины'}")
        buttons.append([InlineKeyboardButton(text=f"✅ Разбан {u['user_id']}", callback_data=f"sec_unban_{u['user_id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Защита", callback_data="adm_security")])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("sec_unban_"))
async def cb_sec_unban(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.removeprefix("sec_unban_"))
    await db.set_user_ban(user_id, False)
    await callback.answer("Разблокирован")
    await _show_security_menu(callback.message)


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if not await is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("❓ <code>/ban ID причина</code>", parse_mode="HTML")
        return
    user_id = int(parts[1])
    if await is_admin(user_id):
        await message.answer("❌ Нельзя заблокировать администратора.")
        return
    reason = parts[2] if len(parts) > 2 else "без причины"
    await db.set_user_ban(user_id, True, reason)
    await message.answer(f"🚫 Пользователь <code>{user_id}</code> заблокирован.\nПричина: {reason}", reply_markup=admin_menu_kb(), parse_mode="HTML")


@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if not await is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("❓ <code>/unban ID</code>", parse_mode="HTML")
        return
    user_id = int(parts[1])
    await db.set_user_ban(user_id, False)
    await message.answer(f"✅ Пользователь <code>{user_id}</code> разблокирован.", reply_markup=admin_menu_kb(), parse_mode="HTML")


async def _show_error_logs(message: Message, edit: bool = True, error_type: str | None = None):
    limit = await get_int_setting("error_log_limit", 20)
    summary = await db.get_error_summary()
    logs = await db.get_error_logs(limit, error_type=error_type)
    title = ERROR_TYPE_LABELS.get(error_type, "все ошибки") if error_type else "все ошибки"
    lines = [f"🧾 <b>Логи ошибок — {title}</b>\n"]
    if summary:
        lines.append("📊 <b>Сводка:</b>")
        for item in summary:
            label = ERROR_TYPE_LABELS.get(item["error_type"], item["error_type"])
            lines.append(f"• {label}: <b>{item['count']}</b> | последнее: <code>{item['last_at']}</code>")
    else:
        lines.append("✅ Ошибок пока нет.")
    if logs:
        lines.append("\n📝 <b>Последние записи:</b>")
        for item in logs:
            label = ERROR_TYPE_LABELS.get(item["error_type"], item["error_type"])
            ctx = f" | {item['context']}" if item.get("context") else ""
            order = f" | заказ #{item['order_id']}" if item.get("order_id") else ""
            user = f" | user <code>{item['user_id']}</code>" if item.get("user_id") else ""
            msg = str(item["message"]).replace("<", "&lt;").replace(">", "&gt;")[:220]
            lines.append(f"\n{label}\n<code>{item['created_at']}</code>{user}{order}{ctx}\n<code>{msg}</code>")
    lines.append("\n💡 Настройка длины отчета: кнопка «Количество строк». Очистка удаляет только журнал ошибок, данные заказов не трогает.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Все", callback_data="err_filter_all"), InlineKeyboardButton(text="💳 Платежи", callback_data="err_filter_payment")],
        [InlineKeyboardButton(text="🔗 Ссылки", callback_data="err_filter_create_link"), InlineKeyboardButton(text="✉️ Сообщения", callback_data="err_filter_send_message")],
        [InlineKeyboardButton(text="🗄 База", callback_data="err_filter_database"), InlineKeyboardButton(text="🔢 Количество строк", callback_data="set_edit_error_log_limit")],
        [InlineKeyboardButton(text="🧹 Очистить этот отчет", callback_data=f"err_clear_{error_type or 'all'}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back_main")],
    ])
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("errors"))
async def cmd_errors(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await _show_error_logs(message, edit=False)


@router.callback_query(F.data == "adm_errors")
async def cb_adm_errors(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await _show_error_logs(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("err_filter_"))
async def cb_err_filter(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    value = callback.data.removeprefix("err_filter_")
    await _show_error_logs(callback.message, error_type=None if value == "all" else value)
    await callback.answer()


@router.callback_query(F.data.startswith("err_clear_"))
async def cb_err_clear(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    value = callback.data.removeprefix("err_clear_")
    await db.clear_error_logs(None if value == "all" else value)
    await callback.answer("Логи очищены")
    await _show_error_logs(callback.message, error_type=None if value == "all" else value)




async def _show_admin_logs(message: Message, edit: bool = True):
    logs = await db.get_admin_logs(30)
    lines = [
        "📜 <b>Логи админов</b>",
        "Автоматически очищаются раз в 7 дней.",
    ]
    if not logs:
        lines.append("\nПока записей нет.")
    else:
        lines.append("\n📝 <b>Последние действия:</b>")
        for item in logs:
            action = html(item.get("action"))
            details = html(item.get("details"))
            details_line = f"\n<code>{details}</code>" if item.get("details") else ""
            lines.append(
                f"\n<code>{item['created_at']}</code>\n"
                f"👤 <code>{item['admin_id']}</code> | {html(item.get('admin_name'))}\n"
                f"⚙️ {action}{details_line}"
            )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="adm_admin_logs")],
        [InlineKeyboardButton(text="🧹 Очистить логи", callback_data="adm_log_clear")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back_main")],
    ])
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("adminlogs"))
async def cmd_adminlogs(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await _show_admin_logs(message, edit=False)


@router.callback_query(F.data == "adm_admin_logs")
async def cb_adm_admin_logs(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await _show_admin_logs(callback.message)
    await callback.answer()


@router.callback_query(F.data == "adm_log_clear")
async def cb_adm_log_clear(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await db.clear_admin_logs()
    await callback.answer("Логи админов очищены")
    await _show_admin_logs(callback.message)



# ══════════════════════════════════════════════════════════════════════════════
#  BACKUPS / EXPORTS
# ══════════════════════════════════════════════════════════════════════════════

BACKUP_DIR = Path("backups")
EXPORT_DIR = Path("exports")


def _ensure_dirs():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _timestamp_for_file() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


async def create_database_backup() -> Path:
    _ensure_dirs()
    src = Path(db.DB_PATH)
    dest = BACKUP_DIR / f"bot_data_{_timestamp_for_file()}.db"
    if not src.exists():
        raise FileNotFoundError(f"База не найдена: {src}")
    shutil.copy2(src, dest)
    return dest


async def cleanup_old_backups():
    keep_days = await get_int_setting("daily_backup_keep_days", 14)
    cutoff = time.time() - max(1, keep_days) * 24 * 60 * 60
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for file in BACKUP_DIR.glob("bot_data_*.db"):
        try:
            if file.stat().st_mtime < cutoff:
                file.unlink()
        except Exception:
            pass


async def _write_csv(filename: str, rows: list[dict]) -> Path:
    _ensure_dirs()
    path = EXPORT_DIR / filename
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


async def _show_backups_menu(message: Message, edit: bool = True):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = sorted(BACKUP_DIR.glob("bot_data_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    auto = "✅ включён" if await S("daily_backup_enabled", "1") == "1" else "❌ выключен"
    keep = await S("daily_backup_keep_days", "14")
    lines = [
        "💾 <b>Резервные копии и экспорт</b>",
        f"Автобэкап: <b>{auto}</b>",
        f"Хранение: <b>{keep}</b> дней",
        f"Последних копий: <b>{len(backups)}</b>",
    ]
    if backups[:5]:
        lines.append("\n<b>Последние:</b>")
        for b in backups[:5]:
            size_kb = round(b.stat().st_size / 1024, 1)
            lines.append(f"• <code>{b.name}</code> — {size_kb} KB")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать базу", callback_data="backup_download_db")],
        [InlineKeyboardButton(text="🆕 Создать копию сейчас", callback_data="backup_create_now")],
        [InlineKeyboardButton(text="📄 Экспорт заказов", callback_data="backup_export_orders")],
        [InlineKeyboardButton(text="👥 Экспорт пользователей", callback_data="backup_export_users")],
        [InlineKeyboardButton(text="🛒 Экспорт товаров", callback_data="backup_export_products")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back_main")],
    ])
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("backups"))
async def cmd_backups(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await _show_backups_menu(message, edit=False)


@router.callback_query(F.data == "adm_backups")
async def cb_adm_backups(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await _show_backups_menu(callback.message)
    await callback.answer()


@router.callback_query(F.data.in_({"backup_download_db", "backup_create_now", "backup_export_orders", "backup_export_users", "backup_export_products"}))
async def cb_backup_actions(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    try:
        if callback.data in {"backup_download_db", "backup_create_now"}:
            path = await create_database_backup()
            await callback.message.answer_document(FSInputFile(path), caption="💾 Резервная копия базы")
            await cleanup_old_backups()
        elif callback.data == "backup_export_orders":
            path = await _write_csv(f"orders_{_timestamp_for_file()}.csv", await db.get_all_orders_export())
            await callback.message.answer_document(FSInputFile(path), caption="📄 Экспорт заказов")
        elif callback.data == "backup_export_users":
            path = await _write_csv(f"users_{_timestamp_for_file()}.csv", await db.get_all_users())
            await callback.message.answer_document(FSInputFile(path), caption="👥 Экспорт пользователей")
        elif callback.data == "backup_export_products":
            path = await _write_csv(f"products_{_timestamp_for_file()}.csv", await db.get_all_products())
            await callback.message.answer_document(FSInputFile(path), caption="🛒 Экспорт товаров")
        await callback.answer("Готово")
    except Exception as e:
        await db.log_error("database", str(e), user_id=callback.from_user.id, context="backup/export")
        await callback.answer("Ошибка. Подробности в логах.", show_alert=True)


async def daily_backup_loop():
    while True:
        try:
            if await S("daily_backup_enabled", "1") == "1":
                await create_database_backup()
                await cleanup_old_backups()
        except Exception as e:
            await db.log_error("database", str(e), context="daily_backup_loop")
        await asyncio.sleep(24 * 60 * 60)


# ══════════════════════════════════════════════════════════════════════════════
#  REVIEWS AFTER PURCHASE
# ══════════════════════════════════════════════════════════════════════════════


def review_request_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐", callback_data=f"review_rate_{order_id}_1"),
         InlineKeyboardButton(text="⭐⭐", callback_data=f"review_rate_{order_id}_2"),
         InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"review_rate_{order_id}_3")],
        [InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"review_rate_{order_id}_4"),
         InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"review_rate_{order_id}_5")],
        [InlineKeyboardButton(text="✍️ Написать отзыв", callback_data=f"review_text_{order_id}")],
        [InlineKeyboardButton(text="🆘 Нужна помощь", callback_data=f"review_help_{order_id}")],
    ])


async def send_review_request(order: dict):
    sub_name = await product_name_for_order(order)
    try:
        await bot.send_message(
            order["user_id"],
            f"⭐ <b>Всё получилось?</b>\n\nКак вам материал: <b>{html(sub_name)}</b>?\nОцените покупку или напишите отзыв.",
            reply_markup=review_request_kb(order["id"]), parse_mode="HTML",
        )
        await db.mark_review_request_sent(order["id"])
    except Exception as e:
        await db.log_error("send_message", str(e), user_id=order["user_id"], order_id=order["id"], context="send_review_request")


async def review_request_loop():
    while True:
        try:
            hours = await get_int_setting("review_request_delay_hours", 24)
            for order in await db.get_orders_for_review_requests(hours, limit=20):
                await send_review_request(order)
                await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Review loop error: {e}")
        await asyncio.sleep(60 * 60)


@router.callback_query(F.data.startswith("review_rate_"))
async def cb_review_rate(callback: CallbackQuery):
    parts = callback.data.removeprefix("review_rate_").split("_")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await callback.answer("Ошибка", show_alert=True)
        return
    order_id = int(parts[0])
    rating = int(parts[1])
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    await db.save_purchase_review(order_id, callback.from_user.id, rating=rating)
    await callback.message.edit_text(f"Спасибо за оценку: {'⭐' * rating}\n\nЕсли нужна помощь — напишите в поддержку.", reply_markup=back_to_main_kb(), parse_mode="HTML")
    await callback.answer("Спасибо!")


@router.callback_query(F.data.startswith("review_text_"))
async def cb_review_text(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.removeprefix("review_text_"))
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    await state.set_state(ReviewFlow.waiting_text)
    await state.update_data(review_order_id=order_id)
    await callback.message.edit_text("✍️ Напишите отзыв одним сообщением:", reply_markup=cancel_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(ReviewFlow.waiting_text, F.text, F.chat.type == "private")
async def fsm_review_text(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = int(data.get("review_order_id", 0))
    order = await db.get_order(order_id)
    if not order or order["user_id"] != message.from_user.id:
        await state.clear()
        await message.answer("❌ Заказ не найден.", reply_markup=back_to_main_kb(), parse_mode="HTML")
        return
    await db.save_purchase_review(order_id, message.from_user.id, review_text=message.text.strip())
    await state.clear()
    await message.answer("Спасибо! Отзыв сохранён 🙏", reply_markup=back_to_main_kb(), parse_mode="HTML")
    await notify_admins(f"⭐ <b>Новый отзыв</b>\n\n📦 #{order_id}\n👤 <code>{message.from_user.id}</code>\n\n{html(message.text[:1000])}")


@router.callback_query(F.data.startswith("review_help_"))
async def cb_review_help(callback: CallbackQuery):
    order_id = int(callback.data.removeprefix("review_help_"))
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    await db.save_purchase_review(order_id, callback.from_user.id, needs_help=True)
    await callback.message.edit_text("🆘 Напишите проблему в ответном сообщении или выберите раздел поддержки.", reply_markup=back_to_main_kb(), parse_mode="HTML")
    await notify_admins(f"🆘 <b>Покупателю нужна помощь</b>\n\n📦 #{order_id}\n👤 <code>{callback.from_user.id}</code>")
    await callback.answer()


async def _show_reviews(message: Message, edit: bool = True):
    reviews = await db.get_purchase_reviews(30)
    lines = ["⭐ <b>Отзывы покупателей</b>\n"]
    if not reviews:
        lines.append("Пока отзывов нет.")
    for r in reviews:
        stars = "⭐" * int(r.get("rating") or 0) if r.get("rating") else "—"
        help_mark = " 🆘" if r.get("needs_help") else ""
        text = (r.get("review_text") or "").strip()
        if len(text) > 180:
            text = text[:177] + "..."
        lines.append(f"<code>{r['created_at']}</code> | #{r['order_id']} | <code>{r['user_id']}</code>{help_mark}\n{stars}\n{html(text) if text else '—'}\n")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="adm_reviews")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back_main")],
    ])
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("reviews"))
async def cmd_reviews(message: Message):
    if not await is_admin(message.from_user.id):
        return
    await _show_reviews(message, edit=False)


@router.callback_query(F.data == "adm_reviews")
async def cb_adm_reviews(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    await _show_reviews(callback.message)
    await callback.answer()


# ══════════════════════════════════════════════════════════════════════════════
#  UNPAID ORDER REMINDERS
# ══════════════════════════════════════════════════════════════════════════════


def unpaid_reminder_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", callback_data=f"remind_pay_{order_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"remind_cancel_{order_id}")],
    ])


async def unpaid_order_reminder_loop():
    while True:
        try:
            minutes = await get_int_setting("pending_order_reminder_minutes", 60)
            if minutes > 0:
                for order in await db.get_pending_orders_for_reminder(minutes, limit=30):
                    sub_name = await product_name_for_order(order)
                    try:
                        await bot.send_message(
                            order["user_id"],
                            "🔔 <b>Вы начали оформление заказа, но не завершили оплату.</b>\n\n"
                            f"📦 #{order['id']} | {html(sub_name)}\n"
                            f"💰 {order['price']}₽\n\n"
                            "Хотите продолжить?",
                            reply_markup=unpaid_reminder_kb(order["id"]), parse_mode="HTML",
                        )
                        await db.mark_order_reminder_sent(order["id"])
                    except Exception as e:
                        await db.log_error("send_message", str(e), user_id=order["user_id"], order_id=order["id"], context="unpaid_order_reminder")
                    await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Unpaid reminder loop error: {e}")
        await asyncio.sleep(10 * 60)


@router.callback_query(F.data.startswith("remind_pay_"))
async def cb_remind_pay(callback: CallbackQuery):
    order_id = int(callback.data.removeprefix("remind_pay_"))
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order["status"] != "pending":
        await callback.answer("Заказ уже обработан", show_alert=True)
        return
    product = await db.get_product(int(order["subcategory"])) if str(order.get("subcategory", "")).isdigit() else None
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"📦 <b>Заказ #{order_id}</b>\n\n{html(product['name'])}\n\n💰 <b>{product['price']}₽</b>\n\nВыберите способ оплаты:",
        reply_markup=await payment_method_kb(product["id"], product["price"], product.get("category_id", 0)), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remind_cancel_"))
async def cb_remind_cancel(callback: CallbackQuery):
    order_id = int(callback.data.removeprefix("remind_cancel_"))
    order = await db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    await db.cancel_order(order_id)
    await callback.message.edit_text(f"🚫 Заказ #{order_id} отменён.", reply_markup=back_to_main_kb(), parse_mode="HTML")
    await callback.answer("Отменено")


async def admin_log_cleanup_loop():
    while True:
        try:
            await db.purge_old_admin_logs(7)
        except Exception as e:
            logger.warning(f"Admin log cleanup error: {e}")
        await asyncio.sleep(7 * 24 * 60 * 60)


# ─── Set commands ────────────────────────────────────────────────────────────

async def set_commands():
    user_cmds = [
        BotCommand(command="start", description="🎓 Главное меню"),
        BotCommand(command="menu", description="📌 Меню"),
        BotCommand(command="myid", description="🆔 Мой ID"),
        BotCommand(command="chatid", description="🔍 ID этого чата"),
    ]
    await bot.set_my_commands(user_cmds, scope=BotCommandScopeAllPrivateChats())
    admin_cmds = user_cmds + [
        BotCommand(command="admin", description="⚙️ Панель"),
        BotCommand(command="help_admin", description="📖 Справка"),
        BotCommand(command="stats", description="📊 Статистика"),
        BotCommand(command="pending", description="📦 Ожидающие"),
        BotCommand(command="orders", description="📋 Заказы"),
        BotCommand(command="confirm", description="✅ Подтвердить"),
        BotCommand(command="reject", description="❌ Отклонить"),
        BotCommand(command="users", description="👥 Пользователи"),
        BotCommand(command="broadcast", description="📢 Рассылка"),
        BotCommand(command="backups", description="💾 Резервные копии"),
        BotCommand(command="reviews", description="⭐ Отзывы"),
        BotCommand(command="ban", description="🚫 Заблокировать пользователя"),
        BotCommand(command="unban", description="✅ Разблокировать пользователя"),
        BotCommand(command="errors", description="🧾 Логи ошибок"),
        BotCommand(command="adminlogs", description="📜 Логи админов"),
        BotCommand(command="addadmin", description="👮 Добавить админа"),
        BotCommand(command="deladmin", description="🚫 Удалить админа"),
        BotCommand(command="admins", description="👮 Список"),
    ]
    if config.ADMIN_ID:
        try:
            await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=config.ADMIN_ID))
        except Exception:
            pass
    for adm in await db.get_all_admins():
        try:
            await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=adm["user_id"]))
        except Exception:
            pass


# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    await db.init_db()
    await db.seed_defaults(config)
    await db.seed_default_categories()
    await db.seed_default_products()
    await db.purge_old_admin_logs(7)
    asyncio.create_task(admin_log_cleanup_loop())
    asyncio.create_task(daily_backup_loop())
    asyncio.create_task(review_request_loop())
    asyncio.create_task(unpaid_order_reminder_loop())
    await set_commands()
    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
