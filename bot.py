import asyncio
import logging
import json
import os
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.client.default import DefaultBotProperties


# ---------------- НАСТРОЙКИ ----------------

logging.basicConfig(level=logging.INFO)

# Локально: вставь токен сюда.
# На сервере: задай переменную окружения BOT_TOKEN (она будет иметь приоритет).
FALLBACK_TOKEN = "PASTE_YOUR_TOKEN_HERE"

TOKEN = os.getenv("BOT_TOKEN") or FALLBACK_TOKEN
if not TOKEN or TOKEN == "PASTE_YOUR_TOKEN_HERE":
    raise RuntimeError(
        "Не задан токен. Локально вставь токен в FALLBACK_TOKEN, "
        "а на сервере задай переменную окружения BOT_TOKEN."
    )

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

CONTENT_RU_PATH = Path("data/content_ru.json")
CONTENT_KZ_PATH = Path("data/content_kz.json")

# user_id -> "ru" | "kz"
USER_LANG: dict[int, str] = {}


# ---------------- ЗАГРУЗКА КОНТЕНТА ----------------

def load_json(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"Не найден файл контента: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


CONTENT_RU = load_json(CONTENT_RU_PATH)
CONTENT_KZ = load_json(CONTENT_KZ_PATH)


def content_for(user_id: int) -> dict:
    lang = USER_LANG.get(user_id, "ru")
    return CONTENT_KZ if lang == "kz" else CONTENT_RU


def get_category_by_id(content: dict, cat_id: str) -> Optional[dict]:
    for c in content.get("categories", []):
        if c.get("id") == cat_id:
            return c
    return None


def render_category_text(content: dict, cat: dict) -> str:
    title = cat.get("title", cat.get("button", "Инструкция"))
    steps = cat.get("steps", [])
    important = cat.get("important", "")
    contacts = cat.get("contacts", [])
    laws = cat.get("laws", [])

    labels = content.get("labels", {})
    plan_label = labels.get("plan", "План действий")
    important_label = labels.get("important", "Важно")
    where_label = labels.get("where", "Куда обращаться")
    laws_label = labels.get("laws", "Нормы/законы")

    lines = [f"*{title}*", "", f"*{plan_label}:*"]
    for i, step in enumerate(steps, 1):
        lines.append(f"{i}. {step}")

    if important:
        lines.append("")
        lines.append(f"*{important_label}:* {important}")

    if contacts:
        lines.append("")
        lines.append(f"*{where_label}:*")
        for item in contacts:
            lines.append(f"• {item}")

    if laws:
        lines.append("")
        lines.append(f"*{laws_label}:*")
        for law in laws:
            lines.append(f"• {law}")

    return "\n".join(lines)


# ---------------- КЛАВИАТУРЫ ----------------

def lang_keyboard() -> InlineKeyboardMarkup:
    kb = [[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
        InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="set_lang:kz"),
    ]]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def main_keyboard(content: dict) -> InlineKeyboardMarkup:
    kb = []
    for cat in content.get("categories", []):
        cat_id = cat["id"]
        btn_text = cat.get("button", cat_id)

        # eGov/ЭЦП — отдельное подменю
        if cat_id == "egov_ecp_hacked":
            kb.append([InlineKeyboardButton(text=btn_text, callback_data="case_gos")])
        else:
            kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"case_json:{cat_id}")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def scenario_keyboard(content: dict, previous: str) -> InlineKeyboardMarkup:
    nav = content.get("nav", {})
    back_text = nav.get("back", "⬅️ Назад")
    home_text = nav.get("home", "🏠 В главное меню")

    kb = [
        [InlineKeyboardButton(text=back_text, callback_data=previous)],
        [InlineKeyboardButton(text=home_text, callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def gos_keyboard(content: dict) -> InlineKeyboardMarkup:
    gos = content.get("egov_submenu", {})
    kb = [
        [InlineKeyboardButton(text=gos.get("app", "💻 Установил приложение"), callback_data="gos_app")],
        [InlineKeyboardButton(text=gos.get("file", "⬇️ Скачал файл"), callback_data="gos_file")],
        [InlineKeyboardButton(text=gos.get("link", "🔗 Перешёл по ссылке / QR"), callback_data="gos_link")],
        [InlineKeyboardButton(text=gos.get("code", "📞 Сообщил код"), callback_data="gos_code")],
        [InlineKeyboardButton(text=gos.get("form", "📂 Внёс данные в форму"), callback_data="gos_form")],
        [InlineKeyboardButton(text=gos.get("site", "🌐 Действие на сайте/в приложении"), callback_data="gos_site")],
        [InlineKeyboardButton(text=gos.get("self", "💬 Сам сообщил данные"), callback_data="gos_self")],
        [InlineKeyboardButton(text=gos.get("back", "⬅️ Назад"), callback_data="back_main")],
        [InlineKeyboardButton(text=gos.get("other", "❓ Другое"), callback_data="gos_other")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ---------------- /start и выбор языка ----------------

@dp.message(F.text == "/start")
async def cmd_start(message: Message) -> None:
    # Если язык ещё не выбран — предлагаем выбор языка
    if message.from_user.id not in USER_LANG:
        await message.answer(content_for(message.from_user.id).get("choose_lang", "Выберите язык:"), reply_markup=lang_keyboard())
        return

    content = content_for(message.from_user.id)
    await message.answer(content.get("menu_title", "Меню"), reply_markup=main_keyboard(content))


@dp.callback_query(F.data.startswith("set_lang:"))
async def set_lang(callback: CallbackQuery) -> None:
    lang = callback.data.split(":", 1)[1]
    USER_LANG[callback.from_user.id] = "kz" if lang == "kz" else "ru"

    content = content_for(callback.from_user.id)
    await callback.message.edit_text(content.get("menu_title", "Меню"), reply_markup=main_keyboard(content))
    await callback.answer()


# ---------------- Категории из JSON ----------------

@dp.callback_query(F.data.startswith("case_json:"))
async def process_json_case(callback: CallbackQuery) -> None:
    content = content_for(callback.from_user.id)
    cat_id = callback.data.split(":", 1)[1]
    cat = get_category_by_id(content, cat_id)

    if not cat:
        await callback.answer(content.get("errors", {}).get("not_found", "Категория не найдена"), show_alert=True)
        return

    text = render_category_text(content, cat)
    await callback.message.edit_text(text, reply_markup=scenario_keyboard(content, "back_main"))
    await callback.answer()


# ---------------- eGov/ЭЦП подменю ----------------

@dp.callback_query(F.data == "case_gos")
async def open_gos_menu(callback: CallbackQuery) -> None:
    content = content_for(callback.from_user.id)
    await callback.message.edit_text(
        content.get("egov_title", "Как произошёл доступ к eGov/ЭЦП?"),
        reply_markup=gos_keyboard(content)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("gos_"))
async def process_gos(callback: CallbackQuery) -> None:
    content = content_for(callback.from_user.id)
    code = callback.data
    egov_texts = content.get("egov_texts", {})

    text = egov_texts.get(code) or egov_texts.get("gos_other") or "Нет инструкции."
    await callback.message.edit_text(text, reply_markup=scenario_keyboard(content, "case_gos"))
    await callback.answer()


# ---------------- Назад в меню ----------------

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery) -> None:
    content = content_for(callback.from_user.id)
    await callback.message.edit_text(content.get("menu_title", "Меню"), reply_markup=main_keyboard(content))
    await callback.answer()


# ---------------- ЗАПУСК ----------------

async def main() -> None:
    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
