"""
Telegram Education Bot — selling video courses via categories.

Features:
- Main menu with inline keyboard
- Video materials category with 3 subcategories + price list
- Payment flow with admin confirmation
- Support category
- Admin panel: confirm/reject orders, view stats
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import database as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ─── Keyboards ───────────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Видеоматериалы", callback_data="cat_video")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="cat_support")],
        [InlineKeyboardButton(text="📋 Мои заказы", callback_data="my_orders")],
    ])


def video_subcategories_kb() -> InlineKeyboardMarkup:
    buttons = []
    for key, sub in config.SUBCATEGORIES.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{sub['name']} — {sub['price']} ₽",
                callback_data=f"sub_{key}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_kb(subcategory_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_{subcategory_key}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="cat_video")],
    ])


def admin_order_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{order_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order_id}"),
        ]
    ])


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")],
    ])


# ─── Handlers ────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    await message.answer(
        "🎓 <b>Добро пожаловать в Edu Store!</b>\n\n"
        "Здесь вы можете приобрести доступ к обучающим видеоматериалам "
        "по программированию, дизайну и маркетингу.\n\n"
        "Выберите раздел:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(
        "📌 <b>Главное меню</b>\n\nВыберите раздел:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if config.ADMIN_ID and message.from_user.id != config.ADMIN_ID:
        return
    stats = await db.get_stats()
    await message.answer(
        "📊 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"📦 Всего заказов: <b>{stats['orders']}</b>\n"
        f"✅ Подтверждено: <b>{stats['confirmed']}</b>\n"
        f"💰 Выручка: <b>{stats['revenue']} ₽</b>",
        parse_mode="HTML",
    )


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>", parse_mode="HTML")


# ─── Callback handlers ──────────────────────────────────────────────────────

@router.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "📌 <b>Главное меню</b>\n\nВыберите раздел:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cat_video")
async def cb_video_category(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎬 <b>Видеоматериалы</b>\n\n"
        "Выберите интересующее направление обучения.\n"
        "После оплаты вам будет предоставлен доступ к закрытому каналу с материалами.\n\n"
        "📋 <b>Прайс-лист:</b>",
        reply_markup=video_subcategories_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub_"))
async def cb_subcategory(callback: CallbackQuery):
    key = callback.data.removeprefix("sub_")
    sub = config.SUBCATEGORIES.get(key)
    if not sub:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    text = (
        f"{sub['name']}\n\n"
        f"📝 <b>Описание:</b>\n{sub['description']}\n\n"
        f"💰 <b>Стоимость:</b> {sub['price']} ₽\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>Способ оплаты:</b> {config.PAYMENT_METHOD}\n"
        f"💳 <b>Карта:</b> <code>{config.PAYMENT_CARD}</code>\n"
        f"👤 <b>Получатель:</b> {config.PAYMENT_NAME}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 В комментарии к переводу укажите ваш Telegram ID: "
        f"<code>{callback.from_user.id}</code>\n\n"
        "После оплаты нажмите кнопку ниже ⬇️"
    )
    await callback.message.edit_text(text, reply_markup=payment_kb(key), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("paid_"))
async def cb_paid(callback: CallbackQuery):
    key = callback.data.removeprefix("paid_")
    sub = config.SUBCATEGORIES.get(key)
    if not sub:
        await callback.answer("Ошибка", show_alert=True)
        return

    order_id = await db.create_order(
        callback.from_user.id,
        callback.from_user.username,
        key,
        sub["price"],
    )

    await callback.message.edit_text(
        "⏳ <b>Заявка на оплату создана!</b>\n\n"
        f"📦 Заказ: <b>#{order_id}</b>\n"
        f"📚 Курс: {sub['name']}\n"
        f"💰 Сумма: {sub['price']} ₽\n\n"
        "Ваш платёж будет проверен администратором.\n"
        "После подтверждения вы получите ссылку на канал с материалами.\n\n"
        "⏱ Обычно это занимает не более 30 минут.",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )
    await callback.answer()

    # Notify admin
    if config.ADMIN_ID:
        admin_text = (
            "🔔 <b>Новый заказ!</b>\n\n"
            f"📦 Заказ: <b>#{order_id}</b>\n"
            f"👤 Покупатель: {callback.from_user.full_name}\n"
            f"🆔 ID: <code>{callback.from_user.id}</code>\n"
            f"📱 Username: @{callback.from_user.username or '—'}\n"
            f"📚 Курс: {sub['name']}\n"
            f"💰 Сумма: {sub['price']} ₽\n\n"
            "Проверьте поступление оплаты и подтвердите заказ:"
        )
        await bot.send_message(
            config.ADMIN_ID,
            admin_text,
            reply_markup=admin_order_kb(order_id),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("confirm_"))
async def cb_confirm_order(callback: CallbackQuery):
    if config.ADMIN_ID and callback.from_user.id != config.ADMIN_ID:
        await callback.answer("Только администратор может подтверждать заказы", show_alert=True)
        return

    order_id = int(callback.data.removeprefix("confirm_"))
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    if order["status"] != "pending":
        await callback.answer("Заказ уже обработан", show_alert=True)
        return

    await db.confirm_order(order_id)
    sub = config.SUBCATEGORIES.get(order["subcategory"])

    await callback.message.edit_text(
        f"✅ Заказ <b>#{order_id}</b> подтверждён!\n"
        f"Ссылка на канал отправлена пользователю.",
        parse_mode="HTML",
    )
    await callback.answer("Заказ подтверждён!")

    # Send channel link to user
    if sub:
        await bot.send_message(
            order["user_id"],
            f"🎉 <b>Оплата подтверждена!</b>\n\n"
            f"📦 Заказ: <b>#{order_id}</b>\n"
            f"📚 Курс: {sub['name']}\n\n"
            f"🔗 Ваша ссылка на канал с материалами:\n{sub['channel_link']}\n\n"
            "Спасибо за покупку! Приятного обучения! 🎓",
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("reject_"))
async def cb_reject_order(callback: CallbackQuery):
    if config.ADMIN_ID and callback.from_user.id != config.ADMIN_ID:
        await callback.answer("Только администратор может отклонять заказы", show_alert=True)
        return

    order_id = int(callback.data.removeprefix("reject_"))
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    if order["status"] != "pending":
        await callback.answer("Заказ уже обработан", show_alert=True)
        return

    await db.reject_order(order_id)

    await callback.message.edit_text(
        f"❌ Заказ <b>#{order_id}</b> отклонён.",
        parse_mode="HTML",
    )
    await callback.answer("Заказ отклонён")

    sub = config.SUBCATEGORIES.get(order["subcategory"])
    sub_name = sub["name"] if sub else order["subcategory"]
    await bot.send_message(
        order["user_id"],
        f"❌ <b>Заказ #{order_id} отклонён</b>\n\n"
        f"📚 Курс: {sub_name}\n\n"
        "Оплата не была подтверждена. Если вы уверены, что оплатили, "
        "свяжитесь с поддержкой.",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cat_support")
async def cb_support(callback: CallbackQuery):
    lines = ["🆘 <b>Поддержка</b>\n", "По любым вопросам обращайтесь:\n"]
    for contact in config.SUPPORT_CONTACTS:
        lines.append(f"• {contact['name']}: {contact['username']}")
    lines.append("\nМы ответим в ближайшее время!")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "my_orders")
async def cb_my_orders(callback: CallbackQuery):
    orders = await db.get_user_orders(callback.from_user.id)
    if not orders:
        await callback.message.edit_text(
            "📋 <b>Мои заказы</b>\n\nУ вас пока нет заказов.",
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    status_emoji = {"pending": "⏳", "confirmed": "✅", "rejected": "❌"}
    lines = ["📋 <b>Мои заказы</b>\n"]
    for o in orders[:10]:
        sub = config.SUBCATEGORIES.get(o["subcategory"])
        sub_name = sub["name"] if sub else o["subcategory"]
        emoji = status_emoji.get(o["status"], "❓")
        lines.append(
            f"{emoji} #{o['id']} | {sub_name} | {o['price']} ₽ | {o['created_at'][:16]}"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


async def main():
    await db.init_db()
    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
