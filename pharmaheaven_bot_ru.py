
"""
PharmaHeaven — безопасный шаблон Telegram-бота на русском языке.

ВАЖНО:
Этот бот НЕ оформляет заказы, НЕ принимает оплату и НЕ даёт медицинских обещаний.
Он подходит как:
- каталог продукции,
- FAQ-бот,
- сбор заявок на консультацию,
- витрина бренда с уведомлениями админу.

Совместим с python-telegram-bot 22.x
Документация: https://docs.python-telegram-bot.org/
"""

import asyncio
import html
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

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

# =========================
# НАСТРОЙКИ
# =========================
BOT_NAME = "PharmaHeaven"
DB_PATH = Path("pharmaheaven_requests.db")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID_RAW = os.getenv("ADMIN_CHAT_ID", "").strip()
ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_RAW) if ADMIN_CHAT_ID_RAW.lstrip("-").isdigit() else None

# Если есть @username менеджера или канал/чат для связи — можно указать:
MANAGER_CONTACT = os.getenv("MANAGER_CONTACT", "@your_manager")

BRAND_DESCRIPTION = (
    "Добро пожаловать в <b>PharmaHeaven</b>.\n\n"
    "Это информационный бот-каталог: здесь можно посмотреть ассортимент, "
    "ознакомиться с описаниями, прочитать FAQ и оставить заявку на консультацию."
)

DISCLAIMER_TEXT = (
    "⚠️ <b>Важная информация</b>\n\n"
    "• Информация в боте носит ознакомительный характер.\n"
    "• Бот не заменяет консультацию врача или иного квалифицированного специалиста.\n"
    "• Не используйте продукцию как способ диагностики, лечения или профилактики заболеваний без профессиональной консультации.\n"
    "• Перед применением внимательно изучайте состав, ограничения и индивидуальные противопоказания.\n"
    "• При беременности, кормлении грудью, приёме лекарств и наличии хронических состояний обязательно консультируйтесь со специалистом."
)

FAQ_ITEMS = [
    (
        "Что это за бот?",
        "Это русскоязычный каталог продукции PharmaHeaven с описаниями, FAQ и формой заявки на консультацию."
    ),
    (
        "Можно ли оформить заказ прямо в боте?",
        "В этом шаблоне оформление заказа и приём оплаты отключены. Бот только показывает каталог и собирает обращения."
    ),
    (
        "Кому приходит заявка?",
        "Если настроен ADMIN_CHAT_ID, заявка будет отправлена админу в Telegram и сохранится в SQLite-базе."
    ),
    (
        "Можно ли добавить фото товаров?",
        "Да. В коде предусмотрены поля image_url. При желании можно доработать отправку через send_photo."
    ),
    (
        "Можно ли подключить сайт, CRM или Google Sheets?",
        "Да. Этот шаблон легко расширяется: можно добавить вебхуки, Google Sheets API, CRM, админ-панель и аналитику."
    ),
]

PRODUCTS = [
    {
        "id": "omega3",
        "name": "Omega-3 Balance",
        "category": "Базовая поддержка",
        "subtitle": "Капсулы с омега-3",
        "description": (
            "Информационная карточка продукта для витрины.\n"
            "Подходит для демонстрации состава, формы выпуска и общих особенностей."
        ),
        "details": [
            "Форма: капсулы",
            "Категория: базовая поддержка рациона",
            "Упаковка: 60 капсул",
            "Особенности: удобно добавить состав, способ приёма и предупреждения",
        ],
        "image_url": "",
    },
    {
        "id": "magnesium",
        "name": "Magnesium Complex",
        "category": "Минералы",
        "subtitle": "Комплекс магния",
        "description": (
            "Карточка для раздела минералов. Можно указать форму магния, "
            "объём упаковки, особенности состава и общие сведения."
        ),
        "details": [
            "Форма: капсулы/таблетки",
            "Категория: минералы",
            "Упаковка: 90 капсул",
            "Особенности: можно добавить состав и рекомендации по ознакомлению с этикеткой",
        ],
        "image_url": "",
    },
    {
        "id": "vitamin_d3",
        "name": "Vitamin D3 Daily",
        "category": "Витамины",
        "subtitle": "Витамин D3",
        "description": (
            "Карточка витаминного продукта. Хорошо подходит для красивого описания, "
            "бренд-подачи и пояснений по формату выпуска."
        ),
        "details": [
            "Форма: капли/капсулы",
            "Категория: витамины",
            "Упаковка: 30 мл или 60 капсул",
            "Особенности: можно указать состав, формат хранения и служебные заметки",
        ],
        "image_url": "",
    },
    {
        "id": "collagen",
        "name": "Marine Collagen",
        "category": "Красота и уход",
        "subtitle": "Морской коллаген",
        "description": (
            "Пример карточки для beauty-направления. Можно адаптировать под порошок, "
            "саше, напитки или капсулы."
        ),
        "details": [
            "Форма: порошок/саше",
            "Категория: красота и уход",
            "Упаковка: 14 или 30 порций",
            "Особенности: можно добавить вкус, состав и формат применения",
        ],
        "image_url": "",
    },
]

# =========================
# СОСТОЯНИЯ ДИАЛОГА
# =========================
(
    REQUEST_NAME,
    REQUEST_PHONE,
    REQUEST_CITY,
    REQUEST_PRODUCT,
    REQUEST_COMMENT,
) = range(5)

# =========================
# ЛОГИРОВАНИЕ
# =========================
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# =========================
# БАЗА ДАННЫХ
# =========================
def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            user_id INTEGER,
            username TEXT,
            full_name TEXT,
            phone TEXT,
            city TEXT,
            product_interest TEXT,
            comment TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_request(data: dict[str, Any]) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO requests (
            created_at, user_id, username, full_name, phone, city, product_interest, comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            data.get("user_id"),
            data.get("username"),
            data.get("full_name"),
            data.get("phone"),
            data.get("city"),
            data.get("product_interest"),
            data.get("comment"),
        ),
    )
    request_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(request_id)


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📦 Каталог", callback_data="menu_catalog")],
            [InlineKeyboardButton("❓ FAQ", callback_data="menu_faq")],
            [InlineKeyboardButton("⚠️ Важная информация", callback_data="menu_disclaimer")],
            [InlineKeyboardButton("📝 Оставить заявку", callback_data="menu_request")],
            [InlineKeyboardButton("👤 Связаться с менеджером", callback_data="menu_manager")],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ В главное меню", callback_data="menu_home")]]
    )


def catalog_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for item in PRODUCTS:
        rows.append(
            [InlineKeyboardButton(f"• {item['name']}", callback_data=f"product_{item['id']}")]
        )
    rows.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


def faq_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for idx, item in enumerate(FAQ_ITEMS, start=1):
        rows.append(
            [InlineKeyboardButton(f"{idx}. {item[0]}", callback_data=f"faq_{idx-1}")]
        )
    rows.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


def request_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отменить заявку", callback_data="cancel_request")]]
    )


def find_product(product_id: str) -> dict[str, Any] | None:
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product
    return None


def product_card_text(product: dict[str, Any]) -> str:
    details = "\n".join(f"• {html.escape(line)}" for line in product.get("details", []))
    return (
        f"<b>{html.escape(product['name'])}</b>\n"
        f"<i>{html.escape(product['subtitle'])}</i>\n\n"
        f"<b>Категория:</b> {html.escape(product['category'])}\n\n"
        f"{html.escape(product['description'])}\n\n"
        f"<b>Подробности:</b>\n{details}\n\n"
        f"ℹ️ Для этого шаблона карточка носит информационный характер."
    )


async def send_or_edit(
    update: Update,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    else:
        assert update.message
        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


# =========================
# ОСНОВНЫЕ КОМАНДЫ
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        f"👋 <b>{BOT_NAME}</b>\n\n"
        f"{BRAND_DESCRIPTION}\n\n"
        "Выберите нужный раздел ниже:"
    )
    await send_or_edit(update, text, main_menu_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>Команды бота</b>\n\n"
        "/start — открыть главное меню\n"
        "/help — показать справку\n"
        "/catalog — открыть каталог\n"
        "/faq — часто задаваемые вопросы\n"
        "/disclaimer — важная информация\n"
        "/request — оставить заявку"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📦 <b>Каталог продукции</b>\n\nВыберите интересующий товар:",
        reply_markup=catalog_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "❓ <b>FAQ</b>\n\nВыберите вопрос:",
        reply_markup=faq_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def disclaimer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        DISCLAIMER_TEXT,
        reply_markup=back_to_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )


# =========================
# CALLBACK-МЕНЮ
# =========================
async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    query = update.callback_query
    if not query:
        return None

    data = query.data

    if data == "menu_home":
        await start(update, context)
        return None

    if data == "menu_catalog":
        await send_or_edit(
            update,
            "📦 <b>Каталог продукции</b>\n\nВыберите интересующий товар:",
            catalog_keyboard(),
        )
        return None

    if data == "menu_faq":
        await send_or_edit(
            update,
            "❓ <b>FAQ</b>\n\nВыберите вопрос:",
            faq_keyboard(),
        )
        return None

    if data == "menu_disclaimer":
        await send_or_edit(update, DISCLAIMER_TEXT, back_to_menu_keyboard())
        return None

    if data == "menu_manager":
        text = (
            "👤 <b>Связь с менеджером</b>\n\n"
            f"Напишите менеджеру: {html.escape(MANAGER_CONTACT)}\n\n"
            "Либо вернитесь в меню и оставьте заявку — администратор получит уведомление."
        )
        await send_or_edit(update, text, back_to_menu_keyboard())
        return None

    if data.startswith("product_"):
        product_id = data.replace("product_", "", 1)
        product = find_product(product_id)
        if not product:
            await send_or_edit(
                update,
                "Товар не найден.",
                back_to_menu_keyboard(),
            )
            return None

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📝 Оставить заявку по этому товару", callback_data=f"request_product_{product_id}")],
                [InlineKeyboardButton("⬅️ К каталогу", callback_data="menu_catalog")],
            ]
        )
        await send_or_edit(update, product_card_text(product), keyboard)
        return None

    if data.startswith("faq_"):
        idx = int(data.replace("faq_", "", 1))
        question, answer = FAQ_ITEMS[idx]
        text = f"❓ <b>{html.escape(question)}</b>\n\n{html.escape(answer)}"
        await send_or_edit(
            update,
            text,
            InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("⬅️ К FAQ", callback_data="menu_faq")],
                    [InlineKeyboardButton("⬅️ В главное меню", callback_data="menu_home")],
                ]
            ),
        )
        return None

    return None


# =========================
# ЗАЯВКА
# =========================
async def request_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["request_data"] = {}

    query = update.callback_query
    product_from_callback = None

    if query and query.data and query.data.startswith("request_product_"):
        product_id = query.data.replace("request_product_", "", 1)
        product = find_product(product_id)
        if product:
            product_from_callback = product["name"]
            context.user_data["request_data"]["product_interest"] = product_from_callback

    text = (
        "📝 <b>Оформление заявки на консультацию</b>\n\n"
        "Шаг 1 из 5.\n"
        "Пожалуйста, напишите ваше имя."
    )

    if query:
        await query.answer()
        await query.edit_message_text(
            text=text,
            reply_markup=request_cancel_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    else:
        assert update.message
        await update.message.reply_text(
            text,
            reply_markup=request_cancel_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    return REQUEST_NAME


async def request_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message
    name = update.message.text.strip()
    context.user_data.setdefault("request_data", {})["full_name"] = name

    await update.message.reply_text(
        "Шаг 2 из 5.\nПожалуйста, отправьте телефон или другой удобный контакт.",
        reply_markup=request_cancel_keyboard(),
    )
    return REQUEST_PHONE


async def request_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message
    phone = update.message.text.strip()
    context.user_data.setdefault("request_data", {})["phone"] = phone

    await update.message.reply_text(
        "Шаг 3 из 5.\nИз какого вы города?",
        reply_markup=request_cancel_keyboard(),
    )
    return REQUEST_CITY


async def request_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message
    city = update.message.text.strip()
    context.user_data.setdefault("request_data", {})["city"] = city

    existing_product = context.user_data.get("request_data", {}).get("product_interest")
    if existing_product:
        await update.message.reply_text(
            f"Шаг 4 из 5.\nТовар уже выбран: <b>{html.escape(existing_product)}</b>\n"
            "Если хотите, можете написать другой интересующий продукт или категорию.",
            reply_markup=request_cancel_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "Шаг 4 из 5.\nКакой товар или категория вас интересует?",
            reply_markup=request_cancel_keyboard(),
        )
    return REQUEST_PRODUCT


async def request_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message
    product_interest = update.message.text.strip()
    context.user_data.setdefault("request_data", {})["product_interest"] = product_interest

    await update.message.reply_text(
        "Шаг 5 из 5.\nДобавьте комментарий: например, удобное время для связи или ваш вопрос.\n"
        "Если комментария нет, напишите: -",
        reply_markup=request_cancel_keyboard(),
    )
    return REQUEST_COMMENT


async def request_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message

    req = context.user_data.setdefault("request_data", {})
    req["comment"] = update.message.text.strip()
    req["user_id"] = update.effective_user.id if update.effective_user else None
    req["username"] = update.effective_user.username if update.effective_user else None

    request_id = save_request(req)

    summary = (
        "✅ <b>Заявка сохранена</b>\n\n"
        f"<b>ID заявки:</b> {request_id}\n"
        f"<b>Имя:</b> {html.escape(req.get('full_name', ''))}\n"
        f"<b>Контакт:</b> {html.escape(req.get('phone', ''))}\n"
        f"<b>Город:</b> {html.escape(req.get('city', ''))}\n"
        f"<b>Интерес:</b> {html.escape(req.get('product_interest', ''))}\n"
        f"<b>Комментарий:</b> {html.escape(req.get('comment', ''))}\n\n"
        "С вами свяжутся после обработки обращения."
    )

    await update.message.reply_text(
        summary,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )

    if ADMIN_CHAT_ID:
        admin_text = (
            "📥 <b>Новая заявка в PharmaHeaven</b>\n\n"
            f"<b>ID:</b> {request_id}\n"
            f"<b>Имя:</b> {html.escape(req.get('full_name', ''))}\n"
            f"<b>Контакт:</b> {html.escape(req.get('phone', ''))}\n"
            f"<b>Город:</b> {html.escape(req.get('city', ''))}\n"
            f"<b>Интерес:</b> {html.escape(req.get('product_interest', ''))}\n"
            f"<b>Комментарий:</b> {html.escape(req.get('comment', ''))}\n"
            f"<b>User ID:</b> {req.get('user_id')}\n"
            f"<b>Username:</b> @{html.escape(req.get('username', '')) if req.get('username') else 'нет'}"
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Не удалось отправить уведомление админу")

    context.user_data.pop("request_data", None)
    return ConversationHandler.END


async def request_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("request_data", None)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "❌ Заявка отменена.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        assert update.message
        await update.message.reply_text(
            "❌ Заявка отменена.",
            reply_markup=main_menu_keyboard(),
        )
    return ConversationHandler.END


# =========================
# ОБРАБОТКА ОШИБОК
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Ошибка при обработке апдейта:", exc_info=context.error)


# =========================
# СБОРКА ПРИЛОЖЕНИЯ
# =========================
def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не задана. "
            "Установите токен и запустите бота снова."
        )

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("request", request_start),
            CallbackQueryHandler(request_start, pattern=r"^menu_request$"),
            CallbackQueryHandler(request_start, pattern=r"^request_product_.+$"),
        ],
        states={
            REQUEST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_name)],
            REQUEST_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_phone)],
            REQUEST_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_city)],
            REQUEST_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_product)],
            REQUEST_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_comment)],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(request_cancel, pattern=r"^cancel_request$"),
        ],
        per_chat=True,
        per_user=True,
        per_message=False,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("catalog", catalog_command))
    application.add_handler(CommandHandler("faq", faq_command))
    application.add_handler(CommandHandler("disclaimer", disclaimer_command))

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(menu_router))

    application.add_error_handler(error_handler)
    return application


async def main() -> None:
    init_db()
    application = build_application()
    logger.info("Бот %s запускается...", BOT_NAME)
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("Бот запущен.")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
