import json
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

"""
PharmaHeaven Telegram bot
-------------------------
Safe template for an informational wellness catalog bot.

What this bot does:
- Shows a catalog of general wellness products
- Displays detailed product cards
- Explains delivery/payment placeholders (text only)
- Collects contact requests for a human manager
- Stores leads in SQLite
- Contains a FAQ and legal disclaimer

What this bot does NOT do:
- No checkout flow
- No medical claims
- No diagnosis/treatment advice
- No direct sale automation for supplements

Setup:
1. Create a bot with @BotFather
2. Set env var BOT_TOKEN=... 
3. Optionally set ADMIN_CHAT_ID=123456789 to receive lead notifications
4. pip install python-telegram-bot==21.*
5. python pharmaheaven_bot.py
"""

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "pharmaheaven.db")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

ASK_NAME, ASK_PHONE, ASK_PRODUCT, ASK_COMMENT = range(4)

PRODUCTS: List[Dict[str, str]] = [
    {
        "id": "omega_balance",
        "name": "Omega Balance",
        "category": "Поддержка ежедневного рациона",
        "description": (
            "Комплекс омега-3 для взрослых. Карточка товара носит только информационный характер. "
            "Перед применением важно изучить состав, противопоказания и рекомендации производителя."
        ),
        "price": "от 1 490 ₽",
        "usage": "Смотрите инструкцию производителя на упаковке.",
    },
    {
        "id": "vitamin_d_plus",
        "name": "Vitamin D Plus",
        "category": "Ежедневный wellness-комплекс",
        "description": (
            "Информационная карточка для ознакомления с ассортиментом. Не является медицинской рекомендацией."
        ),
        "price": "от 990 ₽",
        "usage": "Только по инструкции производителя и с учетом личных ограничений.",
    },
    {
        "id": "magnesium_relax",
        "name": "Magnesium Relax",
        "category": "Поддержка образа жизни",
        "description": (
            "Описание ассортимента для клиентов. Не предназначено для диагностики, лечения или профилактики заболеваний."
        ),
        "price": "от 1 190 ₽",
        "usage": "Следуйте официальной инструкции производителя.",
    },
]

FAQ_TEXT = (
    "<b>FAQ</b>\n\n"
    "<b>1. Это магазин?</b>\n"
    "Это демонстрационный бот-каталог. Он показывает ассортимент и помогает оставить заявку на консультацию.\n\n"
    "<b>2. Можно ли оформить заказ прямо в боте?</b>\n"
    "В этой безопасной версии нет оформления заказа и приема оплаты. Клиент может оставить контакт, а менеджер свяжется отдельно.\n\n"
    "<b>3. Есть ли медицинские советы?</b>\n"
    "Нет. Бот не дает медицинских рекомендаций, не ставит диагнозы и не предлагает лечение.\n\n"
    "<b>4. Где хранится информация?</b>\n"
    "Контакты сохраняются в SQLite-базу на вашем сервере."
)

DISCLAIMER_TEXT = (
    "<b>Важно</b>\n\n"
    "Информация в боте предназначена только для ознакомления с ассортиментом. "
    "Она не заменяет консультацию врача или фармацевта. "
    "Нельзя использовать материалы бота для самодиагностики или назначения лечения. "
    "Перед применением любого продукта необходимо ознакомиться с официальной инструкцией производителя и противопоказаниями."
)


def init_db() -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                user_id INTEGER,
                username TEXT,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                product_name TEXT NOT NULL,
                comment TEXT
            )
            """
        )
        conn.commit()


def save_lead(user_id: int | None, username: str | None, full_name: str, phone: str, product_name: str, comment: str) -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO leads (created_at, user_id, username, full_name, phone, product_name, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(timespec="seconds"),
                user_id,
                username,
                full_name,
                phone,
                product_name,
                comment,
            ),
        )
        conn.commit()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📦 Каталог", callback_data="catalog")],
        [InlineKeyboardButton("📝 Оставить заявку", callback_data="lead_start")],
        [InlineKeyboardButton("❓ FAQ", callback_data="faq")],
        [InlineKeyboardButton("⚖️ Важная информация", callback_data="disclaimer")],
    ]
    return InlineKeyboardMarkup(keyboard)


def catalog_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(f"{item['name']} · {item['price']}", callback_data=f"product:{item['id']}")]
        for item in PRODUCTS
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="home")])
    return InlineKeyboardMarkup(keyboard)


def product_keyboard(product_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 Запросить консультацию", callback_data=f"lead_product:{product_id}")],
            [InlineKeyboardButton("⬅️ К каталогу", callback_data="catalog")],
        ]
    )


def get_product(product_id: str) -> Dict[str, str] | None:
    return next((item for item in PRODUCTS if item["id"] == product_id), None)


def product_card(product: Dict[str, str]) -> str:
    return (
        f"<b>{product['name']}</b>\n"
        f"Категория: {product['category']}\n"
        f"Цена: {product['price']}\n\n"
        f"{product['description']}\n\n"
        f"<b>Как использовать:</b> {product['usage']}\n\n"
        f"<i>Перед применением ознакомьтесь с инструкцией производителя.</i>"
    )


async def send_home(target, text: str) -> None:
    await target.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>Добро пожаловать в PharmaHeaven</b>\n\n"
        "Это подробный Telegram-бот для демонстрации wellness-ассортимента, FAQ и сбора заявок на консультацию.\n\n"
        "Выберите нужный раздел ниже."
    )
    await send_home(update.effective_message, text)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "home":
        await query.edit_message_text(
            "<b>PharmaHeaven</b>\n\nВыберите раздел:",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(),
        )
        return

    if data == "catalog":
        await query.edit_message_text(
            "<b>Каталог</b>\n\nВыберите карточку товара:",
            parse_mode=ParseMode.HTML,
            reply_markup=catalog_keyboard(),
        )
        return

    if data.startswith("product:"):
        product_id = data.split(":", 1)[1]
        product = get_product(product_id)
        if not product:
            await query.edit_message_text("Товар не найден.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text(
            product_card(product),
            parse_mode=ParseMode.HTML,
            reply_markup=product_keyboard(product_id),
        )
        return

    if data == "faq":
        await query.edit_message_text(
            FAQ_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="home")]]),
        )
        return

    if data == "disclaimer":
        await query.edit_message_text(
            DISCLAIMER_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="home")]]),
        )
        return


async def lead_start_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    product_name = "Не выбрано"
    data = query.data or ""
    if data.startswith("lead_product:"):
        product_id = data.split(":", 1)[1]
        product = get_product(product_id)
        if product:
            product_name = product["name"]

    context.user_data["lead"] = {"product_name": product_name}
    await query.message.reply_text("Как вас зовут?")
    return ASK_NAME


async def lead_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("lead", {})["full_name"] = (update.message.text or "").strip()
    await update.message.reply_text("Оставьте номер телефона или @username для связи.")
    return ASK_PHONE


async def lead_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("lead", {})["phone"] = (update.message.text or "").strip()

    current_product = context.user_data["lead"].get("product_name", "Не выбрано")
    prompt = (
        f"Укажите интересующий продукт. Сейчас выбрано: <b>{current_product}</b>\n"
        f"Можно написать название вручную."
    )
    await update.message.reply_text(prompt, parse_mode=ParseMode.HTML)
    return ASK_PRODUCT


async def lead_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("lead", {})["product_name"] = (update.message.text or "").strip()
    await update.message.reply_text("Добавьте комментарий к заявке или напишите '-' если без комментария.")
    return ASK_COMMENT


async def lead_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment = (update.message.text or "").strip()
    if comment == "-":
        comment = ""

    lead = context.user_data.get("lead", {})
    user = update.effective_user

    save_lead(
        user_id=user.id if user else None,
        username=user.username if user else None,
        full_name=lead.get("full_name", ""),
        phone=lead.get("phone", ""),
        product_name=lead.get("product_name", "Не указано"),
        comment=comment,
    )

    summary = (
        "<b>Заявка сохранена</b>\n\n"
        f"Имя: {lead.get('full_name', '')}\n"
        f"Контакт: {lead.get('phone', '')}\n"
        f"Продукт: {lead.get('product_name', 'Не указано')}\n"
        f"Комментарий: {comment or '—'}\n\n"
        "Менеджер сможет связаться с вами вручную."
    )
    await update.message.reply_text(summary, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())

    if ADMIN_CHAT_ID:
        admin_message = (
            "<b>Новая заявка PharmaHeaven</b>\n\n"
            f"Имя: {lead.get('full_name', '')}\n"
            f"Контакт: {lead.get('phone', '')}\n"
            f"Продукт: {lead.get('product_name', 'Не указано')}\n"
            f"Комментарий: {comment or '—'}\n"
            f"Telegram: @{user.username if user and user.username else 'нет username'}"
        )
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=admin_message, parse_mode=ParseMode.HTML)
        except Exception as exc:
            logger.warning("Failed to notify admin: %s", exc)

    context.user_data.pop("lead", None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("lead", None)
    await update.effective_message.reply_text("Действие отменено.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Команды:\n"
        "/start — главное меню\n"
        "/catalog — каталог\n"
        "/faq — частые вопросы\n"
        "/disclaimer — важная информация\n"
        "/lead — оставить заявку\n"
        "/cancel — отменить ввод"
    )
    await update.message.reply_text(text)


async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Каталог</b>\n\nВыберите карточку товара:",
        parse_mode=ParseMode.HTML,
        reply_markup=catalog_keyboard(),
    )


async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(FAQ_TEXT, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())


async def disclaimer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(DISCLAIMER_TEXT, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())


async def lead_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["lead"] = {"product_name": "Не выбрано"}
    await update.message.reply_text("Как вас зовут?")
    return ASK_NAME


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я понимаю команды и кнопки меню. Нажмите /start, чтобы открыть главное меню.",
        reply_markup=main_menu_keyboard(),
    )


def build_application() -> Application:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Environment variable BOT_TOKEN is required")

    application = ApplicationBuilder().token(token).build()

    lead_conv = ConversationHandler(
        entry_points=[
            CommandHandler("lead", lead_command),
            CallbackQueryHandler(lead_start_from_button, pattern=r"^(lead_start|lead_product:.+)$"),
        ],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_phone)],
            ASK_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_product)],
            ASK_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_comment)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
        per_user=True,
        per_message=False,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("catalog", catalog_command))
    application.add_handler(CommandHandler("faq", faq_command))
    application.add_handler(CommandHandler("disclaimer", disclaimer_command))
    application.add_handler(lead_conv)
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^(home|catalog|product:.+|faq|disclaimer)$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))

    return application


def export_products_json(filepath: str = "products.json") -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(PRODUCTS, f, ensure_ascii=False, indent=2)


def main() -> None:
    init_db()
    export_products_json()
    app = build_application()
    logger.info("PharmaHeaven bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
