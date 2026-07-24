#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import html
import logging
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from deep_translator import GoogleTranslator
from db import (
    init_db, save_request, get_request_by_id,
    get_requests_due_for_reminder, mark_reminded,
    extend_request, close_request,
    set_build_link, set_pin_code, set_calibration_plan, set_demo_status,
    get_active_requests
)

# === НАСТРОЙКИ ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===
load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан. Укажите его в .env или переменных окружения.")

# Локальный прокси (например, socks5://127.0.0.1:10808) — нужен только если
# api.telegram.org напрямую недоступен (например, при локальной разработке в РФ).
BOT_PROXY = os.environ.get("BOT_PROXY")

MAIN_CHAT_ID = -1003345325031

TOPIC_IDS = {
    "global": 3,
    "russia_sng": 4,
    "china": 5
}

# ID топика "Discussion", куда отправляется еженедельный отчёт по активным демо.
# Узнать: отправить /topicid прямо в этом топике.
# "general" — Discussion является General-топиком (топик по умолчанию), у него нет
# message_thread_id, сообщения в него отправляются вообще без этого параметра.
DISCUSSION_TOPIC_ID = "general"

TOPIC_LABELS = {
    TOPIC_IDS["global"]: "🌍 Global",
    TOPIC_IDS["russia_sng"]: "🇷🇺 Russia/SNG",
    TOPIC_IDS["china"]: "🇨🇳 China",
}

MOSCOW_TZ = timezone(timedelta(hours=3))
WEEKLY_REPORT_WEEKDAY = 0  # понедельник
WEEKLY_REPORT_HOUR = 10

REMINDER_HOURS_BEFORE = 24
REMINDER_CHECK_INTERVAL_SECONDS = 3600

DURATION_LABELS = {
    "1": "1 день", "3": "3 дня", "5": "5 дней",
    "7": "7 дней", "10": "10 дней", "14": "14 дней"
}

STATUS_CODES = ["build_sent", "partner_launching", "partner_no_response", "setup", "other"]

REQUEST_MANAGEMENT = {
    "ru": {
        "btn_build": "🔗 Билд",
        "btn_calibration": "📋 Калибровка",
        "btn_status": "📊 Статус",
        "btn_back": "⬅️ Назад",
        "btn_extend": "🔄 Продлить",
        "btn_close": "⛔ Отключить в указанную дату",
        "btn_cancel": "❌ Отмена",
        "duration_labels": {
            "1": "1 день", "3": "3 дня", "5": "5 дней",
            "7": "7 дней", "10": "10 дней", "14": "14 дней"
        },
        "btn_pin": "📌 PIN-код",
        "prompt_build": "Введите ссылку на билд:",
        "prompt_pin": "Введите PIN-код:",
        "prompt_calibration": "Введите план калибровки:",
        "prompt_status_other": "Введите статус:",
        "status_build_sent": "🚀 Билд отправлен",
        "status_partner_launching": "🟡 Партнёр запускает",
        "status_partner_no_response": "🔴 Партнёр не вышел на связь",
        "status_setup": "🔧 Настройка",
        "status_other": "❓ Другое",
        "label_build": "Билд",
        "label_pin": "PIN-код",
        "label_calibration": "План калибровки",
        "label_status": "Статус демо",
        "updated": "обновлено",
    },
    "en": {
        "btn_build": "🔗 Build",
        "btn_calibration": "📋 Calibration",
        "btn_status": "📊 Status",
        "btn_back": "⬅️ Back",
        "btn_extend": "🔄 Extend",
        "btn_close": "⛔ Disable on scheduled date",
        "btn_cancel": "❌ Cancel",
        "duration_labels": {
            "1": "1 day", "3": "3 days", "5": "5 days",
            "7": "7 days", "10": "10 days", "14": "14 days"
        },
        "btn_pin": "📌 PIN code",
        "prompt_build": "Enter the build link:",
        "prompt_pin": "Enter the PIN code:",
        "prompt_calibration": "Enter the calibration plan:",
        "prompt_status_other": "Enter the status:",
        "status_build_sent": "🚀 Build sent",
        "status_partner_launching": "🟡 Partner launching",
        "status_partner_no_response": "🔴 Partner not responding",
        "status_setup": "🔧 Setup",
        "status_other": "❓ Other",
        "label_build": "Build",
        "label_pin": "PIN code",
        "label_calibration": "Calibration plan",
        "label_status": "Demo status",
        "updated": "updated",
    },
    "zh": {
        "btn_build": "🔗 构建",
        "btn_calibration": "📋 校准",
        "btn_status": "📊 状态",
        "btn_back": "⬅️ 返回",
        "btn_extend": "🔄 延长",
        "btn_close": "⛔ 按计划日期关闭",
        "btn_cancel": "❌ 取消",
        "duration_labels": {
            "1": "1 天", "3": "3 天", "5": "5 天",
            "7": "7 天", "10": "10 天", "14": "14 天"
        },
        "btn_pin": "📌 PIN码",
        "prompt_build": "请输入构建链接:",
        "prompt_pin": "请输入PIN码:",
        "prompt_calibration": "请输入校准计划:",
        "prompt_status_other": "请输入状态:",
        "status_build_sent": "🚀 已发送构建",
        "status_partner_launching": "🟡 合作伙伴正在启动",
        "status_partner_no_response": "🔴 合作伙伴未回应",
        "status_setup": "🔧 设置",
        "status_other": "❓ 其他",
        "label_build": "构建",
        "label_pin": "PIN码",
        "label_calibration": "校准计划",
        "label_status": "演示状态",
        "updated": "已更新",
    },
}


def get_management_texts(lang_code: str) -> dict:
    return REQUEST_MANAGEMENT.get(lang_code, REQUEST_MANAGEMENT["ru"])


# === ЛОКАЛИЗАЦИЯ ===
MESSAGES = {
    "start_choose_lang": "👋 Добро пожаловать! Пожалуйста, выберите язык.\n\n"
                         "👋 Welcome! Please choose your language.\n\n"
                         "👋 欢迎！请选择语言。",
    "lang_selected": {
        "ru": "🇷🇺 Выбран русский язык.",
        "en": "🇺🇸 English selected.",
        "zh": "🇨🇳 中文已选择。"
    },
    "choose_server": {
        "ru": "🌍 Выберите сервер для демо-запроса:",
        "en": "🌍 Choose a server for the demo request:",
        "zh": "🌍 请选择演示服务器："
    },
    "ask_server_version": {
        "ru": "📦 Выберите версию сервера:",
        "en": "📦 Choose server version:",
        "zh": "📦 请选择服务器版本："
    },
    "ask_area": {
        "ru": "📐 Выберите размер игровой площадки:",
        "en": "📐 Choose game area size:",
        "zh": "📐 请选择游戏区域尺寸"
    },
    "ask_vr_device": {
        "ru": "👓 Выберите VR-шлем:",
        "en": "👓 Choose VR headset:",
        "zh": "👓 请选择 VR 头显："
    },
    "ask_partner_contact": {
        "ru": "📎 Хотите добавить контактные данные партнёра?",
        "en": "📎 Would you like to add partner contact details?",
        "zh": "📎 是否要添加合作伙伴联系信息？"
    },
    "partner_contact_yes": {
        "ru": "✅ Да, добавить",
        "en": "✅ Yes, add",
        "zh": "✅ 是，添加"
    },
    "partner_contact_no": {
        "ru": "❌ Нет, пропустить",
        "en": "❌ No, skip",
        "zh": "❌ 否，跳过"
    },
    "ask_partner_name": {
        "ru": "👤 Введите имя партнёра:",
        "en": "👤 Enter partner name:",
        "zh": "👤 请输入合作伙伴姓名："
    },
    "ask_partner_phone": {
        "ru": "📱 Введите номер телефона партнёра:",
        "en": "📱 Enter partner phone number:",
        "zh": "📱 请输入合作伙伴电话号码："
    },
    "ask_partner_email": {
        "ru": "📧 Введите email партнёра:",
        "en": "📧 Enter partner email:",
        "zh": "📧 请输入合作伙伴电子邮件："
    },
    "ask_partner_crm": {
        "ru": "🔗 Введите ссылку на CRM партнёра:",
        "en": "🔗 Enter partner CRM link:",
        "zh": "🔗 请输入合作伙伴CRM链接："
    },
    "ask_city": {
        "ru": "🌍 Укажите страну / город:",
        "en": "🌍 Enter country / city:",
        "zh": "🌍 请输入国家 / 城市："
    },
    "ask_duration": {
        "ru": "⏳ Укажите срок действия демо игры:",
        "en": "⏳ Enter demo validity period:",
        "zh": "⏳ 请输入演示有效期："
    },
    "ask_comment": {
        "ru": "✏️ Добавить комментарий (опционально):",
        "en": "✏️ Add a comment (optional):",
        "zh": "✏️ 添加评论（可选）："
    },
    "enter_comment": {
        "ru": "Введите комментарий:",
        "en": "Enter comment:",
        "zh": "请输入评论："
    },
    "send_without_comment": {
        "ru": "✅ Отправить без комментария",
        "en": "✅ Send without comment",
        "zh": "✅ 发送，无需评论"
    },
    "success_with_link": {
        "ru": "✅ Запрос успешно оформлен и отправлен в раздел <a href='{link}'>[перейти к запросу]</a>",
        "en": "✅ Request successfully submitted and sent to section <a href='{link}'>[go to request]</a>",
        "zh": "✅ 请求已成功提交并发送至分区 <a href='{link}'>[跳转到请求]</a>"
    },
    "buttons": {
        "lang": {
            "ru": {"lang_ru": "🇷🇺 Русский", "lang_en": "🇺🇸 English", "lang_zh": "🇨🇳 中文"},
            "en": {"lang_ru": "🇷 Russian", "lang_en": "🇺🇸 English", "lang_zh": "🇨🇳 Chinese"},
            "zh": {"lang_ru": "🇷🇺 俄语", "lang_en": "🇺 English", "lang_zh": "🇨🇳 中文"}
        },
        "server": {
            "ru": {"server_usd": "🇺🇸 Сервер USD", "server_eud": "🇪🇺 Сервер EUD", "server_rud": "🇷 Сервер RUD", "server_chd": "🇨🇳 Сервер CHD"},
            "en": {"server_usd": "🇺 Server USD", "server_eud": "🇪🇺 Server EUD", "server_rud": "🇷🇺 Server RUD", "server_chd": "🇨🇳 Server CHD"},
            "zh": {"server_usd": "🇺 服务器 USD", "server_eud": "🇪🇺 服务器 EUD", "server_rud": "🇷🇺 服务器 RUD", "server_chd": "🇨 服务器 CHD"}
        },
        "server_version": {
            "ru": {"ver_1272": "📦 1.2.7.2", "ver_1281": "🚀 1.2.8.1", "ver_130": "✨ 1.3.0"},
            "en": {"ver_1272": "📦 1.2.7.2", "ver_1281": "🚀 1.2.8.1", "ver_130": "✨ 1.3.0"},
            "zh": {"ver_1272": "📦 1.2.7.2", "ver_1281": "🚀 1.2.8.1", "ver_130": "✨ 1.3.0"}
        },
        "vr_device": {
            "ru": {"vr_quest2": "🔵 Meta Quest 2", "vr_quest3": "🔵 Meta Quest 3/3s", "vr_pico4": "🟣 Pico 4", "vr_pico4ultra": "🟣 Pico 4 Ultra/Ultra Enterprise"},
            "en": {"vr_quest2": "🔵 Meta Quest 2", "vr_quest3": "🔵 Meta Quest 3/3s", "vr_pico4": "🟣 Pico 4", "vr_pico4ultra": "🟣 Pico 4 Ultra/Ultra Enterprise"},
            "zh": {"vr_quest2": "🔵 Meta Quest 2", "vr_quest3": "🔵 Meta Quest 3/3s", "vr_pico4": "🟣 Pico 4", "vr_pico4ultra": "🟣 Pico 4 Ultra/Ultra Enterprise"}
        },
        "duration": {
            "ru": {"dur_1": "1 день", "dur_3": "3 дня", "dur_5": "5 дней", "dur_7": "7 дней", "dur_10": "10 дней", "dur_14": "14 дней"},
            "en": {"dur_1": "1 day", "dur_3": "3 days", "dur_5": "5 days", "dur_7": "7 days", "dur_10": "10 days", "dur_14": "14 days"},
            "zh": {"dur_1": "1 天", "dur_3": "3 天", "dur_5": "5 天", "dur_7": "7 天", "dur_10": "10 天", "dur_14": "14 天"}
        },
        "comment": {
            "ru": "✏️ Добавить комментарий",
            "en": "✏️ Add comment",
            "zh": "✏️ 添加评论"
        },
        "back": {
            "ru": "⬅️ Назад",
            "en": "⬅️ Back",
            "zh": "⬅️ 返回"
        }
    }
}

AREA_SIZES_LEGACY_GLOBAL = ["4x8", "6x6", "8x8", "9x6", "10x7", "10x10", "10x12", "10x15"]
AREA_SIZES_LEGACY_CHD = ["4x8", "6x6", "7x15", "8x8", "8x12", "9x6", "10x7", "10x10", "10x12", "10x15"]
AREA_SIZES_NEW = [
    "4x8", "5x7", "5x10", "6x6", "6x8", "7x15", "8x8", "8x12",
    "9x6", "9x12", "10x7", "10x10", "10x12", "10x15"
]

bot = Bot(token=BOT_TOKEN, session=AiohttpSession(proxy=BOT_PROXY) if BOT_PROXY else None)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class Form(StatesGroup):
    language = State()
    server_type = State()
    server_version = State()
    area_size = State()
    vr_device = State()
    partner_contact = State()
    partner_name = State()
    partner_phone = State()
    partner_email = State()
    partner_crm = State()
    city = State()
    duration = State()
    comment = State()


class RequestEdit(StatesGroup):
    build_link = State()
    pin_code = State()
    calibration_plan = State()
    demo_status_other = State()


RU_MONTHS_GENITIVE = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}


def format_ru_date(dt: datetime) -> str:
    return f"{dt.day:02d} {RU_MONTHS_GENITIVE[dt.month]} {dt.year}"


# === ПЕРЕВОД ===
def translate_to_russian(text: str, source_lang: str) -> str:
    """Безопасный перевод с обработкой ошибок"""
    if not text or source_lang == "ru":
        return text
    try:
        src = 'zh-CN' if source_lang == "zh" else 'en'
        translator = GoogleTranslator(source=src, target='ru')
        return translator.translate(text)
    except Exception as e:
        logger.error(f"Ошибка перевода '{text}': {e}")
        return text


# === КЛАВИАТУРЫ ===
def get_lang_keyboard(lang_code):
    b = MESSAGES["buttons"]["lang"][lang_code]
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=b["lang_ru"], callback_data="lang_ru")],
        [types.InlineKeyboardButton(text=b["lang_en"], callback_data="lang_en")],
        [types.InlineKeyboardButton(text=b["lang_zh"], callback_data="lang_zh")]
    ])


def get_server_keyboard(lang_code):
    b = MESSAGES["buttons"]["server"][lang_code]
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=b["server_usd"], callback_data="server_usd")],
        [types.InlineKeyboardButton(text=b["server_eud"], callback_data="server_eud")],
        [types.InlineKeyboardButton(text=b["server_rud"], callback_data="server_rud")],
        [types.InlineKeyboardButton(text=b["server_chd"], callback_data="server_chd")],
        [types.InlineKeyboardButton(text=MESSAGES["buttons"]["back"][lang_code], callback_data="back")]
    ])


def get_version_keyboard(lang_code):
    b = MESSAGES["buttons"]["server_version"][lang_code]
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=b["ver_1272"], callback_data="ver_1272")],
        [types.InlineKeyboardButton(text=b["ver_1281"], callback_data="ver_1281")],
        [types.InlineKeyboardButton(text=b["ver_130"], callback_data="ver_130")],
        [types.InlineKeyboardButton(text=MESSAGES["buttons"]["back"][lang_code], callback_data="back")]
    ])


def get_area_keyboard(lang_code, server_type, server_version):
    if server_version == "1.3.0":
        sizes = AREA_SIZES_NEW
    else:
        sizes = AREA_SIZES_LEGACY_CHD if server_type == "CHD" else AREA_SIZES_LEGACY_GLOBAL
    buttons = [[types.InlineKeyboardButton(text=size, callback_data=f"area_{size}")] for size in sizes]
    buttons.append([types.InlineKeyboardButton(text=MESSAGES["buttons"]["back"][lang_code], callback_data="back")])
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def get_vr_keyboard(lang_code):
    b = MESSAGES["buttons"]["vr_device"][lang_code]
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=b["vr_quest2"], callback_data="vr_quest2")],
        [types.InlineKeyboardButton(text=b["vr_quest3"], callback_data="vr_quest3")],
        [types.InlineKeyboardButton(text=b["vr_pico4"], callback_data="vr_pico4")],
        [types.InlineKeyboardButton(text=b["vr_pico4ultra"], callback_data="vr_pico4ultra")],
        [types.InlineKeyboardButton(text=MESSAGES["buttons"]["back"][lang_code], callback_data="back")]
    ])


def get_partner_keyboard(lang_code):
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=MESSAGES["partner_contact_yes"][lang_code], callback_data="partner_yes")],
        [types.InlineKeyboardButton(text=MESSAGES["partner_contact_no"][lang_code], callback_data="partner_no")],
        [types.InlineKeyboardButton(text=MESSAGES["buttons"]["back"][lang_code], callback_data="back")]
    ])


def get_duration_keyboard(lang_code):
    b = MESSAGES["buttons"]["duration"][lang_code]
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=b["dur_1"], callback_data="dur_1")],
        [types.InlineKeyboardButton(text=b["dur_3"], callback_data="dur_3")],
        [types.InlineKeyboardButton(text=b["dur_5"], callback_data="dur_5")],
        [types.InlineKeyboardButton(text=b["dur_7"], callback_data="dur_7")],
        [types.InlineKeyboardButton(text=b["dur_10"], callback_data="dur_10")],
        [types.InlineKeyboardButton(text=b["dur_14"], callback_data="dur_14")],
        [types.InlineKeyboardButton(text=MESSAGES["buttons"]["back"][lang_code], callback_data="back")]
    ])


def get_comment_keyboard(lang_code):
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=MESSAGES["buttons"]["comment"][lang_code], callback_data="add_comment")],
        [types.InlineKeyboardButton(text=MESSAGES["send_without_comment"][lang_code], callback_data="send_without_comment")],
        [types.InlineKeyboardButton(text=MESSAGES["buttons"]["back"][lang_code], callback_data="back")]
    ])


def back_keyboard(lang_code):
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=MESSAGES["buttons"]["back"][lang_code], callback_data="back")]
    ])


# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    logger.info(f"Команда /start от пользователя {message.from_user.id}")
    
    if message.chat.type != "private":
        bot_info = await bot.get_me()
        builder = InlineKeyboardBuilder()
        msg_text = (
            "🤖 Заполнение формы доступно только в личном чате с ботом.\n\n"
            "🤖 Form submission is only available in a private chat with the bot.\n\n"
            "🤖 表单填写仅限与机器人私聊。"
        )
        builder.button(text="Contact the bot", url=f"https://t.me/{bot_info.username}")
        await message.answer(msg_text, reply_markup=builder.as_markup(), disable_web_page_preview=True)
        return

    await state.clear()
    await message.answer(MESSAGES["start_choose_lang"], reply_markup=get_lang_keyboard("ru"))
    await state.set_state(Form.language)


@dp.callback_query(lambda c: c.data.startswith("lang_"))
async def process_language(callback: types.CallbackQuery, state: FSMContext):
    lang_map = {"lang_ru": "ru", "lang_en": "en", "lang_zh": "zh"}
    lang_code = lang_map.get(callback.data)
    if not lang_code:
        logger.warning(f"Неверный выбор языка: {callback.data}")
        await callback.answer("Ошибка выбора языка", show_alert=True)
        return
    await state.update_data(language=lang_code)
    await callback.message.edit_text(MESSAGES["choose_server"][lang_code], reply_markup=get_server_keyboard(lang_code))
    await state.set_state(Form.server_type)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("server_"))
async def process_server_type(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang_code = data.get("language", "en")
    server_map = {
        "server_usd": ("USD", TOPIC_IDS["global"]),
        "server_eud": ("EUD", TOPIC_IDS["global"]),
        "server_rud": ("RUD", TOPIC_IDS["russia_sng"]),
        "server_chd": ("CHD", TOPIC_IDS["china"]),
    }
    server_info = server_map.get(callback.data)
    if not server_info:
        logger.warning(f"Неверный выбор сервера: {callback.data}")
        await callback.answer("Ошибка выбора сервера", show_alert=True)
        return
    server_type, topic_id = server_info
    await state.update_data(server_type=server_type, topic_id=topic_id)
    await callback.message.edit_text(MESSAGES["ask_server_version"][lang_code], reply_markup=get_version_keyboard(lang_code))
    await state.set_state(Form.server_version)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("ver_"))
async def process_server_version(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang_code = data.get("language", "en")
    version = {"ver_1272": "1.2.7.2", "ver_1281": "1.2.8.1", "ver_130": "1.3.0"}.get(callback.data)
    if not version:
        logger.warning(f"Неверный выбор версии: {callback.data}")
        await callback.answer("Ошибка выбора версии", show_alert=True)
        return
    await state.update_data(server_version=version)
    server_type = data.get("server_type")
    await callback.message.edit_text(MESSAGES["ask_area"][lang_code], reply_markup=get_area_keyboard(lang_code, server_type, version))
    await state.set_state(Form.area_size)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("area_"))
async def process_area_size(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang_code = data.get("language", "en")
    area_size = callback.data.replace("area_", "")
    await state.update_data(area_size=area_size)
    await callback.message.edit_text(MESSAGES["ask_vr_device"][lang_code], reply_markup=get_vr_keyboard(lang_code))
    await state.set_state(Form.vr_device)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("vr_"))
async def process_vr_device(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang_code = data.get("language", "en")
    vr_map = {
        "vr_quest2": "Meta Quest 2",
        "vr_quest3": "Meta Quest 3/3s",
        "vr_pico4": "Pico 4",
        "vr_pico4ultra": "Pico 4 Ultra/Ultra Enterprise"
    }
    vr_device = vr_map.get(callback.data)
    if not vr_device:
        logger.warning(f"Неверный выбор VR: {callback.data}")
        await callback.answer("Ошибка выбора VR", show_alert=True)
        return
    await state.update_data(vr_device=vr_device)
    await callback.message.edit_text(MESSAGES["ask_partner_contact"][lang_code], reply_markup=get_partner_keyboard(lang_code))
    await state.set_state(Form.partner_contact)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "partner_yes")
async def partner_yes(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang_code = data.get("language", "en")
    await callback.message.edit_text(MESSAGES["ask_partner_name"][lang_code], reply_markup=back_keyboard(lang_code))
    await state.set_state(Form.partner_name)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "partner_no")
async def partner_no(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(partner_name=None, partner_phone=None, partner_email=None, partner_crm=None)
    data = await state.get_data()
    lang_code = data.get("language", "en")
    await callback.message.edit_text(MESSAGES["ask_city"][lang_code], reply_markup=back_keyboard(lang_code))
    await state.set_state(Form.city)
    await callback.answer()


@dp.message(Form.partner_name)
async def process_partner_name(message: types.Message, state: FSMContext):
    await state.update_data(partner_name=message.text.strip() or None)
    data = await state.get_data()
    lang_code = data.get("language", "en")
    await message.answer(MESSAGES["ask_partner_phone"][lang_code], reply_markup=back_keyboard(lang_code))
    await state.set_state(Form.partner_phone)


@dp.message(Form.partner_phone)
async def process_partner_phone(message: types.Message, state: FSMContext):
    await state.update_data(partner_phone=message.text.strip() or None)
    data = await state.get_data()
    lang_code = data.get("language", "en")
    await message.answer(MESSAGES["ask_partner_email"][lang_code], reply_markup=back_keyboard(lang_code))
    await state.set_state(Form.partner_email)


@dp.message(Form.partner_email)
async def process_partner_email(message: types.Message, state: FSMContext):
    await state.update_data(partner_email=message.text.strip() or None)
    data = await state.get_data()
    lang_code = data.get("language", "en")
    await message.answer(MESSAGES["ask_partner_crm"][lang_code], reply_markup=back_keyboard(lang_code))
    await state.set_state(Form.partner_crm)


@dp.message(Form.partner_crm)
async def process_partner_crm(message: types.Message, state: FSMContext):
    await state.update_data(partner_crm=message.text.strip() or None)
    data = await state.get_data()
    lang_code = data.get("language", "en")
    await message.answer(MESSAGES["ask_city"][lang_code], reply_markup=back_keyboard(lang_code))
    await state.set_state(Form.city)


@dp.message(Form.city)
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    data = await state.get_data()
    lang_code = data.get("language", "en")
    await message.answer(MESSAGES["ask_duration"][lang_code], reply_markup=get_duration_keyboard(lang_code))
    await state.set_state(Form.duration)


@dp.callback_query(lambda c: c.data.startswith("dur_"))
async def process_duration(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang_code = data.get("language", "en")
    duration_map = {
        "dur_1": "1", "dur_3": "3", "dur_5": "5",
        "dur_7": "7", "dur_10": "10", "dur_14": "14"
    }
    duration = duration_map.get(callback.data)
    if not duration:
        logger.warning(f"Неверный выбор срока: {callback.data}")
        await callback.answer("Ошибка выбора срока", show_alert=True)
        return
    await state.update_data(duration=duration)
    await callback.message.edit_text(MESSAGES["ask_comment"][lang_code], reply_markup=get_comment_keyboard(lang_code))
    await state.set_state(Form.comment)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "add_comment")
async def ask_comment(callback: types.CallbackQuery, state: FSMContext):
    lang_code = (await state.get_data()).get("language", "en")
    await callback.message.edit_text(MESSAGES["enter_comment"][lang_code], reply_markup=back_keyboard(lang_code))
    await state.set_state(Form.comment)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "send_without_comment")
async def send_without_comment(callback: types.CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback.from_user.id} выбрал отправку без комментария")
    await state.update_data(comment=None)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await finalize_request(callback, state)
    except Exception as e:
        logger.error(f"Ошибка в send_without_comment: {e}", exc_info=True)
        await callback.answer("Произошла ошибка. Попробуйте снова.", show_alert=True)
    await callback.answer()


@dp.message(Form.comment)
async def process_comment(message: types.Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} ввёл комментарий")
    await state.update_data(comment=message.text.strip())
    await finalize_request(message, state)


# === ФИНАЛИЗАЦИЯ ЗАПРОСА ===
async def finalize_request(event, state: FSMContext):
    data = await state.get_data()
    lang_code = data.get("language", "en")
    
    try:
        is_callback = isinstance(event, types.CallbackQuery)
        user = event.from_user if is_callback else event.from_user
        user_id = user.id
        username = user.username
        first_name = user.first_name
        last_name = user.last_name

        server_type = data.get("server_type")
        server_version = data.get("server_version")
        vr_device = data.get("vr_device")
        area_size = data.get("area_size")
        city = data.get("city")
        duration = data.get("duration")
        topic_id = data.get("topic_id")
        comment = data.get("comment")
        partner_name = data.get("partner_name")
        partner_phone = data.get("partner_phone")
        partner_email = data.get("partner_email")
        partner_crm = data.get("partner_crm")

        try:
            city_ru = translate_to_russian(city, lang_code) if city else ""
            comment_ru = translate_to_russian(comment, lang_code) if comment else None
        except Exception as e:
            logger.error(f"Ошибка перевода: {e}")
            city_ru = city or ""
            comment_ru = comment

        demo_start = datetime.now()
        demo_end = demo_start + timedelta(days=int(duration))

        final_msg = (
            f"🎮 Заявка на включение {server_type} Demo\n\n"
            f"🌍 Страна / Город: {html.escape(city_ru)}\n"
            f"📐 Размер игровой зоны: {area_size} м\n"
            f"📦 Версия игры: {server_version}\n"
            f"🥽 Оборудование: {vr_device}\n"
            f"📅 Срок демо: {duration} дня(ей) с "
            f"<b>{format_ru_date(demo_start)}</b> до <b>{format_ru_date(demo_end)}</b>\n"
        )

        partner_lines = []
        if partner_name:
            partner_lines.append(f"👤 Контакт (Имя): {html.escape(partner_name)}")
        if partner_phone:
            partner_lines.append(f"📱 Телефон: {html.escape(partner_phone)}")
        if partner_email:
            partner_lines.append(f"📧 Email: {html.escape(partner_email)}")
        if partner_crm:
            partner_lines.append(f"🔗 Ссылка на CRM: {html.escape(partner_crm)}")
        if partner_lines:
            final_msg += "\n" + "\n".join(partner_lines) + "\n"

        if comment_ru:
            final_msg += f"\n💬 Комментарий: {html.escape(comment_ru)}"

        user_info = f"\n\n🧑‍💼 Ответственный: {html.escape(first_name or '')}"
        if last_name:
            user_info += f" {html.escape(last_name)}"
        if username:
            user_info += f" (@{html.escape(username)})"
        if lang_code == "zh":
            user_info += " (на китайском языке)"
        elif lang_code == "en":
            user_info += " (на английском языке)"

        final_msg += user_info

        if lang_code in ["en", "zh"]:
            final_msg += "\n\n🌐 Сообщение автоматически переведено на русский"

        try:
            sent_message = await bot.send_message(
                chat_id=MAIN_CHAT_ID,
                text=final_msg,
                message_thread_id=topic_id,
                parse_mode="HTML"
            )
            msg_id = sent_message.message_id
            chat_id_short = str(MAIN_CHAT_ID).replace("-100", "")
            link = f"https://t.me/c/{chat_id_short}/{msg_id}?thread={topic_id}"
            logger.info(f"Сообщение отправлено в чат, ссылка: {link}")
        except Exception as e:
            logger.error(f"Ошибка отправки в чат: {e}", exc_info=True)
            link = "#"
            msg_id = "unknown"

        req_id = None
        try:
            expires_at = demo_end
            request_data = {
                "user_id": user_id,
                "language": lang_code,
                "server_type": server_type,
                "area_size": area_size,
                "vr_device": vr_device,
                "duration": int(duration),
                "city": city,
                "topic_id": topic_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "server_version": server_version,
                "message_id": msg_id if isinstance(msg_id, int) else None,
                "original_text": final_msg
            }
            req_id = save_request(request_data, link, expires_at.strftime("%Y-%m-%d %H:%M:%S"))
            logger.info(f"Запрос сохранён в БД для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения в БД: {e}", exc_info=True)

        if req_id is not None and isinstance(msg_id, int):
            try:
                await bot.edit_message_reply_markup(
                    chat_id=MAIN_CHAT_ID,
                    message_id=msg_id,
                    reply_markup=get_request_management_keyboard(req_id, lang_code, server_version)
                )
            except Exception as e:
                logger.error(f"Не удалось прикрепить кнопки управления к заявке #{req_id}: {e}", exc_info=True)

        success_msg = MESSAGES["success_with_link"][lang_code].format(link=link)
        
        try:
            if is_callback:
                await bot.send_message(
                    chat_id=event.from_user.id,
                    text=success_msg,
                    parse_mode="HTML"
                )
                await event.message.delete()
            else:
                await event.answer(
                    success_msg,
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Ошибка отправки подтверждения: {e}", exc_info=True)
            try:
                plain_msg = f"✅ Запрос успешно оформлен! Ссылка: {link}"
                if is_callback:
                    await bot.send_message(chat_id=event.from_user.id, text=plain_msg)
                else:
                    await event.answer(plain_msg)
            except Exception as e2:
                logger.error(f"Не удалось отправить подтверждение: {e2}")

        await state.clear()
        logger.info(f"Запрос успешно завершён для пользователя {user_id}")
        
    except Exception as e:
        logger.error(f"Критическая ошибка в finalize_request: {e}", exc_info=True)
        try:
            await state.clear()
        except:
            pass
        try:
            error_msg = "❌ Произошла ошибка при обработке запроса. Попробуйте снова /start"
            if isinstance(event, types.CallbackQuery):
                await bot.send_message(chat_id=event.from_user.id, text=error_msg)
            else:
                await event.answer(error_msg)
        except:
            pass


# === ОБРАБОТКА КНОПКИ НАЗАД ===
@dp.callback_query(lambda c: c.data == "back")
async def process_back(callback: types.CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback.from_user.id} нажал кнопку 'Назад'")
    current_state = await state.get_state()
    data = await state.get_data()
    lang_code = data.get("language", "ru")
    server_type = data.get("server_type")

    if current_state == Form.server_version:
        await callback.message.edit_text(MESSAGES["choose_server"][lang_code], reply_markup=get_server_keyboard(lang_code))
        await state.set_state(Form.server_type)
    elif current_state == Form.area_size:
        await callback.message.edit_text(MESSAGES["ask_server_version"][lang_code], reply_markup=get_version_keyboard(lang_code))
        await state.set_state(Form.server_version)
    elif current_state == Form.vr_device:
        server_version = data.get("server_version")
        await callback.message.edit_text(MESSAGES["ask_area"][lang_code], reply_markup=get_area_keyboard(lang_code, server_type, server_version))
        await state.set_state(Form.area_size)
    elif current_state == Form.partner_contact:
        await callback.message.edit_text(MESSAGES["ask_vr_device"][lang_code], reply_markup=get_vr_keyboard(lang_code))
        await state.set_state(Form.vr_device)
    elif current_state == Form.partner_name:
        await callback.message.edit_text(MESSAGES["ask_partner_contact"][lang_code], reply_markup=get_partner_keyboard(lang_code))
        await state.set_state(Form.partner_contact)
    elif current_state == Form.partner_phone:
        await callback.message.edit_text(MESSAGES["ask_partner_name"][lang_code], reply_markup=back_keyboard(lang_code))
        await state.set_state(Form.partner_name)
    elif current_state == Form.partner_email:
        await callback.message.edit_text(MESSAGES["ask_partner_phone"][lang_code], reply_markup=back_keyboard(lang_code))
        await state.set_state(Form.partner_phone)
    elif current_state == Form.partner_crm:
        await callback.message.edit_text(MESSAGES["ask_partner_email"][lang_code], reply_markup=back_keyboard(lang_code))
        await state.set_state(Form.partner_email)
    elif current_state == Form.city:
        if data.get("partner_name") is not None:
            await callback.message.edit_text(MESSAGES["ask_partner_crm"][lang_code], reply_markup=back_keyboard(lang_code))
            await state.set_state(Form.partner_crm)
        else:
            await callback.message.edit_text(MESSAGES["ask_partner_contact"][lang_code], reply_markup=get_partner_keyboard(lang_code))
            await state.set_state(Form.partner_contact)
    elif current_state == Form.duration:
        await callback.message.edit_text(MESSAGES["ask_city"][lang_code], reply_markup=back_keyboard(lang_code))
        await state.set_state(Form.city)
    elif current_state == Form.comment:
        await callback.message.edit_text(MESSAGES["ask_duration"][lang_code], reply_markup=get_duration_keyboard(lang_code))
        await state.set_state(Form.duration)
    elif current_state == Form.server_type:
        await callback.message.edit_text(MESSAGES["start_choose_lang"], reply_markup=get_lang_keyboard("ru"))
        await state.set_state(Form.language)
    else:
        await callback.message.edit_text(MESSAGES["start_choose_lang"], reply_markup=get_lang_keyboard("ru"))
        await state.set_state(Form.language)

    await callback.answer()


@dp.message(RequestEdit.build_link)
async def process_build_link_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    req_id = data.get("edit_req_id")
    prompt_message_id = data.get("prompt_message_id")
    await state.clear()
    if req_id is None:
        return
    set_build_link(req_id, message.text.strip())
    req = get_request_by_id(req_id)
    if not req:
        return
    await refresh_request_message(req)
    t = get_management_texts(req.get("language") or "ru")
    confirm = await message.reply(f"✅ {t['label_build']} {t['updated']}")
    to_delete = [mid for mid in [prompt_message_id, message.message_id, confirm.message_id] if mid]
    asyncio.create_task(delete_messages_later(message.chat.id, to_delete))


@dp.message(RequestEdit.pin_code)
async def process_pin_code_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    req_id = data.get("edit_req_id")
    prompt_message_id = data.get("prompt_message_id")
    await state.clear()
    if req_id is None:
        return
    set_pin_code(req_id, message.text.strip())
    req = get_request_by_id(req_id)
    if not req:
        return
    await refresh_request_message(req)
    t = get_management_texts(req.get("language") or "ru")
    confirm = await message.reply(f"✅ {t['label_pin']} {t['updated']}")
    to_delete = [mid for mid in [prompt_message_id, message.message_id, confirm.message_id] if mid]
    asyncio.create_task(delete_messages_later(message.chat.id, to_delete))


@dp.message(RequestEdit.calibration_plan)
async def process_calibration_plan_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    req_id = data.get("edit_req_id")
    prompt_message_id = data.get("prompt_message_id")
    await state.clear()
    if req_id is None:
        return
    set_calibration_plan(req_id, message.text.strip())
    req = get_request_by_id(req_id)
    if not req:
        return
    await refresh_request_message(req)
    t = get_management_texts(req.get("language") or "ru")
    confirm = await message.reply(f"✅ {t['label_calibration']} {t['updated']}")
    to_delete = [mid for mid in [prompt_message_id, message.message_id, confirm.message_id] if mid]
    asyncio.create_task(delete_messages_later(message.chat.id, to_delete))


@dp.message(RequestEdit.demo_status_other)
async def process_status_other_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    req_id = data.get("edit_req_id")
    prompt_message_id = data.get("prompt_message_id")
    await state.clear()
    if req_id is None:
        return
    req = get_request_by_id(req_id)
    if not req:
        return
    status_text = message.text.strip()
    try:
        status_text = translate_to_russian(status_text, req.get("language") or "ru")
    except Exception as e:
        logger.error(f"Ошибка перевода статуса: {e}")
    set_demo_status(req_id, status_text)
    req = get_request_by_id(req_id)
    await refresh_request_message(req)
    t = get_management_texts(req.get("language") or "ru")
    confirm = await message.reply(f"✅ {t['label_status']} {t['updated']}")
    to_delete = [mid for mid in [prompt_message_id, message.message_id, confirm.message_id] if mid]
    asyncio.create_task(delete_messages_later(message.chat.id, to_delete))


@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer("🟢 Бот работает нормально!")
    logger.info(f"Health check от пользователя {message.from_user.id}")


@dp.message(Command("topicid"))
async def cmd_topicid(message: types.Message):
    await message.reply(f"topic_id этого топика: {message.message_thread_id}")


# === НАПОМИНАНИЯ О СРОКЕ ДЕМО ===
def mention_html(user_id: int, first_name: str, last_name: str = None) -> str:
    name = first_name or "Сотрудник"
    if last_name:
        name += f" {last_name}"
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


def get_request_management_keyboard(req_id: int, lang_code: str, server_version: str = None):
    t = get_management_texts(lang_code)
    if server_version == "1.3.0":
        first_row = types.InlineKeyboardButton(text=t["btn_pin"], callback_data=f"setpin:{req_id}")
    else:
        first_row = types.InlineKeyboardButton(text=t["btn_build"], callback_data=f"setbuild:{req_id}")
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [first_row],
        [types.InlineKeyboardButton(text=t["btn_calibration"], callback_data=f"setcalib:{req_id}")],
        [types.InlineKeyboardButton(text=t["btn_status"], callback_data=f"setstatusmenu:{req_id}")],
    ])


def get_status_choice_keyboard(req_id: int, lang_code: str):
    t = get_management_texts(lang_code)
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t["status_build_sent"], callback_data=f"setstatus:{req_id}:build_sent")],
        [types.InlineKeyboardButton(text=t["status_partner_launching"], callback_data=f"setstatus:{req_id}:partner_launching")],
        [types.InlineKeyboardButton(text=t["status_partner_no_response"], callback_data=f"setstatus:{req_id}:partner_no_response")],
        [types.InlineKeyboardButton(text=t["status_setup"], callback_data=f"setstatus:{req_id}:setup")],
        [types.InlineKeyboardButton(text=t["status_other"], callback_data=f"setstatus:{req_id}:other")],
        [types.InlineKeyboardButton(text=t["btn_back"], callback_data=f"statuscancel:{req_id}")],
    ])


def get_dynamic_fields_lines(req: dict) -> list:
    t = get_management_texts(req.get("language") or "ru")
    ru_t = REQUEST_MANAGEMENT["ru"]
    lines = []
    if req.get("server_version") == "1.3.0":
        if req.get("pin_code"):
            lines.append(f"📌 {t['label_pin']}: {html.escape(req['pin_code'])}")
    elif req.get("build_link"):
        lines.append(f"🔗 {t['label_build']}: {html.escape(req['build_link'])}")
    if req.get("calibration_plan"):
        lines.append(f"📋 {t['label_calibration']}: {html.escape(req['calibration_plan'])}")
    if req.get("demo_status"):
        # Статус всегда показывается по-русски для сотрудников в общем чате,
        # даже если кнопки выбора статуса были на языке заявки.
        status_label = ru_t.get(f"status_{req['demo_status']}", req["demo_status"])
        lines.append(f"📊 {ru_t['label_status']}: {status_label}")
    return lines


def build_dynamic_footer(req: dict) -> str:
    lines = get_dynamic_fields_lines(req)
    if not lines:
        return ""
    return "\n\n" + "―" * 16 + "\n" + "\n".join(lines)


async def refresh_request_message(req: dict):
    if not req.get("message_id"):
        return
    text = (req.get("original_text") or "") + build_dynamic_footer(req)
    keyboard = get_request_management_keyboard(req["id"], req.get("language") or "ru", req.get("server_version"))
    try:
        await bot.edit_message_text(
            chat_id=MAIN_CHAT_ID,
            message_id=req["message_id"],
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Не удалось обновить сообщение заявки #{req['id']}: {e}", exc_info=True)


def get_extend_duration_keyboard(req_id: int, lang_code: str):
    t = get_management_texts(lang_code)
    labels = t.get("duration_labels", DURATION_LABELS)
    buttons = [
        [types.InlineKeyboardButton(text=labels[days], callback_data=f"extdur:{req_id}:{days}")]
        for days in DURATION_LABELS
    ]
    buttons.append([types.InlineKeyboardButton(text=t["btn_cancel"], callback_data=f"extcancel:{req_id}")])
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def get_reminder_keyboard(req_id: int, lang_code: str):
    t = get_management_texts(lang_code)
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=t["btn_extend"], callback_data=f"extend:{req_id}")],
        [types.InlineKeyboardButton(text=t["btn_close"], callback_data=f"close:{req_id}")]
    ])


def build_details_block(req: dict) -> str:
    mention = mention_html(req["user_id"], req["first_name"], req["last_name"])
    lines = [
        f"📡 Сервер: {req['server_type']}" + (f" (версия {req['server_version']})" if req.get('server_version') else ""),
        f"📐 Площадка: {req['area_size']} м",
    ]
    if req.get("vr_device"):
        lines.append(f"👓 VR: {req['vr_device']}")
    lines.append(f"🌍 Город: {html.escape(req['city'])}")
    lines.extend(get_dynamic_fields_lines(req))
    lines.append(f"👤 Ответственный: {mention}")
    if req.get("message_link") and req["message_link"] != "#":
        lines.append(f"🔗 <a href=\"{req['message_link']}\">Исходная заявка</a>")
    return "\n".join(lines)


def build_reminder_text(req: dict) -> str:
    expires_at = datetime.strptime(req["expires_at"], "%Y-%m-%d %H:%M:%S")
    return (
        f"⏰ Напоминание: через сутки истекает срок демо-доступа\n"
        f"📅 Окончание: <b>{format_ru_date(expires_at)}</b>\n\n"
        f"{build_details_block(req)}\n\n"
        f"Продлить срок или отключить демо в указанную дату?"
    )


async def reminder_loop():
    while True:
        try:
            due_requests = get_requests_due_for_reminder(REMINDER_HOURS_BEFORE)
            for req in due_requests:
                try:
                    await bot.send_message(
                        chat_id=MAIN_CHAT_ID,
                        text=build_reminder_text(req),
                        message_thread_id=req["topic_id"],
                        parse_mode="HTML",
                        reply_markup=get_reminder_keyboard(req["id"], req.get("language") or "ru")
                    )
                    mark_reminded(req["id"])
                    logger.info(f"Напоминание отправлено по заявке #{req['id']}")
                except TelegramRetryAfter as e:
                    logger.warning(f"Флуд-контроль Telegram, ждём {e.retry_after} сек.")
                    await asyncio.sleep(e.retry_after)
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания по заявке #{req['id']}: {e}", exc_info=True)
                await asyncio.sleep(2)  # пауза между отправками, чтобы не словить флуд-контроль
        except Exception as e:
            logger.error(f"Ошибка в reminder_loop: {e}", exc_info=True)
        await asyncio.sleep(REMINDER_CHECK_INTERVAL_SECONDS)


def _is_responsible(callback: types.CallbackQuery, req: dict) -> bool:
    return req is not None and callback.from_user.id == req["user_id"]


@dp.callback_query(lambda c: c.data.startswith("extend:"))
async def process_extend_click(callback: types.CallbackQuery, state: FSMContext):
    req_id = int(callback.data.split(":")[1])
    req = get_request_by_id(req_id)
    if not _is_responsible(callback, req):
        await callback.answer("Продлить может только ответственный сотрудник по заявке", show_alert=True)
        return
    await callback.message.edit_reply_markup(
        reply_markup=get_extend_duration_keyboard(req_id, req.get("language") or "ru")
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("extcancel:"))
async def process_extend_cancel(callback: types.CallbackQuery, state: FSMContext):
    req_id = int(callback.data.split(":")[1])
    req = get_request_by_id(req_id)
    if not _is_responsible(callback, req):
        await callback.answer("Действие доступно только ответственному сотруднику", show_alert=True)
        return
    await callback.message.edit_reply_markup(
        reply_markup=get_reminder_keyboard(req_id, req.get("language") or "ru")
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("extdur:"))
async def process_extend_duration(callback: types.CallbackQuery, state: FSMContext):
    _, req_id_str, days_str = callback.data.split(":")
    req_id = int(req_id_str)
    req = get_request_by_id(req_id)
    if not _is_responsible(callback, req):
        await callback.answer("Продлить может только ответственный сотрудник по заявке", show_alert=True)
        return

    current_expires = datetime.strptime(req["expires_at"], "%Y-%m-%d %H:%M:%S")
    new_expires = current_expires + timedelta(days=int(days_str))
    extend_request(req_id, new_expires.strftime("%Y-%m-%d %H:%M:%S"))
    req["expires_at"] = new_expires.strftime("%Y-%m-%d %H:%M:%S")

    await callback.message.edit_text(
        f"✅ Статус: продлено на {DURATION_LABELS[days_str]}\n"
        f"📅 Новое окончание: <b>{format_ru_date(new_expires)}</b>\n\n"
        f"{build_details_block(req)}",
        parse_mode="HTML"
    )
    logger.info(f"Заявка #{req_id} продлена на {days_str} дней, новое окончание {new_expires}")
    await callback.answer("Продлено")


@dp.callback_query(lambda c: c.data.startswith("close:"))
async def process_close_click(callback: types.CallbackQuery, state: FSMContext):
    req_id = int(callback.data.split(":")[1])
    req = get_request_by_id(req_id)
    if not _is_responsible(callback, req):
        await callback.answer("Отключить может только ответственный сотрудник по заявке", show_alert=True)
        return

    close_request(req_id)
    expires_at = datetime.strptime(req["expires_at"], "%Y-%m-%d %H:%M:%S")
    await callback.message.edit_text(
        f"⛔ Статус: отключаем в назначенную дату\n"
        f"📅 Дата отключения: <b>{format_ru_date(expires_at)}</b>\n\n"
        f"{build_details_block(req)}",
        parse_mode="HTML"
    )
    logger.info(f"Заявка #{req_id} закрыта (отключение в {expires_at})")
    await callback.answer("Отмечено")


EDIT_PROMPT_CLEANUP_DELAY = 5


async def delete_messages_later(chat_id: int, message_ids: list, delay: int = EDIT_PROMPT_CLEANUP_DELAY):
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception as e:
            logger.warning(f"Не удалось удалить служебное сообщение {mid} в чате {chat_id}: {e}")


@dp.callback_query(lambda c: c.data.startswith("setbuild:"))
async def process_setbuild_click(callback: types.CallbackQuery, state: FSMContext):
    req_id = int(callback.data.split(":")[1])
    req = get_request_by_id(req_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    t = get_management_texts(req.get("language") or "ru")
    prompt = await bot.send_message(
        chat_id=callback.message.chat.id,
        message_thread_id=callback.message.message_thread_id,
        text=t["prompt_build"],
        reply_markup=types.ForceReply(selective=True)
    )
    await state.update_data(edit_req_id=req_id, prompt_message_id=prompt.message_id)
    await state.set_state(RequestEdit.build_link)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("setpin:"))
async def process_setpin_click(callback: types.CallbackQuery, state: FSMContext):
    req_id = int(callback.data.split(":")[1])
    req = get_request_by_id(req_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    t = get_management_texts(req.get("language") or "ru")
    prompt = await bot.send_message(
        chat_id=callback.message.chat.id,
        message_thread_id=callback.message.message_thread_id,
        text=t["prompt_pin"],
        reply_markup=types.ForceReply(selective=True)
    )
    await state.update_data(edit_req_id=req_id, prompt_message_id=prompt.message_id)
    await state.set_state(RequestEdit.pin_code)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("setcalib:"))
async def process_setcalib_click(callback: types.CallbackQuery, state: FSMContext):
    req_id = int(callback.data.split(":")[1])
    req = get_request_by_id(req_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    t = get_management_texts(req.get("language") or "ru")
    prompt = await bot.send_message(
        chat_id=callback.message.chat.id,
        message_thread_id=callback.message.message_thread_id,
        text=t["prompt_calibration"],
        reply_markup=types.ForceReply(selective=True)
    )
    await state.update_data(edit_req_id=req_id, prompt_message_id=prompt.message_id)
    await state.set_state(RequestEdit.calibration_plan)
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("setstatusmenu:"))
async def process_status_menu_click(callback: types.CallbackQuery, state: FSMContext):
    req_id = int(callback.data.split(":")[1])
    req = get_request_by_id(req_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await callback.message.edit_reply_markup(
        reply_markup=get_status_choice_keyboard(req_id, req.get("language") or "ru")
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("statuscancel:"))
async def process_status_cancel_click(callback: types.CallbackQuery, state: FSMContext):
    req_id = int(callback.data.split(":")[1])
    req = get_request_by_id(req_id)
    if not req:
        await callback.answer()
        return
    await callback.message.edit_reply_markup(
        reply_markup=get_request_management_keyboard(req_id, req.get("language") or "ru", req.get("server_version"))
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("setstatus:"))
async def process_set_status_click(callback: types.CallbackQuery, state: FSMContext):
    _, req_id_str, status_code = callback.data.split(":")
    req_id = int(req_id_str)
    if status_code not in STATUS_CODES:
        await callback.answer("Неизвестный статус", show_alert=True)
        return

    req = get_request_by_id(req_id)
    if not req:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if status_code == "other":
        t = get_management_texts(req.get("language") or "ru")
        prompt = await bot.send_message(
            chat_id=callback.message.chat.id,
            message_thread_id=callback.message.message_thread_id,
            text=t["prompt_status_other"],
            reply_markup=types.ForceReply(selective=True)
        )
        await state.update_data(edit_req_id=req_id, prompt_message_id=prompt.message_id)
        await state.set_state(RequestEdit.demo_status_other)
        await callback.answer()
        return

    set_demo_status(req_id, status_code)
    req = get_request_by_id(req_id)
    await refresh_request_message(req)
    await callback.answer("OK")


# === ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ ПО АКТИВНЫМ ДЕМО ===
TELEGRAM_MESSAGE_LIMIT = 3500  # с запасом от реального лимита Telegram в 4096 символов


def build_weekly_report_chunks() -> list:
    requests = get_active_requests()
    header = f"📊 Еженедельный отчёт — активные демо ({format_ru_date(datetime.now())})"

    if not requests:
        return [f"{header}\n\nАктивных демо сейчас нет."]

    ru_t = REQUEST_MANAGEMENT["ru"]
    grouped = {}
    for req in requests:
        grouped.setdefault(req["topic_id"], []).append(req)

    blocks = [header, ""]
    total = 0
    for topic_id, label in TOPIC_LABELS.items():
        reqs = grouped.get(topic_id)
        if not reqs:
            continue
        blocks.append(f"<b>{label}</b>")
        for i, req in enumerate(reqs, 1):
            total += 1
            expires_at = datetime.strptime(req["expires_at"], "%Y-%m-%d %H:%M:%S")
            mention = mention_html(req["user_id"], req["first_name"], req["last_name"])
            status_label = ru_t.get(f"status_{req['demo_status']}", req["demo_status"]) if req.get("demo_status") else "—"
            blocks.append(
                f"{i}. <b>{req['server_type']}</b> — {html.escape(req['city'])}\n"
                f"   📅 Активна до: {format_ru_date(expires_at)}\n"
                f"   📊 Статус: {status_label}\n"
                f"   🧑‍💼 Ответственный: {mention}\n"
                f"   🔗 <a href=\"{req['message_link']}\">Заявка</a>"
            )
            blocks.append("")

    blocks.append(f"Итого активных демо: {total}")

    # Упаковываем блоки в сообщения, каждое не длиннее лимита Telegram
    chunks = []
    current = []
    current_len = 0
    for block in blocks:
        block_len = len(block) + 1
        if current and current_len + block_len > TELEGRAM_MESSAGE_LIMIT:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(block)
        current_len += block_len
    if current:
        chunks.append("\n".join(current))
    return chunks


async def send_weekly_report():
    if not DISCUSSION_TOPIC_ID:
        logger.warning("DISCUSSION_TOPIC_ID не задан — еженедельный отчёт не отправлен")
        return
    chunks = build_weekly_report_chunks()
    thread_kwargs = {} if DISCUSSION_TOPIC_ID == "general" else {"message_thread_id": DISCUSSION_TOPIC_ID}
    for chunk in chunks:
        try:
            await bot.send_message(
                chat_id=MAIN_CHAT_ID,
                text=chunk,
                parse_mode="HTML",
                **thread_kwargs
            )
        except TelegramRetryAfter as e:
            logger.warning(f"Флуд-контроль при отправке отчёта, ждём {e.retry_after} сек.")
            await asyncio.sleep(e.retry_after)
            await bot.send_message(chat_id=MAIN_CHAT_ID, text=chunk, parse_mode="HTML", **thread_kwargs)
        await asyncio.sleep(1)
    logger.info(f"Еженедельный отчёт отправлен ({len(chunks)} сообщений)")


async def weekly_report_loop():
    while True:
        now = datetime.now(MOSCOW_TZ)
        days_ahead = (WEEKLY_REPORT_WEEKDAY - now.weekday()) % 7
        next_run = (now + timedelta(days=days_ahead)).replace(
            hour=WEEKLY_REPORT_HOUR, minute=0, second=0, microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=7)
        wait_seconds = (next_run - now).total_seconds()
        logger.info(f"Следующий еженедельный отчёт запланирован на {next_run}")
        await asyncio.sleep(wait_seconds)
        try:
            await send_weekly_report()
        except Exception as e:
            logger.error(f"Ошибка отправки еженедельного отчёта: {e}", exc_info=True)


@dp.message(Command("weeklyreport"))
async def cmd_weekly_report(message: types.Message):
    if not DISCUSSION_TOPIC_ID:
        await message.reply("⚠️ DISCUSSION_TOPIC_ID не задан в коде бота.")
        return
    try:
        await send_weekly_report()
    except Exception as e:
        logger.error(f"Ошибка ручного запуска еженедельного отчёта: {e}", exc_info=True)
        await message.reply(f"⚠️ Не удалось отправить отчёт: {e}")


# Обязательно регистрируется последним: aiogram проверяет обработчики сообщений
# в порядке регистрации и останавливается на первом совпадении, а у этого
# хендлера нет фильтра (совпадает с любым сообщением) — если поставить его
# раньше, он "съест" все команды и state-хендлеры, зарегистрированные после него.
@dp.message()
async def handle_unknown_state(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        logger.warning(f"Получено сообщение в состоянии {current_state} от {message.from_user.id}")
        await message.answer(
            "🔄 Похоже, произошла ошибка. Начните заново: /start",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.clear()


# === MAIN ===
async def main():
    logger.info("Запуск бота...")
    init_db()
    logger.info("База данных инициализирована")
    asyncio.create_task(reminder_loop())
    asyncio.create_task(weekly_report_loop())
    logger.info("Фоновая проверка сроков демо запущена")
    await dp.start_polling(bot)


if __name__ == "__main__":
    logger.info("=== Бот запущен ===")
    asyncio.run(main())
