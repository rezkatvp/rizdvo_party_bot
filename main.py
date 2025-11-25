import os
import asyncio
import random
import json
import logging
from typing import Dict, Optional, Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode

from datetime import datetime, date

# ================== ЛОГІНГ ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ENV CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PARTY_CHANNEL_LINK = os.getenv("PARTY_CHANNEL_LINK")  # канал
PARTY_CHAT_LINK = os.getenv("PARTY_CHAT_LINK")        # чат вечірки (опційно)

# Ключ: (chat_id, message_id) → міст
# value: {"peer_id": int, "prefix_to_peer": str, "reply_prefix_back": str}
BRIDGE_REPLIES: Dict[tuple[int, int], Dict[str, Any]] = {}

# GIF-и
START_GIF_ID = "CgACAgIAAxkBAAEE_kVpIJHcbwutHFMVmzRWNSy4lG8CEQAC-YgAAuEo-EjlnrqzRWboTjYE"
SANTA_GIF_ID = os.getenv("SANTA_GIF_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не заданий в змінних середовища")

# ================== КОНСТАНТИ ВЕЧІРКИ ==================
PARTY_NAME = os.getenv("PARTY_NAME", "Різдвяний Спектр")
PARTY_LOCATION = os.getenv("PARTY_LOCATION", "Адресу скинемо окремо перед вечіркою 😉")
PARTY_DATES_TEXT = os.getenv("PARTY_DATES_TEXT", "26 грудня, 18:00")

# ================== АКТИВНА ВЕЧІРКА ==================
PARTY = {
    "active": False,
    "name": PARTY_NAME,
    "location": PARTY_LOCATION,
    "dates_text": PARTY_DATES_TEXT,
    "code": None,
    "feedback_date": None,  # YYYY-MM-DD, з якого дня просимо відгук
}


def register_bridge_message(
    chat_id: int,
    message_id: int,
    peer_id: int,
    prefix_to_peer: str,
    reply_prefix_back: str,
):
    """
    Реєструємо "якір" для reply у чаті chat_id → коли хтось відповідає
    на message_id, ми перешлемо це peer_id з prefix_to_peer.

    reply_prefix_back — префікс для наступного "дзеркального" повідомлення
    у відповідь від peer_id назад (для багатокрокового діалогу).
    """
    BRIDGE_REPLIES[(chat_id, message_id)] = {
        "peer_id": peer_id,
        "prefix_to_peer": prefix_to_peer,
        "reply_prefix_back": reply_prefix_back,
    }


def apply_party_to_globals():
    global PARTY_NAME, PARTY_LOCATION, PARTY_DATES_TEXT
    if PARTY.get("name"):
        PARTY_NAME = PARTY["name"]
    if PARTY.get("location"):
        PARTY_LOCATION = PARTY["location"]
    if PARTY.get("dates_text"):
        PARTY_DATES_TEXT = PARTY["dates_text"]


def generate_party_code(length: int = 6) -> str:
    import string
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def party_rules_text(include_cta: bool = True) -> str:
    base = (
        f"📜 <b>Правила вечірки «{PARTY_NAME}»</b>\n\n"
        "1. У кожного гостя є <b>свій колір-образ</b>. "
        "Це має бути <b>моно-образ</b> — весь твій лук в одному кольорі.\n\n"
        "2. Разом з кольором у тебе є <b>роль</b> та <b>набір міні-завдань</b>. "
        "Роль можна озвучувати, завдання — НІ 😉\n\n"
        "3. Гра «Таємний Миколайчик» — важлива частина вечірки.\n\n"
        "4. Кожен гість приносить <b>своє меню</b>: страву, напій і десерт. "
        "Це може бути щось невелике й недороге, але круто, якщо воно хоч трохи пасує до твого кольору.\n\n"
        "5. Поганий настрій, токсичність і «я тут постою в куточку» — не наш формат. "
        "Приходимо за атмосферою, сміхом і теплом 🥰"
    )
    if include_cta:
        base += "\n\nЯкщо тобі все підходить — підтверджуй участь нижче 👇"
    return base


SANTA_BASE_RULES = (
    "🎅 <b>Таємний Миколайчик</b>\n\n"
    "• Кожен учасник таємно дарує подарунок іншому гостю\n"
    "• Можеш написати свої побажання або обрати «Сюрприз»\n"
    "• Після запуску гри дізнаєшся, хто твій підопічний\n"
    "• Можна анонімно переписуватись через бота\n"
    "• Головне — увага і настрій, а не сума подарунка 🫶"
)

router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

# ================== КОЛЬОРИ ТА ГОСТІ ==================
COLORS: Dict[int, Dict[str, Any]] = {
    1: {
        "emoji": "🌸",
        "name": "Пудрово-рожевий",
        "label": "🌸 Пудрово-рожевий (Морозний Рум’янець)",
        "role": "Морозний Рум’янець",
    },
    2: {
        "emoji": "❄️",
        "name": "Блакитний",
        "label": "❄️ Блакитний (Смурфик Святвечора)",
        "role": "Смурфик Святвечора",
    },
    3: {
        "emoji": "🍊",
        "name": "Мандариновий",
        "label": "🍊 Мандариновий (Аромат Різдва)",
        "role": "Аромат Різдва",
    },
    4: {
        "emoji": "🌲",
        "name": "Хвойно-зелений",
        "label": "🌲 Хвойно-зелений (Лісова Ялинка)",
        "role": "Лісова Ялинка",
    },
    5: {
        "emoji": "🌌",
        "name": "Глибокий синій",
        "label": "🌌 Глибокий синій (Різдвяна Ніч)",
        "role": "Різдвяна Ніч",
    },
    6: {
        "emoji": "❤️",
        "name": "Яскраво-червоний",
        "label": "❤️ Яскраво-червоний (Полуничний Санта)",
        "role": "Полуничний Санта",
    },
    7: {
        "emoji": "🍫",
        "name": "Какаовий коричневий",
        "label": "🍫 Какаовий коричневий (Гарячий Шоколад)",
        "role": "Гарячий Шоколад",
    },
}

# Привʼязка гостей до кольорів (фіксовано)
PREASSIGNED_COLORS: Dict[int, int] = {
    228116679: 1,  # Алінка
    225843530: 2,  # Славік (адмін)
    1219847735: 3, # Саша
    1465084512: 4, # Лариса
    539744711: 5,  # Наташка
    925614596: 6,  # Мама
    584640361: 7,  # Теща
}

# Універсальні завдання 6 та 7
UNIVERSAL_TASKS = [
    "Організуй хоча б одне спільне фото компанії, де видно максимальну кількість кольорів образів.",
    "Скажи комусь один дуже щирий різдвяний комплімент так, щоб людина його запамʼятала.",
]

# 7 завдань під кожного гостя (перші 5 – унікальні під колір/настрій)
COLOR_TASKS: Dict[int, list[str]] = {
    1: [
        "ПОХВАЛИТИ ЧИЇСЬ ОБРАЗ АБО ДЕТАЛЬ У ДУЖЕ НІЖНОМУ, МʼЯКОМУ СТИЛІ.",
        "ЗРОБИ СЕЛФІ У ВСІХ НА ВИДУ В СВОЄМУ ОБРАЗІ ТАК, ЩОБ РОЖЕВИЙ КОЛІР МАКСИМАЛЬНО ДОМІНУВАВ У КАДРІ.",
        "СКАЖИ РЕЧЕННЯ ТІЛЬКИ З ІМЕННИКІВ",
        "ПОЧНИ ХВАЛИТИ ЧИЙСЬ ОБРАЗ, АЛЕ СКАЖИ ЩО ТВІЙ МІГ БУТИ КРАЩЕ, ЯК БИ НЕ ... (ПРИДУМАЙ ЩОСЬ)",
        "ХОЧ РАЗ ЗА ВЕЧІР СКАЖИ ФРАЗУ НА КШТАЛТ: «МЕНІ ЗДАЄТЬСЯ, ТУТ НЕ ВИСТАЧАЄ ТРОХИ НІЖНОСТІ",
        *UNIVERSAL_TASKS,
    ],
    2: [
        "Хоч раз зобрази себе «Смурфика Святвечора» — зроби смішну або мультик-грімасу для фото.",
        "Запропонуй мінімум двом людям вийти подихати свіжим повітрям або просто змінити локацію.",
        "Зроби жартівливий «прогноз погоди» на вечір для компанії.",
        "Знайди когось у теплому одязі та скажи, що він/вона виглядає як персонаж зимового мультика.",
        "Під кінець вечірки спробуй трохи «розморозити» когось, хто соромиться – втягни в легку гру чи розмову.",
        *UNIVERSAL_TASKS,
    ],
    3: [
        "ХОЧ РАЗ ПРИНЕСИ В КІМНАТУ ЩОСЬ МАНДАРИНОВЕ - АРОМАТ, ЖАРТИ ЧИ АСОЦІАЦІЇ.",
        "ЗАПРОПОНУЙ КОМУСЬ ПІДНЯТИ КЕЛИХ «ЗА АРОМАТ СПРАВЖНЬОГО РІЗДВА».",
        "РОЗКАЖИ КОРОТКУ ІСТОРІЮ, ПОВʼЯЗАНУ З НОВИМ РОКОМ, РІЗДВОМ І МАНДАРИНАМИ.",
        "ПОЖАРТУЙ НАД ТИМ, ЩО ТИ СЬОГОДНІ ПАХНЕШ ЯК (ПРИДУМАЙ ЩОСЬ)",
        "ЗАПИТАЙ КОГОСЬ, ЯКИЙ ЗИМОВИЙ НАПІЙ ВІН ЛЮБИТЬ НАЙБІЛЬШЕ.",
        *UNIVERSAL_TASKS,
    ],
    4: [
        "ЗРОБИ ВІДЕО ЯК ТИ ТАНЦУЄШЬ БІЛЯ ЯЛИНКИ.",
        "ЗАПРОПОНУЙ КОМУСЬ «ПРИКРАСИТИ» ТЕБЕ: ЩОБ ХТОСЬ ДОДАВ У ТВІЙ ОБРАЗ ІГРАШКУ.",
        "ЗБЕРИ НЕВЕЛИКУ КОМПАНІЮ НАВКОЛО СЕБЕ І ЗРОБИ З НИМИ ВЕСЕЛИЙ КАДР.",
        "ПРОТЯГОМ ВЕЧОРА ТРИЧІ ПОСПІЛЬ, НА БУДЬ-ЯКУ ФРАЗУ ВІД РІЗНИХ ГОСТЕЙ, ВІДПОВІДАЙ ОДНАКОВО: «ТИЦ ПЕРДИЦЬ».",
        "ЗРОБИ МОМЕНТ «ТИХОГО ЛІСУ» - ПОЧНИ ЩОСЬ РОЗПОВІДАТИ І РІЗКО ЗАМОВЧИ НІБИ ЩОСЬ ЗГАДУЄШ, ПОКИ ХТОСЬ СПИТАЄ, «І ЩО ДАЛІ?» ЧИ ЩОСЬ ПОДІБНЕ.",
        *UNIVERSAL_TASKS,
    ],
    5: [
        "ЗРОБИ ВИГЛЯД ЩО ТИ НА КОГОСЬ ОБРАЗИЛАСЬ, А КОЛИ ХТОСЬ СПИТАЄ ЩО СТАЛОСЬ, ВІДПОВІДАЙ +1 ЗАВДАННЯ",
        "ПОПРОСИ КОГОСЬ ПОГРІТИ ТОБІ РУКИ",
        "ТРИЧІ ПОСПІЛЬ, НА ТРИ ФРАЗИ ВІД ОДНОГО ГОСТЯ, ВІДПОВІДАЙ «ЩО ЦЕ ЗАВДАННЯ, Я ВИГРАЛА!»",
        "ЗРОБИ ДВА ФОТО, ДЕ ВИ З КИМОСЬ ДИВИТЕСЬ В ОДНОМУ НАПРЯМКУ, НАЧЕ НА ЗОРЯНЕ НЕБО.",
        "СКАЖИ ХОЧА Б ДВОМ ЛЮДЯМ, ЩО ВОНИ СЬОГОДНІ ВИГЛЯДАЮТЬ КРАЩЕ, НІЖ НІЧНІ ВОГНІ.",
        *UNIVERSAL_TASKS,
    ],
    6: [
        "ХОЧ РАЗ ПОЖАРТУЙ, ЩО ТИ СЬОГОДНІ ОФІЦІЙНИЙ ПОСТАЧАЛЬНИК ГАРНОГО НАСТРОЮ.",
        "ОРГАНІЗУЙ МАЛЕНЬКИЙ «ТЕСТ СМАКУ» - ВИБЕРИ ЖЕРТВУ, ІІ СПИТАЙ ЯК ЙОМУ НА СМАК 5+ СТРАВ НА СТОЛІ.",
        "ПОПРАВ ОДЯГ ХОЧАБ ТРЬОМ ЛЮДЯМ ЗА СТОЛОМ",
        "ПОПРОСИ КОГОСЬ СФОТОГРАФУВАТИ ТЕБЕ БІЛЯ ЯЛИНКИ І ОДРАЗУ СКИНУТИ ТОБІ СМСКОЮ",
        "ЗРОБИ ДИВНИЙ КОМПЛІМЕНТ ОДНІЙ З НЕВІСТОК. ТАК ЩОБ ЇМ БУЛО НЕ ПО СОБІ. КОЛИ ВОНИ ПОДЯКУЮТЬ, ЗАВДАННЯ ВИКОНАНЕ",
        *UNIVERSAL_TASKS,
    ],
    7: [
        "ЗАПРОПОНУЙ КОМУСЬ «УЯВНУ ЧАШКУ ГАРЯЧОГО: ШОКОЛАДУ» - ОПИШИ СЛОВАМИ ІДЕАЛЬНИЙ НАПІЙ.",
        "РОЗКАЖИ КОРОТКУ ІСТОРІЮ АБО СПОГАД, ДЕ ГАРЯЧИЙ ШОКОЛАД АБО КАКАО ФІГУРУЄ ЯК СИМВОЛ ЗАТИШКУ.",
        "ЗРОБИ ФОТО АБО ВІДЕО, ДЕ ВИ ЦОКАЄТЕСЬ ЗА СТОЛОМ",
        "ПОПРОСИ КОГОСЬ ДЕСЕРТ, А ПОТІМ ПЕРЕПРОСИТИ І ВІДМОВИТИСЬ",
        "5.ХОЧ РАЗ СКАЖИ ФРАЗУ НА КШТАЛТ: «ЯКЩО СТАНЕ ХОЛОДНО У МЕНЕ Є КАКАО» А ПОТІМ «А HI, Я ЙОГО ЗАБУЛА».",
        *UNIVERSAL_TASKS,
    ],
}


def get_color_for_user(user_id: int) -> Optional[Dict[str, Any]]:
    cid = PREASSIGNED_COLORS.get(user_id)
    if not cid:
        return None
    return COLORS.get(cid)


def get_tasks_for_user(user_id: int) -> Optional[list[str]]:
    cid = PREASSIGNED_COLORS.get(user_id)
    if not cid:
        return None
    return COLOR_TASKS.get(cid)


# ================== СТАН SANTA ==================
class SantaConfig:
    def __init__(self) -> None:
        self.registration_open: bool = False
        self.started: bool = False
        self.budget_text: Optional[str] = None
        self.description: Optional[str] = None


SANTA = SantaConfig()

# ================== ПЕРСИСТ ==================
USERS: Dict[int, Dict[str, Any]] = {}
PENDING_ACTION: Dict[int, str] = {}
PENDING_CONTEXT: Dict[int, Any] = {}
DATA_FILE = "party_data.json"


def _base_user_template() -> Dict[str, Any]:
    return {
        "participant": False,
        "color_id": None,
        "menu_dish": None,
        "menu_drink": None,
        "menu_dessert": None,
        "tasks_done": [],          # список bool по 7 завдань
        "santa_joined": False,
        "santa_wish": None,
        "santa_child_id": None,
        "santa_id": None,
        "santa_gift_ready": False,
        "name": None,
        "username": None,
        "has_valid_code": False,
        "party_code": None,
        "feedback_requested": False,  # чи вже просили в нього відгук
        "is_admin": False,
        "postmenu_followups_blocked": False,  # блокуємо авто-нагадування після меню
    }


async def save_data():
    data = {
        "USERS": USERS,
        "SANTA": {
            "registration_open": SANTA.registration_open,
            "started": SANTA.started,
            "budget_text": SANTA.budget_text,
            "description": SANTA.description,
        },
        "PARTY": PARTY,
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Дані збережено (%d гостей)", len(USERS))
    except Exception as e:
        logger.error("Помилка збереження даних: %s", e)


async def load_data():
    global USERS, PARTY
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        USERS = {int(k): v for k, v in raw.get("USERS", {}).items()}

        santa_raw = raw.get("SANTA", {})
        SANTA.registration_open = santa_raw.get("registration_open", False)
        SANTA.started = santa_raw.get("started", False)
        SANTA.budget_text = santa_raw.get("budget_text")
        SANTA.description = santa_raw.get("description")

        party_raw = raw.get("PARTY")
        if party_raw:
            PARTY.update(party_raw)
            apply_party_to_globals()

        logger.info("Дані завантажено: %d гостей", len(USERS))
    except Exception as e:
        logger.error("Не вдалося завантажити дані: %s", e)


# ================== УТІЛІТИ ==================
async def send_gif(msg: Message, gif_id: Optional[str]):
    if not gif_id:
        return
    try:
        await msg.answer_animation(animation=gif_id)
    except Exception as e:
        logger.warning("GIF не відправився: %s", e)


def get_user(uid: int) -> Dict[str, Any]:
    if uid not in USERS:
        USERS[uid] = _base_user_template()
    u = USERS[uid]
    if uid == ADMIN_ID:
        u["is_admin"] = True
    return u


def is_feedback_time() -> bool:
    fb = PARTY.get("feedback_date")
    if not fb:
        return False
    try:
        d = datetime.strptime(fb, "%Y-%m-%d").date()
    except Exception:
        return False
    return date.today() >= d


def mark_user_active(user: Dict[str, Any]) -> None:
    """
    Позначаємо, що користувач щось натиснув / написав,
    тому «післяменюшні» автоповідомлення можна гасити.
    """
    user["postmenu_followups_blocked"] = True


async def postmenu_followups(bot: Bot, user_id: int):
    """
    Ланцюжок автоматичних повідомлень після того, як користувач заповнив меню.
    Гаситься, якщо користувач починає щось тиснути в меню.
    """
    await asyncio.sleep(random.uniform(3, 5))
    user = USERS.get(user_id)
    if not user or user.get("postmenu_followups_blocked"):
        return

    # 1. Запросити в канал
    if PARTY_CHANNEL_LINK:
        try:
            await bot.send_message(
                user_id,
                "Ще один важливий крок! 🎉\n"
                "Залеті в наш канал — там ми спілкуємось, ділимось фотками та мемами:\n"
                f"{PARTY_CHANNEL_LINK}"
            )
        except Exception as e:
            logger.warning("Не зміг надіслати нагадування про канал: %s", e)

    # 2. Почекати 1–5 хвилин
    await asyncio.sleep(random.uniform(60, 300))
    user = USERS.get(user_id)
    if not user or user.get("postmenu_followups_blocked"):
        return

    # 2.1 Нагадати про меню
    try:
        await bot.send_message(
            user_id,
            "Ось так виглядає твоє меню в боті 👇\n"
            "Завжди можеш глянути або змінити його через розділ «🍽 Моє меню» "
            "у «👤 Мій кабінет»."
        )
    except Exception as e:
        logger.warning("Не зміг надіслати нагадування про меню: %s", e)

    # 3. Ще 30 секунд → Таємний Миколайчик
    await asyncio.sleep(30)
    user = USERS.get(user_id)
    if not user or user.get("postmenu_followups_blocked"):
        return

    try:
        await bot.send_message(
            user_id,
            "Також не забувай про гру «Таємний Миколайчик» 🎅\n"
            "Як тільки все буде готово — отримаєш від мене окреме повідомлення "
            "для реєстрації в грі."
        )
    except Exception as e:
        logger.warning("Не зміг надіслати нагадування про Миколайчика: %s", e)

    # 4. Ще 30 секунд → GIF + підказка про допомогу
    await asyncio.sleep(30)
    user = USERS.get(user_id)
    if not user or user.get("postmenu_followups_blocked"):
        return

    try:
        msg = await bot.send_message(
            user_id,
            "Ну що, якщо будуть питання — я завжди тут 😉\n"
            "Натискай «❓ Допомога» в меню, а потім кнопку "
            "«✉ Звʼязатись з організатором Ніколасом»."
        )
        await send_gif(msg, START_GIF_ID)
    except Exception as e:
        logger.warning("Не зміг надіслати фінальне нагадування: %s", e)


# ================== КЛАВІАТУРИ ==================
def main_menu_kb(user: Dict[str, Any]) -> ReplyKeyboardMarkup:
    buttons: list[list[KeyboardButton]] = []

    # 1. Учасник / не учасник
    if user.get("participant"):
        # перший ряд — кабінет + Миколайчик
        buttons.append([
            KeyboardButton(text="👤 Мій кабінет"),
            KeyboardButton(text="🎅 Мій Миколайчик"),
        ])
        # другий ряд — меню + про вечірку
        buttons.append([
            KeyboardButton(text="📜 Наше меню"),
            KeyboardButton(text="ℹ️ Про вечірку"),
        ])
    else:
        # гість не підтвердив участь
        buttons.append([KeyboardButton(text="ℹ️ Про вечірку")])

    # 2. Канал + чат
    row = [KeyboardButton(text="📢 Канал вечірки")]
    row.append(KeyboardButton(text="💬 Чат вечірки"))
    buttons.append(row)

    # 3. Допомога
    buttons.append([KeyboardButton(text="❓ Допомога")])

    # 4. Відгук (якщо час)
    if user.get("participant") and is_feedback_time():
        buttons.append([KeyboardButton(text="⭐ Відгук про вечірку")])

    # 5. Адмін-панель
    if user.get("is_admin"):
        buttons.append([KeyboardButton(text="🛠 Адмін-панель")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def cabinet_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🎨 Мій образ"),
                KeyboardButton(text="📋 Мої завдання"),
            ],
            [KeyboardButton(text="🍽 Моє меню")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
    )


@router.message(F.text == "🍽 Моє меню")
async def my_menu(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("participant"):
        await message.answer("Спочатку підтверди участь у вечірці — напиши /start 🎄")
        return

    mark_user_active(user)

    dish = user.get("menu_dish")
    drink = user.get("menu_drink")
    dessert = user.get("menu_dessert")

    dish_txt = dish or "ще не вказана"
    drink_txt = drink or "ще не вказаний"
    dessert_txt = dessert or "ще не вказаний"

    text = (
        "<b>Твоє меню:</b>\n"
        f"• Страва: {dish_txt}\n"
        f"• Напій: {drink_txt}\n"
        f"• Десерт: {dessert_txt}\n"
    )

    # Якщо меню ще взагалі не заповнене — пропонуємо заповнити
    if not dish and not drink and not dessert:
        text += (
            "\nЗараз у тебе ще нічого не вказано.\n"
            "Можеш заповнити меню прямо зараз 👇"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📝 Заповнити меню зараз",
                        callback_data="menu_now",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⏱ Пізніше додам",
                        callback_data="menu_later",
                    )
                ],
            ]
        )
        await message.answer(text, reply_markup=kb)
        return

    # Якщо щось вже є — питаємо, що саме змінити
    text += (
        "\nЩо хочеш змінити?\n"
        "Можеш обрати варіант нижче, або вручну написати:\n"
        "«Страва: ...», «Напій: ...» або «Десерт: ...»."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏ Змінити страву", callback_data="edit_dish"),
            ],
            [
                InlineKeyboardButton(text="🥂 Змінити напій", callback_data="edit_drink"),
            ],
            [
                InlineKeyboardButton(text="🍰 Змінити десерт", callback_data="edit_dessert"),
            ],
        ]
    )

    await message.answer(text, reply_markup=kb)


@router.message(F.text == "👤 Мій кабінет")
async def cabinet_menu(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("participant"):
        await message.answer("Спочатку підтверди участь у вечірці — напиши /start 🎄")
        return
    mark_user_active(user)
    await message.answer("Твій кабінет гостя:", reply_markup=cabinet_menu_kb())


def santa_join_menu_kb(user: Dict[str, Any]) -> InlineKeyboardMarkup:
    if not SANTA.registration_open:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Реєстрація ще не відкрита", callback_data="noop")]
            ]
        )
    rows = []
    if not user.get("santa_joined"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Хочу брати участь",
                    callback_data="santa_join",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="❌ Не хочу, пас",
                    callback_data="santa_leave",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚪 Вийти з гри (і з вечірки)",
                    callback_data="santa_leave",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def santa_chat_kb(user: Dict[str, Any]) -> InlineKeyboardMarkup:
    rows = []
    if user.get("santa_child_id"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="✉ Написати підопічному", callback_data="msg_child"
                )
            ]
        )
    if user.get("santa_id"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="✉ Написати моєму Миколайчику", callback_data="msg_santa"
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="❓ Питання про Миколайчика",
                callback_data="ask_santa_admin",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎉 Налаштування вечірки", callback_data="admin_party")],
            [InlineKeyboardButton(text="👥 Список гостей", callback_data="admin_guests")],
            [InlineKeyboardButton(text="🎅 Налаштування Миколайчика", callback_data="admin_santa")],
            [InlineKeyboardButton(text="📢 Оголошення в приват", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="💌 Листівка в канал", callback_data="admin_card")],
        ]
    )


def admin_santa_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔓 Відкрити/закрити реєстрацію",
                    callback_data="admin_toggle_santa_reg",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Задати/змінити бюджет",
                    callback_data="admin_set_budget",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📄 Задати опис гри",
                    callback_data="admin_set_santa_desc",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎲 Згенерувати пари",
                    callback_data="admin_gen_pairs",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📨 Розіслати підопічних",
                    callback_data="admin_notify_pairs",
                )
            ],
        ]
    )


@router.message(F.text == "🛠 Адмін-панель")
async def admin_panel_button(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Це тільки для адміна 🙃")
        return
    user = get_user(message.from_user.id)
    mark_user_active(user)
    await message.answer("Привіт, організаторе 🎄 Що робимо?", reply_markup=admin_menu_kb())


# ================== ХЕНДЛЕРИ КОРИСТУВАЧІВ ==================
@router.message(F.animation)
async def get_gif_id(message: Message):
    print(message.animation.file_id)
    await message.answer(f"file_id:\n<code>{message.animation.file_id}</code>")

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    is_known_guest = user_id in PREASSIGNED_COLORS

    # якщо гість відомий по списку – автоматично даємо доступ до вечірки
    if is_known_guest and PARTY.get("active") and PARTY.get("code"):
        current_code = PARTY["code"]
        if not user.get("has_valid_code") or user.get("party_code") != current_code:
            user["has_valid_code"] = True
            user["party_code"] = current_code
            await save_data()
    user["name"] = message.from_user.full_name
    user["username"] = message.from_user.username

    PENDING_ACTION.pop(user_id, None)

    if not PARTY.get("active") or not PARTY.get("code"):
        await message.answer(
            "Зараз для тебе немає активних вечірок 😌\n\n"
            "Як тільки організатор створить нову тусу і дасть код — ти зможеш зайти сюди знову."
        )
        return

    if (
        user.get("participant")
        and user.get("party_code") == PARTY["code"]
        and user.get("has_valid_code")
    ):
        await message.answer(
            "Радий бачити тебе знову 🎄\nТи вже в списку гостей. Ось твоє меню 👇",
            reply_markup=main_menu_kb(user),
        )
        await send_gif(message, START_GIF_ID)
        return

    if not user.get("has_valid_code") or user.get("party_code") != PARTY["code"]:
        await message.answer(
            "Щоб зайти на вечірку, введи, будь ласка, <b>код вечірки</b>, який дав тобі організатор."
        )
        PENDING_ACTION[user_id] = "enter_party_code"
        return

    text = (
        "Вау! ✨\n\n"
        f"Ти відкрив бота вечірки <b>«{PARTY_NAME}»</b>!\n\n"
        "Підтверди свою участь нижче — я додам тебе до списку гостей "
        "і допоможу підготуватись до свята 😉\n\n"
        "То ти з нами на вечірці?"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎉 Так, я буду!", callback_data="party_yes"),
            ],
            [
                InlineKeyboardButton(
                    text="🙈 Я просто дивлюсь", callback_data="party_no"
                )
            ],
        ]
    )

    await message.answer(text, reply_markup=kb)
    await send_gif(message, START_GIF_ID)


@router.callback_query(F.data == "party_yes")
async def cb_party_yes(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user["participant"] = True
    await save_data()

    loc_html = f'<span class="tg-spoiler">{PARTY_LOCATION}</span>'
    text = (
        "Для початку — основні дані та правила. Ознайомся і підтверди участь у вечірці:\n\n"
        f"🎄 <b>{PARTY_NAME}</b>\n"
        f"📍 {loc_html}\n"
        f"🗓 {PARTY_DATES_TEXT}\n\n"
        f"{party_rules_text()}"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Мені все підходить", callback_data="party_confirm_rules"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Я передумав(ла)", callback_data="party_no_after_rules"
                )
            ],
        ]
    )

    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "party_confirm_rules")
async def cb_party_confirm_rules(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)

    color = get_color_for_user(user_id)
    tasks = get_tasks_for_user(user_id)

    if color:
        # запам'ятати color_id
        for cid, c in COLORS.items():
            if c is color:
                user["color_id"] = cid
                break
        await save_data()
        logger.info(
            "Користувач %s отримав образ %s",
            user.get("name") or user_id,
            color["label"],
        )

        # 1. Образ
        first_text = (
            "Чудово! Тоді ловиш свій готовий образ 😊\n\n"
            f"Твій колір: <b>{color['label']}</b>\n"
            f"Твоя роль: <b>{color['role']}</b>"
        )
        await callback.message.edit_text(first_text)

        # 2. Завдання під спойлером (через невелику паузу)
        if tasks:
            await asyncio.sleep(2)
            tasks_text = "\n".join(f"• {t}" for t in tasks)
            await callback.message.answer(
                "А також твої завдання — заховані під спойлером:\n\n"
                f'<span class="tg-spoiler">{tasks_text}</span>'
            )

        # 3. Пропозиція заповнити меню
        await asyncio.sleep(1)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📝 Заповнити меню зараз",
                        callback_data="menu_now",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⏱ Пізніше додам",
                        callback_data="menu_later",
                    )
                ],
            ]
        )
        await callback.message.answer(
            "Завдання ти ще встигнеш перечитати 🙂\n"
            "Пропоную одразу заповнити твоє меню: страву, напій і десерт.",
            reply_markup=kb,
        )
    else:
        await callback.message.edit_text(
            "Ти підтвердив участь 🎄\n\n"
            "У цього бота немає для тебе заздалегідь призначеного кольору.\n"
            "Напиши, будь ласка, організатору через «📞 Звʼязатись з організатором», "
            "щоб узгодити образ і меню.",
            reply_markup=main_menu_kb(user),
        )


@router.callback_query(F.data == "menu_now")
async def cb_menu_now(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    if not user.get("participant"):
        await callback.answer("Спочатку підтверди участь через /start 🎄", show_alert=True)
        return
    await callback.message.answer(
        "Напиши, будь ласка, яку <b>страву</b> ти плануєш принести."
    )
    PENDING_ACTION[user_id] = "set_dish"


@router.callback_query(F.data == "menu_later")
async def cb_menu_later(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    if not user.get("participant"):
        await callback.answer("Спочатку підтверди участь через /start 🎄", show_alert=True)
        return
    await callback.message.answer(
        "Окей, без поспіху 🙂\n"
        "У розділі «👤 Мій кабінет» → «🍽 Моє меню» ти завжди зможеш додати "
        "або змінити страву, напій і десерт.",
        reply_markup=main_menu_kb(user),
    )

@router.callback_query(F.data == "edit_dish")
async def cb_edit_dish(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("participant"):
        await callback.answer("Спочатку підтверди участь через /start 🎄", show_alert=True)
        return
    await callback.message.answer("Добре, напиши нову <b>страву</b>, яку ти плануєш принести.")
    PENDING_ACTION[callback.from_user.id] = "edit_dish"
    await callback.answer()


@router.callback_query(F.data == "edit_drink")
async def cb_edit_drink(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("participant"):
        await callback.answer("Спочатку підтверди участь через /start 🎄", show_alert=True)
        return
    await callback.message.answer("Напиши, будь ласка, новий <b>напій</b> для меню.")
    PENDING_ACTION[callback.from_user.id] = "edit_drink"
    await callback.answer()


@router.callback_query(F.data == "edit_dessert")
async def cb_edit_dessert(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("participant"):
        await callback.answer("Спочатку підтверди участь через /start 🎄", show_alert=True)
        return
    await callback.message.answer("Напиши, будь ласка, новий <b>десерт</b> для меню.")
    PENDING_ACTION[callback.from_user.id] = "edit_dessert"
    await callback.answer()


@router.callback_query(F.data == "party_no_after_rules")
async def cb_party_no_after_rules(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user["participant"] = False
    await save_data()
    await callback.message.edit_text(
        "Окей, я не буду записувати тебе у список гостей 🙈\n"
        "Якщо передумаєш — напиши /start."
    )


@router.callback_query(F.data == "party_no")
async def cb_party_no(callback: CallbackQuery):
    await callback.message.edit_text(
        "Шкода 🥺\n\n"
        f"Можеш просто підглядати за підготовкою до «{PARTY_NAME}».\n"
        "А якщо передумаєш і захочеш приєднатися — просто напиши /start ❤️"
    )


@router.message(F.text == "ℹ️ Про вечірку")
async def about_party(message: Message):
    user = get_user(message.from_user.id)
    mark_user_active(user)
    loc_html = f'<span class="tg-spoiler">{PARTY_LOCATION}</span>'
    text = (
        f"🎄 <b>{PARTY_NAME}</b>\n"
        f"📍 {loc_html}\n"
        f"🗓 {PARTY_DATES_TEXT}\n\n"
        f"{party_rules_text(include_cta=False)}"
    )
    await message.answer(text)


@router.message(F.text == "📢 Канал вечірки")
async def party_channel(message: Message):
    user = get_user(message.from_user.id)
    mark_user_active(user)
    if PARTY_CHANNEL_LINK:
        await message.answer(
            "Ось канал вечірки. Там будуть оголошення, листівки та новини ✨\n"
            f"{PARTY_CHANNEL_LINK}"
        )
    else:
        await message.answer(
            "Організатор ще не додав посилання на канал вечірки 🤔"
        )


@router.message(F.text == "💬 Чат вечірки")
async def party_chat(message: Message):
    user = get_user(message.from_user.id)
    mark_user_active(user)
    if PARTY_CHAT_LINK:
        await message.answer(
            "Ось чат вечірки. Там можна спілкуватися, ділитись фотками та мемами 🥳\n"
            f"{PARTY_CHAT_LINK}"
        )
    else:
        await message.answer(
            "Організатор ще не додав посилання на чат вечірки 🤔"
        )


@router.message(F.text == "🎨 Мій образ")
async def my_look(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("participant"):
        await message.answer("Спочатку підтверди участь у вечірці — напиши /start 🎄")
        return

    mark_user_active(user)

    color_id = user.get("color_id")
    if not color_id:
        await message.answer("Для тебе ще не призначено колір. Напиши організатору 🙈")
        return

    color = COLORS.get(color_id)
    if not color:
        await message.answer("Не можу знайти твій колір, напиши організатору.")
        return

    text = (
        "Ось інформація по твоєму образу:\n\n"
        f"Колір: <b>{color['label']}</b>\n"
        f"Роль: <b>{color['role']}</b>\n\n"
        "Завдання дивись у розділі «📋 Мої завдання» 😉"
    )
    await message.answer(text)


@router.message(F.text == "📜 Наше меню")
async def guests_menu_for_user(message: Message):
    user = get_user(message.from_user.id)
    mark_user_active(user)

    lines = ["📜 <b>Наше меню</b>\n"]
    has_any = False

    for uid, data in USERS.items():
        if not data.get("participant"):
            continue
        has_any = True

        name = data.get("name") or f"Гість {uid}"
        color = get_color_for_user(uid)
        if color:
            color_txt = color["label"]
            role_txt = color["role"]
        else:
            color_txt = "—"
            role_txt = "—"

        dish_txt = data.get("menu_dish") or "—"
        drink_txt = data.get("menu_drink") or "—"
        dessert_txt = data.get("menu_dessert") or "—"
        santa_txt = "✅" if data.get("santa_joined") else "❌"

        lines.append(
            f"• <b>{name}</b>\n"
            f"  Образ: {color_txt}\n"
            f"  Роль: {role_txt}\n"
            f"  Страва: {dish_txt}\n"
            f"  Напій: {drink_txt}\n"
            f"  Десерт: {dessert_txt}\n"
            f"  У грі Миколайчика: {santa_txt}\n"
        )

    if not has_any:
        lines.append("Поки ще ніхто не додав своє меню 🤔")

    await message.answer("\n".join(lines))


def ensure_tasks_state(user: Dict[str, Any]) -> list[int]:
    """
    0 = ще не виконав
    1 = виконав (✅)
    2 = провалено / зловили (❌)
    """
    color_id = user.get("color_id")
    if not color_id or color_id not in COLOR_TASKS:
        return []

    total = len(COLOR_TASKS[color_id])
    raw = user.get("tasks_done") or []

    norm: list[int] = []
    for v in raw:
        if isinstance(v, bool):
            norm.append(1 if v else 0)
        elif isinstance(v, int) and v in (0, 1, 2):
            norm.append(v)
        else:
            norm.append(0)

    if len(norm) < total:
        norm += [0] * (total - len(norm))
    if len(norm) > total:
        norm = norm[:total]

    user["tasks_done"] = norm
    return norm

def task_state_icon(state: int) -> str:
    if state == 1:
        return "✅"
    if state == 2:
        return "❌"
    return "⬜"

def tasks_inline_kb(user: Dict[str, Any]) -> InlineKeyboardMarkup:
    color_id = user.get("color_id")
    tasks = COLOR_TASKS.get(color_id) or []
    done = ensure_tasks_state(user)
    rows = []
    for idx, _ in enumerate(tasks):
        mark = task_state_icon(done[idx])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} Завдання {idx + 1}",
                    callback_data=f"task_toggle:{idx}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="✉ Запит до організатора",
                callback_data="task_ask_org",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "📋 Мої завдання")
async def my_tasks(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("participant"):
        await message.answer("Спочатку підтверди участь у вечірці — напиши /start 🎄")
        return

    mark_user_active(user)

    color_id = user.get("color_id")
    if not color_id or color_id not in COLOR_TASKS:
        await message.answer("Для тебе поки немає списку завдань. Напиши організатору.")
        return

    tasks = COLOR_TASKS[color_id]
    done = ensure_tasks_state(user)

    lines = ["📋 <b>Твої завдання</b>\n"]
    for idx, t in enumerate(tasks):
        mark = task_state_icon(done[idx])
        lines.append(f"{mark} <b>{idx + 1}.</b> {t}")
    lines.append(
        "\nПозначення:\n"
        "⬜ — ще не виконав\n"
        "✅ — виконав\n"
        "❌ — завдання провалене / тебе зловили 😏\n\n"
        "Натискай на завдання, щоб змінити його стан по колу."
    )
    lines.append(
        "\nЯкщо завдання повʼязане з фото або треба підтвердити у організатора — "
        "натисни «✉ Запит до організатора»."
    )

    await message.answer("\n".join(lines), reply_markup=tasks_inline_kb(user))


@router.callback_query(F.data.startswith("task_toggle:"))
async def cb_task_toggle(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("participant"):
        await callback.answer("Спочатку підтверди участь у вечірці — напиши /start 🎄", show_alert=True)
        return

    mark_user_active(user)

    color_id = user.get("color_id")
    if not color_id or color_id not in COLOR_TASKS:
        await callback.answer("Для тебе поки немає завдань.", show_alert=True)
        return

    try:
        idx = int(callback.data.split(":")[1])
    except Exception:
        await callback.answer("Помилка з індексом завдання.", show_alert=True)
        return

    tasks = COLOR_TASKS[color_id]
    done = ensure_tasks_state(user)
    if idx < 0 or idx >= len(tasks):
        await callback.answer("Невідоме завдання.", show_alert=True)
        return

    # 0 -> 1 -> 2 -> 0
    done[idx] = (done[idx] + 1) % 3
    user["tasks_done"] = done
    await save_data()
    await callback.answer("Оновив стан завдання ✅")

    lines = ["📋 <b>Твої завдання</b>\n"]
    for i, t in enumerate(tasks):
        mark = task_state_icon(done[i])
        lines.append(f"{mark} <b>{i + 1}.</b> {t}")
    lines.append(
        "\nПозначення:\n"
        "⬜ — ще не виконав\n"
        "✅ — виконав\n"
        "❌ — завдання провалене / тебе зловили 😏\n\n"
        "Натискай на завдання, щоб змінювати стан по колу."
    )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=tasks_inline_kb(user),
    )


@router.callback_query(F.data == "task_ask_org")
async def cb_task_ask_org(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    mark_user_active(user)
    PENDING_ACTION[user_id] = "task_ask_org"
    msg = await callback.message.answer(
        "Напиши коротко про завдання, яке хочеш підтвердити, "
        "а потім у <b>reply на це повідомлення</b> надішли <b>одне фото</b> або текст.\n"
        "Все, що надішлеш у reply, я перешлю організатору."
    )
    # реєструємо міст для reply (гость → адмін)
    register_bridge_message(
        chat_id=msg.chat.id,
        message_id=msg.message_id,
        peer_id=ADMIN_ID,
        prefix_to_peer="Запит щодо завдання від гостя: ",
        reply_prefix_back="Відповідь організатора щодо завдання: ",
    )
    await callback.answer()


@router.message(F.text == "🎅 Мій Миколайчик")
async def my_santa(message: Message):
    user = get_user(message.from_user.id)

    if not user.get("participant"):
        await message.answer("Спочатку підтвердь, що ти будеш на вечірці — натисни /start 🎄")
        return

    mark_user_active(user)

    await send_gif(message, SANTA_GIF_ID)

    if not SANTA.registration_open and not user.get("santa_joined"):
        await message.answer(
            "Організатор ще не відкрив реєстрацію на гру «Таємний Миколайчик». "
            "Трохи терпіння, скоро все запустимо 🎅"
        )
        return

    if not user.get("santa_joined"):
        budget_part = (
            f"Орієнтовний бюджет: <b>{SANTA.budget_text}</b>\n"
            if SANTA.budget_text
            else ""
        )
        desc_part = f"{SANTA.description}\n\n" if SANTA.description else ""
        text = (
            f"{SANTA_BASE_RULES}\n\n"
            f"{budget_part}"
            f"{desc_part}"
            "Якщо погоджуєшся з правилами — приєднуйся до гри нижче.\n\n"
            "Щоб написати або відповісти у грі, ти завжди обираєш в меню кнопку:\n"
            "«✉ Написати підопічному» або «✉ Написати моєму Миколайчику»."
        )
        await message.answer(text, reply_markup=santa_join_menu_kb(user))
        return

    if not SANTA.started:
        await message.answer(
            "Ти вже в грі 🎅, але пари ще не розподілені. "
            "Чекаємо, поки організатор запустить жеребкування."
        )
        return

    child_id = user.get("santa_child_id")
    santa_id = user.get("santa_id")

    parts = ["🎅 <b>Твій Миколайчик</b>"]

    if child_id:
        child = USERS.get(child_id)
        parts.append("\n\n<b>Твій підопічний:</b>\n")
        parts.append(child.get("name") or "Гість")
        wish = child.get("santa_wish")
        if wish:
            parts.append("\nПобажання / анти-побажання:\n")
            parts.append(wish)
        else:
            parts.append("\nОбрав(ла) варіант: «Сюрприз» 🎁")

    if santa_id:
        parts.append(
            "\n\nУ тебе також є свій Таємний Миколайчик — але хто це, я не скажу 😏"
        )

    parts.append(
        "\n\nЩоб написати або відповісти у грі, просто обирай у меню:\n"
        "• «✉ Написати підопічному» — щоб написати тому, кому готуєш подарунок\n"
        "• «✉ Написати моєму Миколайчику» — щоб написати тому, хто готує подарунок для тебе\n\n"
        "Кожне нове повідомлення починається з натискання відповідної кнопки — так зберігається анонімність."
    )
    await message.answer("".join(parts), reply_markup=santa_chat_kb(user))


@router.message(F.text == "⭐ Відгук про вечірку")
async def feedback_menu(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("participant"):
        await message.answer("Ця опція тільки для гостей вечірки 🎄")
        return
    if not is_feedback_time():
        await message.answer("Ще рано для відгуків 😉")
        return

    mark_user_active(user)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Написати відгук", callback_data="fb_start"
                )
            ]
        ]
    )

    await message.answer(
        "Можеш залишити відгук про вечірку, підготовку або цього бота.\n"
        "Можна надсилати кілька повідомлень (текст, фото, відео), "
        "а потім натиснути кнопку «✅ Відправити відгук».\n"
        "Якщо хочеш анонімно — просто напиши це в одному з повідомлень.",
        reply_markup=kb,
    )


@router.callback_query(F.data == "fb_start")
async def cb_fb_start(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("participant") or not is_feedback_time():
        await callback.answer("Поки що не можна залишати відгук.", show_alert=True)
        return

    mark_user_active(user)

    PENDING_ACTION[callback.from_user.id] = "fb_collect"
    PENDING_CONTEXT[callback.from_user.id] = {"fb_msgs": []}

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Відправити відгук", callback_data="fb_send"
                )
            ]
        ]
    )

    await callback.message.answer(
        "Надсилай сюди все, що хочеш сказати про вечірку.\n"
        "Можна кілька повідомлень, фото, відео.\n"
        "Коли закінчиш — натисни «✅ Відправити відгук».",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "fb_send")
async def cb_fb_send(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)

    ctx = PENDING_CONTEXT.get(user_id) or {}
    fb_msgs = ctx.get("fb_msgs") or []

    if not fb_msgs:
        await callback.answer("Ти ще нічого не написав у відгуку 🙈", show_alert=True)
        return

    bot: Bot = callback.message.bot

    username = user.get("username") or "-"
    header = (
        f"⭐ Фідбек від {user.get('name') or user_id} "
        f"(@{username}):"
    )

    try:
        await bot.send_message(ADMIN_ID, header)
        for chat_id, msg_id in fb_msgs:
            # просто копіюємо все, що накидав у фідбек
            await bot.copy_message(ADMIN_ID, chat_id, msg_id)

        await callback.message.answer(
            "Дякую за відгук! Я передав його організатору 🫶",
            reply_markup=main_menu_kb(user),
        )
    except Exception as e:
        logger.exception("Не зміг передати фідбек організатору: %s", e)
        await callback.message.answer("Не зміг передати фідбек організатору 😔")

    # чистимо стан
    PENDING_ACTION.pop(user_id, None)
    PENDING_CONTEXT.pop(user_id, None)
    user["feedback_requested"] = True
    await save_data()
    await callback.answer()


@router.message(F.text == "❓ Допомога")
async def help_menu(message: Message):
    user = get_user(message.from_user.id)
    mark_user_active(user)
    text = (
        "❓ <b>Допомога</b>\n\n"
        "Коротко, що вміє цей бот:\n\n"
        "• «👤 Мій кабінет» — твій образ, завдання та меню.\n"
        "• «🎅 Мій Миколайчик» — гра та анонімне спілкування.\n"
        "• «📜 Наше меню» — хто що приносить.\n"
        "• «📢 Канал вечірки» — оголошення та листівки.\n"
        "• «💬 Чат вечірки» — живе спілкування.\n\n"
        "ВАЖЛИВО: якщо ти просто пишеш мені повідомлення, його бачу тільки я — бот.\n"
        "Щоб організатор або Миколайчик/підопічний побачили текст, "
        "завжди користуйся відповідними кнопками в меню.\n\n"
        "Щоб написати організатору — натисни кнопку нижче.\n"
        "Якщо хочеш анонімно — додай слово «анонімно» в текст."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉ Звʼязатись з організатором Ніколасом",
                    callback_data="ask_org",
                )
            ]
        ]
    )
    await message.answer(text, reply_markup=kb)


# ================== CALLBACKS: SANTA REG, CHAT, FEEDBACK, ORG ==================
@router.callback_query(F.data == "santa_join")
async def cb_santa_join(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not SANTA.registration_open:
        await callback.answer("Реєстрація ще не відкрита 🙈", show_alert=True)
        return
    user["santa_joined"] = True
    user["santa_gift_ready"] = False
    await save_data()
    await callback.message.edit_text(
        "Ти в грі «Таємний Миколайчик» 🎅\n\n"
        "Напиши, будь ласка, що ти хотів/ла б отримати або чого точно не треба дарувати.\n"
        "Якщо хочеш повний сюрприз — напиши просто «Сюрприз».",
    )
    PENDING_ACTION[callback.from_user.id] = "set_santa_wish"


@router.callback_query(F.data == "santa_leave")
async def cb_santa_leave(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user_id = callback.from_user.id

    logger.info("Користувач %s вийшов з вечірки та гри Santa", user.get("name") or user_id)

    # Повністю скидаємо стан
    USERS[user_id] = _base_user_template()
    await save_data()

    await callback.message.edit_text(
        "Я виключив тебе з гри «Таємний Миколайчик» і з вечірки. "
        "Якщо це помилка — ти завжди можеш почати спочатку через /start."
    )


@router.callback_query(F.data == "msg_child")
async def cb_msg_child(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("santa_child_id"):
        await callback.answer("У тебе поки немає підопічного 🤔", show_alert=True)
        return
    if not SANTA.started:
        await callback.answer("Гра ще не запущена, пари не активні 🙈", show_alert=True)
        return
    mark_user_active(user)
    PENDING_ACTION[callback.from_user.id] = "msg_child"
    await callback.message.answer(
        "Напиши повідомлення, яке я анонімно перешлю твоєму підопічному 👇\n\n"
        "Щоб відповісти пізніше ще раз — знову обери в меню «✉ Написати підопічному»."
    )


@router.callback_query(F.data == "msg_santa")
async def cb_msg_santa(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("santa_id"):
        await callback.answer("У тебе поки немає Миколайчика 🤔", show_alert=True)
        return
    if not SANTA.started:
        await callback.answer("Гра ще не запущена, пари не активні 🙈", show_alert=True)
        return
    mark_user_active(user)
    PENDING_ACTION[callback.from_user.id] = "msg_santa"
    await callback.message.answer(
        "Напиши повідомлення, яке я анонімно перешлю твоєму Миколайчику 👇\n\n"
        "Щоб відповісти ще раз — знову обери в меню «✉ Написати моєму Миколайчику»."
    )


@router.callback_query(F.data == "ask_santa_admin")
async def cb_ask_santa_admin(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    mark_user_active(user)
    PENDING_ACTION[callback.from_user.id] = "ask_santa_admin"
    await callback.message.answer(
        "Напиши своє питання про Таємного Миколайчика.\n"
        "Я перешлю його організатору. Можеш додати «анонімно» у текст."
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "ask_org")
async def cb_ask_org(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    mark_user_active(user)
    PENDING_ACTION[callback.from_user.id] = "ask_org"
    await callback.message.answer(
        "Напиши своє повідомлення організатору. "
        "Якщо хочеш анонімно — додай слово «анонімно» у текст."
    )


# ================== АДМІН ==================
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Ти не виглядаєш як організатор цієї тусовки 😏")
        return
    user = get_user(message.from_user.id)
    mark_user_active(user)
    await message.answer("Привіт, організаторе 🎄 Що робимо?", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_guests")
async def admin_guests(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return

    lines = ["👥 <b>Гості вечірки</b>"]
    has_any = False

    for uid, data in USERS.items():
        if not data.get("participant"):
            continue
        has_any = True
        name = data.get("name") or f"id {uid}"
        color = get_color_for_user(uid)
        if color:
            color_txt = color["label"]
            role_txt = color["role"]
        else:
            color_txt = "-"
            role_txt = "-"

        dish_txt = data.get("menu_dish") or "—"
        drink_txt = data.get("menu_drink") or "—"
        dessert_txt = data.get("menu_dessert") or "—"
        santa_txt = "✅" if data.get("santa_joined") else "❌"
        gift_txt = "🎁" if data.get("santa_gift_ready") else "—"

        lines.append(
            f"• <b>{name}</b>\n"
            f"  Колір: {color_txt}\n"
            f"  Роль: {role_txt}\n"
            f"  Страва: {dish_txt}\n"
            f"  Напій: {drink_txt}\n"
            f"  Десерт: {dessert_txt}\n"
            f"  Santa: {santa_txt} | Подарунок готовий: {gift_txt}\n"
        )

    if not has_any:
        lines.append("Поки нікого немає.")

    await callback.message.edit_text("\n".join(lines), reply_markup=admin_menu_kb())


def admin_party_menu_kb() -> InlineKeyboardMarkup:
    buttons = []

    buttons.append(
        [
            InlineKeyboardButton(
                text="🆕 Створити / оновити вечірку",
                callback_data="admin_party_new",
            )
        ]
    )

    if PARTY.get("active"):
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🚫 Деактивувати вечірку",
                    callback_data="admin_party_deactivate",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "admin_party")
async def admin_party(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return

    status = "активна ✅" if PARTY.get("active") else "неактивна ❌"
    code = PARTY.get("code") or "ще не згенеровано"

    text = (
        "🎉 <b>Налаштування вечірки</b>\n\n"
        f"Статус: {status}\n"
        f"Назва: {PARTY_NAME}\n"
        f"Локація: {PARTY_LOCATION}\n"
        f"Дати: {PARTY_DATES_TEXT}\n"
        f"Код для гостей: <code>{code}</code>\n\n"
        "Спочатку створи або онови вечірку, потім відправ код гостям."
    )
    await callback.message.edit_text(text, reply_markup=admin_party_menu_kb())


@router.callback_query(F.data == "admin_party_new")
async def admin_party_new(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    PENDING_ACTION[callback.from_user.id] = "admin_party_name"
    await callback.message.answer(
        "Введи назву вечірки (наприклад: «Різдвяний спектр»)."
    )


@router.callback_query(F.data == "admin_party_deactivate")
async def admin_party_deactivate(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    PARTY["active"] = False
    PARTY["code"] = None
    await save_data()
    await callback.message.answer(
        "Я деактивував вечірку. Гості не зможуть зайти, поки ти не створиш нову.",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(F.data == "admin_santa")
async def admin_santa(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return

    reg_state = "відкрита ✅" if SANTA.registration_open else "закрита ❌"
    started_state = "запущена 🎲" if SANTA.started else "ще не запущена"
    budget = SANTA.budget_text or "ще не заданий"
    desc = SANTA.description or "опис не заданий"

    text = (
        "🎅 <b>Налаштування Таємного Миколайчика</b>\n\n"
        f"Реєстрація: {reg_state}\n"
        f"Стан гри: {started_state}\n"
        f"Бюджет: {budget}\n"
        f"Опис: {desc}\n"
    )
    await callback.message.edit_text(text, reply_markup=admin_santa_menu_kb())


@router.callback_query(F.data == "admin_toggle_santa_reg")
async def admin_toggle_santa_reg(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return

    if not SANTA.registration_open and not SANTA.budget_text:
        await callback.answer("Спочатку задай бюджет для гри 💰", show_alert=True)
        return

    SANTA.registration_open = not SANTA.registration_open
    await save_data()
    await admin_santa(callback)


@router.callback_query(F.data == "admin_set_budget")
async def admin_set_budget(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    PENDING_ACTION[callback.from_user.id] = "admin_set_budget"
    await callback.message.answer(
        "Напиши текст бюджету для гри (наприклад: «до 600 грн»)."
    )


@router.callback_query(F.data == "admin_set_santa_desc")
async def admin_set_santa_desc(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    PENDING_ACTION[callback.from_user.id] = "admin_set_santa_desc"
    await callback.message.answer(
        "Напиши опис гри «Таємний Миколайчик» (що важливо знати гостям)."
    )


@router.callback_query(F.data == "admin_gen_pairs")
async def admin_gen_pairs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return

    santa_players = [uid for uid, data in USERS.items() if data.get("santa_joined")]
    if len(santa_players) < 2:
        await callback.answer("У грі замало людей для пар 😅", show_alert=True)
        return

    random.shuffle(santa_players)

    for uid in santa_players:
        USERS[uid]["santa_child_id"] = None
        USERS[uid]["santa_id"] = None

    n = len(santa_players)
    for i, santa_uid in enumerate(santa_players):
        child_uid = santa_players[(i + 1) % n]
        USERS[santa_uid]["santa_child_id"] = child_uid
        USERS[child_uid]["santa_id"] = santa_uid

    SANTA.started = True
    await save_data()

    logger.info("Згенеровано пари Миколайчика для %d учасників", len(santa_players))

    await callback.message.edit_text(
        f"Пари Таємного Миколайчика згенеровано 🎲\nУчасників у грі: {len(santa_players)}",
        reply_markup=admin_santa_menu_kb(),
    )


@router.callback_query(F.data == "admin_notify_pairs")
async def admin_notify_pairs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return

    bot: Bot = callback.message.bot
    count = 0
    for uid, data in USERS.items():
        if not data.get("santa_joined"):
            continue
        child_id = data.get("santa_child_id")
        if not child_id:
            continue
        child = USERS.get(child_id)
        if not child:
            continue

        parts = [
            "🎅 <b>Твій підопічний у грі «Таємний Миколайчик»</b>\n",
            f"Імʼя: <b>{child.get('name', 'Гість')}</b>",
        ]
        wish = child.get("santa_wish")
        if wish:
            parts.append("\nПобажання / анти-побажання:\n")
            parts.append(wish)
        else:
            parts.append("\nОбрав(ла) варіант: «Сюрприз» 🎁")

        parts.append(
            "\n\nНе пались завчасно 😉 "
            "Можеш написати йому/їй через меню «🎅 Мій Миколайчик».\n"
            "Щоб написати — обирай «✉ Написати підопічному» в меню бота."
        )
        text = "".join(parts)
        try:
            await bot.send_message(uid, text)
            count += 1
        except Exception as e:
            logger.exception("Не зміг надіслати пару Santa користувачу %s: %s", uid, e)

    await callback.message.edit_text(
        f"Розіслав інформацію про підопічних {count} учасникам 🎄",
        reply_markup=admin_santa_menu_kb(),
    )


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    PENDING_ACTION[callback.from_user.id] = "admin_broadcast"
    await callback.message.answer(
        "Напиши текст оголошення. Я надішлю його всім учасникам у приват.\n"
        "Якщо хочеш оформити окрему красиву листівку в канал — обери «💌 Листівка в канал»."
    )


@router.callback_query(F.data == "admin_card")
async def admin_card(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    PENDING_ACTION[callback.from_user.id] = "admin_card"
    await callback.message.answer(
        "Напиши текст листівки. Я покажу тобі превʼю, а потім ти зможеш відправити її в канал."
    )


@router.callback_query(F.data == "admin_card_publish")
async def admin_card_publish(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    text = PENDING_CONTEXT.pop(callback.from_user.id, None)
    if not text:
        await callback.answer("Немає тексту листівки 🤔", show_alert=True)
        return
    if not PARTY_CHANNEL_LINK:
        await callback.message.answer(
            "PARTY_CHANNEL_LINK не заданий, не знаю, куди відправити листівку. "
            "Додай змінну середовища і перезапусти сервіс."
        )
        return
    try:
        await callback.message.bot.send_message(PARTY_CHANNEL_LINK, text)
        await callback.message.edit_text("Листівку опубліковано в каналі 🎄")
    except Exception as e:
        logger.exception("Не зміг опублікувати листівку в каналі: %s", e)
        await callback.message.answer("Не зміг опублікувати листівку в каналі 😔")


@router.callback_query(F.data == "admin_card_cancel")
async def admin_card_cancel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    PENDING_CONTEXT.pop(callback.from_user.id, None)
    await callback.message.edit_text("Скасовано відправку листівки.")


# ================== /cancel ==================
@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    uid = message.from_user.id
    user = get_user(uid)
    if uid in PENDING_ACTION:
        PENDING_ACTION.pop(uid, None)
        await message.answer(
            "Скасовано ✅ Можеш користуватись меню нижче.", reply_markup=main_menu_kb(user)
        )
    else:
        await message.answer("Нічого скасовувати 😉", reply_markup=main_menu_kb(user))


@router.message(F.reply_to_message)
async def reply_bridge(message: Message):
    """
    Міст для всіх варіантів:
    - гість ↔ організатор
    - Santa ↔ підопічний
    - запит по завданнях
    Працює багаторазово за рахунок дзеркальних якірів.
    """
    key = (message.chat.id, message.reply_to_message.message_id)
    meta = BRIDGE_REPLIES.get(key)
    if not meta:
        # Немає мосту – віддамо це universal_handler'у
        return

    bot: Bot = message.bot

    peer_id = meta["peer_id"]
    prefix_to_peer = meta["prefix_to_peer"]
    reply_prefix_back = meta["reply_prefix_back"]

    text_part = message.text or message.caption or ""

    try:
        sent_msg: Optional[Message] = None

        # спочатку текст з префіксом
        if text_part:
            sent_msg = await bot.send_message(peer_id, f"{prefix_to_peer}{text_part}")

        # якщо є медіа – докинути копією (фото, відео і т.д.)
        if message.photo or message.document or message.video:
            media_sent = await bot.copy_message(peer_id, message.chat.id, message.message_id)
            # якщо тексту не було — в якості "якоря" беремо медіа
            if sent_msg is None:
                sent_msg = media_sent

        # реєструємо дзеркальний міст, щоб відповіді з іншого боку теж ходили по колу
        if sent_msg:
            register_bridge_message(
                chat_id=sent_msg.chat.id,
                message_id=sent_msg.message_id,
                peer_id=message.chat.id,
                prefix_to_peer=reply_prefix_back,
                reply_prefix_back=prefix_to_peer,
            )

    except Exception as e:
        logger.exception("Помилка при пересиланні reply: %s", e)


# ================== УНІВЕРСАЛЬНИЙ ХЕНДЛЕР ==================
@router.message()
async def universal_handler(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    bot: Bot = message.bot
    action = PENDING_ACTION.get(user_id)

    # --- якщо немає активної дії: спроба редагувати меню або попередження про "просто чат" ---
    if not action:
        text = (message.text or "").strip()

        # редагування меню через "Страва: ... / Напій: ... / Десерт: ..."
        low = text.lower()
        updated = False

        if low.startswith("страва:"):
            value = text.split(":", 1)[1].strip()
            if value:
                user["menu_dish"] = value
                updated = True
                mark_user_active(user)
                await message.answer(f"Оновив твою страву 🍽️\nНове значення: {value}")
        elif low.startswith("напій:") or low.startswith("напиток:"):
            value = text.split(":", 1)[1].strip()
            if value:
                user["menu_drink"] = value
                updated = True
                mark_user_active(user)
                await message.answer(f"Оновив твій напій 🥂\nНове значення: {value}")
        elif low.startswith("десерт:"):
            value = text.split(":", 1)[1].strip()
            if value:
                user["menu_dessert"] = value
                updated = True
                mark_user_active(user)
                await message.answer(f"Оновив твій десерт 🍰\nНове значення: {value}")

        if updated:
            await save_data()
            return

        # інакше — пояснюємо, що це бачить тільки бот
        mark_user_active(user)
        await message.answer(
            "Я бачу це повідомлення тільки як бот 🙈\n\n"
            "Щоб написати організатору — натисни «❓ Допомога» → «✉ Звʼязатись з організатором Ніколасом».\n"
            "Щоб написати в грі «Таємний Миколайчик» — зайди в «🎅 Мій Миколайчик» і користуйся кнопками «✉ ...».\n\n"
            "Користуйся кнопками нижче 👇",
            reply_markup=main_menu_kb(user),
        )
        return

    # === далі йдуть стани, де action встановлений ===

    # --- Введення коду вечірки ---
    if action == "enter_party_code":
        PENDING_ACTION.pop(user_id, None)
        code = (message.text or "").strip().upper()
        current_code = (PARTY.get("code") or "").upper()

        if not PARTY.get("active") or not current_code:
            await message.answer(
                "Зараз немає активних вечірок. Запитай код у організатора, коли він створить нову 😊"
            )
            return

        if code != current_code:
            await message.answer(
                "Код не підходить 😔\n"
                "Перевір, будь ласка, чи все правильно, або уточни у організатора."
            )
            PENDING_ACTION[user_id] = "enter_party_code"
            return

        user["has_valid_code"] = True
        user["party_code"] = current_code
        await save_data()

        text = (
            "Вау! ✨\n\n"
            f"Тебе запросили на вечірку <b>«{PARTY_NAME}»</b>!\n\n"
            "Підтверди свою участь нижче — я додам тебе до списку гостей "
            "і допоможу підготуватись до свята 😉\n\n"
            "То ти з нами на вечірці?"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🎉 Так, я буду!", callback_data="party_yes"),
                ],
                [
                    InlineKeyboardButton(
                        text="🙈 Я просто дивлюсь", callback_data="party_no"
                    )
                ],
            ]
        )

        await message.answer(text, reply_markup=kb)
        await send_gif(message, START_GIF_ID)
        return

    # --- Моє меню (покроково з затримками) ---
    if action == "set_dish":
        PENDING_ACTION.pop(user_id, None)
        user["menu_dish"] = (message.text or "").strip()
        await message.answer("Записав твою страву 🍽️")
        await asyncio.sleep(0.5)
        await message.answer(
            "Тепер напиши, будь ласка, який <b>напій</b> ти плануєш принести "
            "(алкогольний або безалкогольний)."
        )
        PENDING_ACTION[user_id] = "set_drink"
        await save_data()
        return

    if action == "set_drink":
        PENDING_ACTION.pop(user_id, None)
        user["menu_drink"] = (message.text or "").strip()
        await message.answer("Супер! 🥂")
        await asyncio.sleep(0.5)
        await message.answer(
            "Тепер напиши, будь ласка, який <b>десерт</b> ти плануєш принести.\n"
            "Це може бути щось невелике і недороге, але круто, якщо хоч трохи "
            "пасує до твого кольору."
        )
        PENDING_ACTION[user_id] = "set_dessert"
        await save_data()
        return

        # --- Локальне редагування меню: тільки один пункт ---
    if action == "edit_dish":
        PENDING_ACTION.pop(user_id, None)
        user["menu_dish"] = (message.text or "").strip()
        await save_data()
        await message.answer(
            f"Оновив твою страву 🍽️\nНове значення: {user['menu_dish']}",
            reply_markup=main_menu_kb(user),
        )
        return

    if action == "edit_drink":
        PENDING_ACTION.pop(user_id, None)
        user["menu_drink"] = (message.text or "").strip()
        await save_data()
        await message.answer(
            f"Оновив твій напій 🥂\nНове значення: {user['menu_drink']}",
            reply_markup=main_menu_kb(user),
        )
        return

    if action == "edit_dessert":
        PENDING_ACTION.pop(user_id, None)
        user["menu_dessert"] = (message.text or "").strip()
        await save_data()
        await message.answer(
            f"Оновив твій десерт 🍰\nНове значення: {user['menu_dessert']}",
            reply_markup=main_menu_kb(user),
        )
        return

    if action == "set_dessert":
        PENDING_ACTION.pop(user_id, None)
        user["menu_dessert"] = (message.text or "").strip()
        await save_data()

        await message.answer(
            f"Готово! Я записав твоє меню:\n"
            f"• Страва: {user['menu_dish']}\n"
            f"• Напій: {user['menu_drink']}\n"
            f"• Десерт: {user['menu_dessert']}",
            reply_markup=main_menu_kb(user),
        )
        await send_gif(message, START_GIF_ID)
        await asyncio.sleep(0.5)
        await message.answer(
            "Памʼятай, що меню бажано має підходити під твій образ — "
            "хоча б по асоціаціях 😉"
        )

        # запускаємо ланцюжок «післяменюшних» повідомлень
        user["postmenu_followups_blocked"] = False
        asyncio.create_task(postmenu_followups(bot, user_id))
        return

    # --- Підтвердження завдання (текст + фото/відео) ---
    if action == "task_ask_org":
        PENDING_ACTION.pop(user_id, None)

        # текст або підпис до фото
        text_or_caption = (message.text or message.caption or "").strip()

        header = (
            f"📎 Коментар від гостя щодо завдання "
            f"({user.get('name') or user_id}, @{user.get('username') or '-'})\n\n"
        )

        sent_anchor: Optional[Message] = None

        try:
            # Спочатку відправляємо текст, якщо він є
            if text_or_caption:
                sent_anchor = await bot.send_message(
                    ADMIN_ID,
                    header + text_or_caption
                )

            # Якщо є медіа — докидаємо його окремо
            if message.photo or message.video or message.document:
                media_msg = await bot.copy_message(
                    ADMIN_ID,
                    message.chat.id,
                    message.message_id
                )
                # Якщо тексту не було — цей медіа-меседж стає "якорем"
                if sent_anchor is None:
                    sent_anchor = media_msg

            # Якщо щось відправили адмінові — реєструємо міст,
            # щоб організатор міг відповісти «reply» і гість це побачив
            if sent_anchor:
                register_bridge_message(
                    chat_id=sent_anchor.chat.id,  # ADMIN_ID
                    message_id=sent_anchor.message_id,
                    peer_id=user_id,
                    prefix_to_peer="Відповідь організатора щодо завдання: ",
                    reply_prefix_back="Гість відповів щодо завдання: ",
                )

        except Exception as e:
            logger.exception("Не зміг передати info по завданню організатору: %s", e)

        await message.answer(
            "Ок, я передав інформацію організатору.\n"
            "Якщо тебе попросять щось дослати — він відповість у цьому чаті 😉"
        )
        return

    # --- Santa wish ---
    if action == "set_santa_wish":
        PENDING_ACTION.pop(user_id, None)
        txt = (message.text or "").strip()
        if txt.lower() in ("сюрприз", "surprise"):
            user["santa_wish"] = None
        else:
            user["santa_wish"] = txt
        await message.answer(
            "Зберіг твої побажання для Таємного Миколайчика 🎅\n"
            "Коли організатор запустить гру, я скажу тобі, хто твій підопічний.",
            reply_markup=main_menu_kb(user),
        )
        await save_data()
        return

    # --- Santa messages ---
    if action in ("msg_child", "msg_santa"):
        PENDING_ACTION.pop(user_id, None)
        target_id = user.get("santa_child_id") if action == "msg_child" else user.get("santa_id")
        if not target_id:
            await message.answer("Схоже, зараз немає активного співрозмовника у грі 🤔")
            return

        if action == "msg_child":
            prefix_to_target = "Твій Таємний Миколайчик пише:\n\n"
            reply_prefix_back = "Твій підопічний відповів: "
        else:
            prefix_to_target = "Твій підопічний у грі «Таємний Миколайчик» пише:\n\n"
            reply_prefix_back = "Твій Таємний Миколайчик відповів: "

        try:
            sent = await bot.send_message(target_id, prefix_to_target + (message.text or ""))
            register_bridge_message(
                chat_id=target_id,
                message_id=sent.message_id,
                peer_id=user_id,
                prefix_to_peer=reply_prefix_back,
                reply_prefix_back=prefix_to_target,
            )
            await message.answer("Я передав твоє повідомлення ✉")
        except Exception as e:
            logger.exception("Не зміг доставити Santa-повідомлення %s → %s: %s", user_id, target_id, e)
            await message.answer("Не зміг доставити повідомлення 😔 Можливо, людина вийшла з гри або заблокувала бота.")
        return

    # --- Question to admin about Santa ---
    if action == "ask_santa_admin":
        PENDING_ACTION.pop(user_id, None)
        text = (message.text or "").strip()
        lower = text.lower()
        anonymous = "анонім" in lower

        if anonymous:
            header = "❓ Анонімне питання про Миколайчика:\n\n"
        else:
            header = (
                f"❓ Питання про Миколайчика від {user.get('name') or user_id} "
                f"(@{user.get('username') or '-'}):\n\n"
            )

        try:
            await bot.send_message(ADMIN_ID, header + text)
            await message.answer("Я передав твоє питання організатору 🎅")
        except Exception as e:
            logger.exception("Не зміг передати питання організатору: %s", e)
            await message.answer("Не зміг передати питання організатору 😔")
        return

    # --- Feedback collect (багато повідомлень, поки не натиснув fb_send) ---
    if action == "fb_collect":
        # НЕ попаємо action тут — він має жити, поки юзер не натисне "Відправити відгук"
        ctx = PENDING_CONTEXT.get(user_id)
        if not ctx:
            PENDING_CONTEXT[user_id] = {"fb_msgs": []}
            ctx = PENDING_CONTEXT[user_id]
        fb_list = ctx.setdefault("fb_msgs", [])
        fb_list.append((message.chat.id, message.message_id))
        await message.answer("Записав у відгук ✅\nКоли закінчиш — натисни «✅ Відправити відгук».")
        return

    # --- Contact organizer directly ---
    if action == "ask_org":
        PENDING_ACTION.pop(user_id, None)
        text = (message.text or "").strip()
        lower = text.lower()
        anonymous = "анонім" in lower

        if anonymous:
            header = "📞 Анонімне повідомлення для організатора:\n\n"
        else:
            header = (
                f"📞 Повідомлення для організатора від {user.get('name') or user_id} "
                f"(@{user.get('username') or '-'}):\n\n"
            )

        try:
            sent = await bot.send_message(ADMIN_ID, header + text)
            register_bridge_message(
                chat_id=ADMIN_ID,
                message_id=sent.message_id,
                peer_id=user_id,
                prefix_to_peer="Організатор відповів: ",
                reply_prefix_back="Гість відповів: ",
            )
            await message.answer(
                "Я передав твоє повідомлення організатору ✅",
                reply_markup=main_menu_kb(user),
            )
        except Exception as e:
            logger.exception("Не зміг передати повідомлення організатору: %s", e)
            await message.answer("Не зміг передати повідомлення організатору 😔")
        return

    # --- Admin: set budget ---
    if action == "admin_set_budget":
        PENDING_ACTION.pop(user_id, None)
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        SANTA.budget_text = (message.text or "").strip()
        await save_data()
        await message.answer(f"Оновив бюджет для Миколайчика: {SANTA.budget_text}")
        return

    # --- Admin: set santa description ---
    if action == "admin_set_santa_desc":
        PENDING_ACTION.pop(user_id, None)
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        SANTA.description = (message.text or "").strip()
        await save_data()
        await message.answer("Зберіг опис гри Таємного Миколайчика.")
        return

    # --- Admin: broadcast to all participants ---
    if action == "admin_broadcast":
        PENDING_ACTION.pop(user_id, None)
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        text = message.text or ""
        sent = 0
        for uid, data in USERS.items():
            if not data.get("participant"):
                continue
            try:
                await bot.send_message(uid, text)
                sent += 1
            except Exception as e:
                logger.exception("Не зміг надіслати broadcast користувачу %s: %s", uid, e)
        await message.answer(f"Розіслав оголошення {sent} учасникам 🎄")
        return

    # --- Admin: створити / оновити вечірку (wizard) ---
    if action == "admin_party_name":
        PENDING_ACTION.pop(user_id, None)
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        PARTY["name"] = (message.text or "").strip()
        apply_party_to_globals()
        await save_data()
        PENDING_ACTION[user_id] = "admin_party_location"
        await message.answer(
            "Супер! Тепер введи <b>локацію</b> (адресу) вечірки.\n"
            "Наприклад: «Київ, вул. Таємна 7»."
        )
        return

    if action == "admin_party_location":
        PENDING_ACTION.pop(user_id, None)
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        PARTY["location"] = (message.text or "").strip()
        apply_party_to_globals()
        await save_data()
        PENDING_ACTION[user_id] = "admin_party_dates"
        await message.answer(
            "Ок! Тепер введи текст про дату/час.\n"
            "Наприклад: «26 грудня, з 18:00 до відкриття метро» або «24–25 грудня, 19:00»."
        )
        return

    if action == "admin_party_dates":
        PENDING_ACTION.pop(user_id, None)
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        PARTY["dates_text"] = (message.text or "").strip()
        apply_party_to_globals()
        await save_data()
        PENDING_ACTION[user_id] = "admin_party_feedback_date"
        await message.answer(
            "Тепер введи дату, з якої просити відгук (у форматі YYYY-MM-DD), "
            "або '-' якщо не хочеш вмикати автоматичний день фідбеку."
        )
        return

    if action == "admin_party_feedback_date":
        PENDING_ACTION.pop(user_id, None)
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        txt_fb = (message.text or "").strip()
        if txt_fb == "-":
            PARTY["feedback_date"] = None
        else:
            PARTY["feedback_date"] = txt_fb

        PARTY["active"] = True
        PARTY["code"] = generate_party_code()
        await save_data()

        await message.answer(
            "Готово! Я оновив вечірку:\n\n"
            f"Назва: <b>{PARTY_NAME}</b>\n"
            f"Локація: {PARTY_LOCATION}\n"
            f"Дати: {PARTY_DATES_TEXT}\n"
            f"Дата старту відгуків: {PARTY.get('feedback_date') or 'не задана'}\n"
            f"Код для гостей: <code>{PARTY['code']}</code>\n\n"
            "Відправ цей код гостям. Без нього вони не зможуть зайти в бота 😉",
            reply_markup=admin_menu_kb(),
        )
        return

    # --- Admin: card to channel ---
    if action == "admin_card":
        PENDING_ACTION.pop(user_id, None)
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        preview = (
            "Ось превʼю листівки, яку можна відправити в канал:\n\n"
            f"{message.text}\n\n"
            "Натисни кнопку нижче, щоб опублікувати в канал."
        )
        PENDING_CONTEXT[user_id] = message.text
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Опублікувати в канал",
                        callback_data="admin_card_publish",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Скасувати", callback_data="admin_card_cancel"
                    )
                ],
            ]
        )
        await message.answer(preview, reply_markup=kb)
        return

    # fallback (на всякий випадок)
    mark_user_active(user)
    await message.answer(
        "Я бачу це повідомлення тільки як бот 🙈\n"
        "Користуйся кнопками нижче 👇",
        reply_markup=main_menu_kb(user),
    )


# ================== RUN BOT ==================
async def main():
    await load_data()
    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    logger.info("🎄 Бот «%s» запущений!", PARTY_NAME)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
