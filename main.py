import os
import asyncio
import random
import json
import logging
import string
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

# ================== ЛОГІНГ ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== ENV CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PARTY_CHANNEL_LINK = os.getenv("PARTY_CHANNEL_LINK")  # опціонально

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
    "active": False,        # чи є активна вечірка
    "name": PARTY_NAME,     # поточна назва
    "location": PARTY_LOCATION,
    "dates_text": PARTY_DATES_TEXT,
    "code": None,           # код вечірки
}


def apply_party_to_globals():
    """
    Підтягуємо назву/адресу/дати з PARTY в глобальні змінні,
    щоб решта коду могла й далі використовувати PARTY_NAME і т.д.
    """
    global PARTY_NAME, PARTY_LOCATION, PARTY_DATES_TEXT
    if PARTY.get("name"):
        PARTY_NAME = PARTY["name"]
    if PARTY.get("location"):
        PARTY_LOCATION = PARTY["location"]
    if PARTY.get("dates_text"):
        PARTY_DATES_TEXT = PARTY["dates_text"]


def generate_party_code(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))

def party_rules_text() -> str:
    return (
    "📜 <b>Правила вечірки «{PARTY_NAME}»</b>\n\n"
    "1. У кожного гостя є свій персональний <b>колір-образ</b>. "
    "Це має бути <b>моно-образ</b> — весь твій лук в одному кольорі.\n\n"
    "2. Разом з кольором ти отримаєш <b>роль</b> і <b>таємне міні-завдання</b>. "
    "Роль можна озвучувати, завдання — під спойлером 😉\n\n"
    "3. Гра «Таємний Миколайчик» — обов’язкова частина вечірки.\n\n"
    "4. Кожен гість приносить <b>страву</b> і <b>напій</b>. "
    "Бажано, щоб страва максимально пасувала до твого образу.\n\n"
    "5. Поганий настрій, токсичність і «я тут постою в куточку» — не наш формат. "
    "Приходимо за атмосферою, сміхом і теплом 🥰\n\n"
    "Якщо тобі все підходить — підтверджуй участь нижче 👇"
)

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

color_lock = asyncio.Lock()

# ================== КОЛЬОРИ ==================
COLORS = [
    {
        "id": 1,
        "emoji": "❤️",
        "name": "Насичений червоний",
        "role": "Санта-Клаус у відпустці",
        "tasks": [
            "Хоч раз за вечір зʼявитися в кімнаті з фразою «Ну що, хто тут добре поводився?»",
            "Організувати хоча б один загальний тост «за Різдво» або «за дива».",
            "Підкинути комусь маленький символічний подарунок або смаколик, нічого не пояснюючи 😉",
        ],
        "taken_by": None,
    },
    {
        "id": 2,
        "emoji": "🌲",
        "name": "Лісовий зелений",
        "role": "Дух Різдвяної Ялинки",
        "tasks": [
            "Зібрати мінімум трьох людей на фото «як ялинка і іграшки».",
            "Попросити когось «прикрасити» тебе чимось додатковим (шарф, дощик, шпилька).",
            "Хоч раз сказати комусь: «Ти сьогодні як прикраса на моїй ялинці» 🎄",
        ],
        "taken_by": None,
    },
    {
        "id": 3,
        "emoji": "🎗️",
        "name": "Золотий",
        "role": "Золота Зірка з вертепу",
        "tasks": [
            "Тричі за вечір відмітити вголос чийсь крутий образ або деталь.",
            "Організувати момент, коли всі піднімуть очі догори — «знайти зірку» в кімнаті.",
            "Придумати й озвучити хоча б одну «золоту» комплімент-метафору комусь.",
        ],
        "taken_by": None,
    },
    {
        "id": 4,
        "emoji": "🩶",
        "name": "Срібний",
        "role": "Снігова Королева/Король",
        "tasks": [
            "Хоч раз зробити драматичний повільний вхід у кімнату, ніби ти головний персонаж балу.",
            "Зробити «королівське фото» з мінімум двома «підданими» по боках.",
            "Сказати хоча б двом людям щось холодно-ввічливе, а потім «розтопити лід» жартом.",
        ],
        "taken_by": None,
    },
    {
        "id": 5,
        "emoji": "🤍",
        "name": "Білий",
        "role": "Сніговик, що ожив",
        "tasks": [
            "Попросити когось «заліпити» тобі уявні вуглинки-очі та морквинку-ніс.",
            "Організувати фото, де всі зображують сніговиків ☃️.",
            "Хоч раз зробити вигляд, що «танеш» від чиєїсь уваги або обіймів.",
        ],
        "taken_by": None,
    },
    {
        "id": 6,
        "emoji": "🫐",
        "name": "Глибокий синій",
        "role": "Вартовик Північного Сяйва",
        "tasks": [
            "Хоч раз запропонувати вийти комусь «подивитись на уявне північне сяйво».",
            "Розповісти мінімум одну історію чи байку, повʼязану з нічним небом або зорями.",
            "Зробити фото, де всі дивляться в один бік, ніби спостерігають за сяйвом.",
        ],
        "taken_by": None,
    },
    {
        "id": 7,
        "emoji": "🎀",
        "name": "Ніжно-рожевий",
        "role": "Фея Цукрової Вати",
        "tasks": [
            "Поширити мінімум три «солодкі» компліменти різним людям.",
            "Провести маленький обряд «посипання» когось уявною цукровою пудрою від поганого настрою.",
            "Запропонувати комусь обмінятися «солодкими історіями» з дитинства.",
        ],
        "taken_by": None,
    },
    {
        "id": 8,
        "emoji": "🟫",
        "name": "Бордово-сливовий",
        "role": "Майстер Глінтвейну",
        "tasks": [
            "Зібрати невелику компанію та обговорити «ідеальний рецепт глінтвейну».",
            "Поставити мінімум трьом людям запитання: «Чим ти грієшся взимку, окрім чаю?»",
            "Зробити фото, де всі тримають чашки/склянки, ніби ви таємне товариство глінтвейну.",
        ],
        "taken_by": None,
    },
    {
        "id": 9,
        "emoji": "🥂",
        "name": "Шампань / кремово-золотий",
        "role": "Новий Рік, що приходить",
        "tasks": [
            "Оголосити хоча б один «міні-новий рік» протягом вечора з відліком від 5 до 1.",
            "Запропонувати комусь придумати коротке побажання «на наступний рік життя».",
            "Організувати «красивий дзвін келихів» та зафіксувати цей момент.",
        ],
        "taken_by": None,
    },
    {
        "id": 10,
        "emoji": "⚫",
        "name": "Чорний з блискітками",
        "role": "Чарівник Чорної Магії Свят",
        "tasks": [
            "Показати комусь маленький «фокус» (навіть якщо це просто прикол або гра слів).",
            "Хоч раз шепнути комусь: «Я знаю одну святкову таємницю про тебе» (можна вигадану 😉).",
            "Організувати фото, де всі роблять «таємничі обличчя».",
        ],
        "taken_by": None,
    },
    {
        "id": 11,
        "emoji": "🟪",
        "name": "Темно-фіолетовий",
        "role": "Різдвяний Чарівник / Лускунчик",
        "tasks": [
            "Розповісти хоча б одну напівсерйозну «легенду» про Різдво або диво.",
            "Зробити тост «за магію моменту».",
            "Знайти людину, яка ще не в настрої свята, і спробувати її «зачарувати» на краще.",
        ],
        "taken_by": None,
    },
    {
        "id": 12,
        "emoji": "🩵",
        "name": "Мʼятний / ніжно-бірюзовий",
        "role": "Крижана Принцеса",
        "tasks": [
            "Хоч раз пожартувати про те, що ти «тут для естетики та краси кадру».",
            "Попросити когось допомогти тобі зробити «ідеальне крижане селфі».",
            "Сказати мінімум двом людям, за що вони сьогодні «сяють».",
        ],
        "taken_by": None,
    },
    {
        "id": 13,
        "emoji": "🤎",
        "name": "Бронзовий / мідний",
        "role": "Гламурний олень Рудольф",
        "tasks": [
            "Хоч раз піджартувати, що ти «сьогодні на підробітку, тягнеш санчата настрою».",
            "Зробити фото з кимось, хто у червоному, ніби це твій Санта.",
            "Запропонувати комусь уявний «покатати на санчатах» і обговорити, що б ти їм віз як подарунок.",
        ],
        "taken_by": None,
    },
    {
        "id": 14,
        "emoji": "🐚",
        "name": "Пудрово-бежевий",
        "role": "Домашній Дух Різдва в кашемірі",
        "tasks": [
            "Перевірити, чи всім комфортно: тричі поцікавитись, чи нікому нічого не бракує.",
            "Зробити один момент «домашнього затишку» — посадити людей ближче, дати плед або чай.",
            "Розповісти коротку історію або спогад, повʼязаний з домашнім Різдвом.",
        ],
        "taken_by": None,
    },
]

# GIF для кожного кольору (ти їх потім заповниш в env як COLOR_1_GIF_ID, COLOR_2_GIF_ID ...)
COLOR_GIFS: Dict[int, Optional[str]] = {
    c["id"]: os.getenv(f"COLOR_{c['id']}_GIF_ID") for c in COLORS
}

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
        "task_index": None,
        "santa_joined": False,
        "santa_wish": None,
        "santa_child_id": None,
        "santa_id": None,
        "santa_gift_ready": False,
        "dish": None,
        "drink": None,
        "name": None,
        "username": None,
        "has_valid_code": False,
        "party_code": None,
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
        "COLORS_taken": {str(c["id"]): c["taken_by"] for c in COLORS},
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

        taken = raw.get("COLORS_taken", {})
        for c in COLORS:
            c["taken_by"] = taken.get(str(c["id"]))

        # PARTY
        party_raw = raw.get("PARTY")
        if party_raw:
            PARTY.update(party_raw)
            # підтягнути назву/адресу/дати з файлу в глобальні константи
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
    return USERS[uid]


def get_color_by_id(cid: int) -> Optional[Dict[str, Any]]:
    for c in COLORS:
        if c["id"] == cid:
            return c
    return None


def get_available_colors():
    return [c for c in COLORS if c["taken_by"] is None]


# ================== КЛАВІАТУРИ ==================
def main_menu_kb(user: Dict[str, Any]) -> ReplyKeyboardMarkup:
    buttons = []

    if user.get("participant"):
        buttons.append([KeyboardButton(text="🎨 Мій образ")])
        buttons.append([KeyboardButton(text="🎅 Мій Миколайчик")])
        buttons.append(
            [
                KeyboardButton(text="📜 Гості та меню"),
                KeyboardButton(text="ℹ️ Про вечірку"),
            ]
        )
    else:
        buttons.append([KeyboardButton(text="ℹ️ Про вечірку")])

    if PARTY_CHANNEL_LINK:
        buttons.append([KeyboardButton(text="📢 Канал вечірки")])

    buttons.append([KeyboardButton(text="📞 Звʼязатись з організатором")])
    buttons.append([KeyboardButton(text="⭐ Фідбек / питання")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def colors_inline_kb() -> InlineKeyboardMarkup:
    available = get_available_colors()
    if not available:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎨 Усі кольори вже зайняті. Напиши організатору.",
                        callback_data="noop",
                    )
                ]
            ]
        )

    rows = []
    row = []
    for c in available:
        # Колір - Назва + роль в одному рядку
        text = f"{c['emoji']} {c['name']} — {c['role']}"
        row.append(InlineKeyboardButton(text=text, callback_data=f"color:{c['id']}"))
        if len(row) == 1:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            [InlineKeyboardButton(text="🎨 Кольори/ролі", callback_data="admin_colors")],
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


# ================== ХЕНДЛЕРИ КОРИСТУВАЧІВ ==================
@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    user["name"] = message.from_user.full_name
    user["username"] = message.from_user.username

    # скидаємо будь-який "завислий" стан
    PENDING_ACTION.pop(user_id, None)

    # якщо немає активної вечірки — нікого не пускаємо
    if not PARTY.get("active") or not PARTY.get("code"):
        await message.answer(
            "Зараз для тебе немає активних вечірок 😌\n\n"
            "Як тільки організатор створить нову тусу і дасть код — ти зможеш зайти сюди знову."
        )
        return

    # якщо юзер вже учасник цієї вечірки
    if (
        user.get("participant")
        and user.get("color_id")
        and user.get("party_code") == PARTY["code"]
        and user.get("has_valid_code")
    ):
        await message.answer(
            "Радий бачити тебе знову 🎄\nТи вже в списку гостей. Ось твоє меню 👇",
            reply_markup=main_menu_kb(user),
        )
        await send_gif(message, START_GIF_ID)
        return

    # якщо код ще не вводив або він від іншої (старої) вечірки — просимо код
    if not user.get("has_valid_code") or user.get("party_code") != PARTY["code"]:
        await message.answer(
            "Щоб зайти на вечірку, введи, будь ласка, <b>код вечірки</b>, який дав тобі організатор."
        )
        PENDING_ACTION[user_id] = "enter_party_code"
        return

    # код правильний і актуальний, але людина ще не підтвердила участь
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
    await callback.message.edit_text(
        "Чудово! Тоді обираємо твій персональний образ 😊\n\n"
        "Пам’ятай: колір бажано нікому не показувати і не розголошувати — "
        "нехай усі дивуються вже на вечірці 😉\n"
        "Повторюватись кольори не можуть — кожен унікальний і тільки один раз!\n\n"
        "Ознайомся з описами нижче та обери той, який тобі ближче до душі 🎨",
        reply_markup=colors_inline_kb(),
    )
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


@router.callback_query(F.data.startswith("color:"))
async def cb_choose_color(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("participant"):
        await callback.answer(
            "Спочатку підтверди, що ти будеш на вечірці 😉", show_alert=True
        )
        return

    async with color_lock:
        color_id = int(callback.data.split(":")[1])
        color = get_color_by_id(color_id)
        if not color:
            await callback.answer(
                "Щось пішло не так з цим кольором 🤔", show_alert=True
            )
            return

        if color["taken_by"] and color["taken_by"] != callback.from_user.id:
            await callback.answer(
                "Цей колір уже зайнятий, обери інший 🙈", show_alert=True
            )
            return

        # звільняємо старий колір, якщо був
        if user.get("color_id"):
            old = get_color_by_id(user["color_id"])
            if old and old["taken_by"] == callback.from_user.id:
                old["taken_by"] = None

        color["taken_by"] = callback.from_user.id
        user["color_id"] = color_id

        # вибираємо випадкове завдання
        if color["tasks"]:
            user["task_index"] = random.randint(0, len(color["tasks"]) - 1)
        else:
            user["task_index"] = None

        await save_data()
        logger.info(
            "Користувач %s обрав колір %s (%s)",
            user.get("name") or callback.from_user.id,
            color["emoji"],
            color["name"],
        )

    task_text = (
        color["tasks"][user["task_index"]]
        if user["task_index"] is not None
        else "Завдання ще не задано."
    )
    spoiler_text = f"Колір: {color['emoji']} {color['name']}\nРоль: {color['role']}\nЗавдання: {task_text}"
    spoiler_html = f'<span class="tg-spoiler">{spoiler_text}</span>'

    await send_gif(callback.message, COLOR_GIFS.get(color_id))

    text = (
        f"{color['emoji']} Твій образ затверджено!\n\n"
        f"Твоя роль: <b>{color['role']}</b>\n\n"
        "Твій колір, роль і мінізавдання сховані під спойлером нижче. "
        "Натисни на затемнений текст, щоб відкрити його "
        "(інші побачать тільки якщо ти покажеш екран):\n\n"
        f"{spoiler_html}\n\n"
        "Памʼятай: краще не розголошувати свій колір до вечірки — "
        "так буде більше вау-ефекту 😉\n\n"
        "Далі я попрошу тебе додати страву і напій, а потім — залетіти в гру «Таємний Миколайчик» 🎅"
    )

    await callback.message.edit_text(text)
    await callback.message.answer(
        "Ось твоє меню учасника 🎄", reply_markup=main_menu_kb(user)
    )


@router.message(F.text == "ℹ️ Про вечірку")
async def about_party(message: Message):
    loc_html = f'<span class="tg-spoiler">{PARTY_LOCATION}</span>'
    text = (
        f"🎄 <b>{PARTY_NAME}</b>\n"
        f"📍 {loc_html}\n"
        f"🗓 {PARTY_DATES_TEXT}\n\n"
        f"{party_rules_text()}"
    )
    await message.answer(text)


@router.message(F.text == "📢 Канал вечірки")
async def party_channel(message: Message):
    if PARTY_CHANNEL_LINK:
        await message.answer(
            "Ось канал вечірки. Там будуть оголошення, листівки та новини ✨\n"
            f"{PARTY_CHANNEL_LINK}"
        )
    else:
        await message.answer(
            "Організатор ще не додав посилання на канал вечірки 🤔"
        )


@router.message(F.text == "🎨 Мій образ")
async def my_look(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("participant"):
        await message.answer("Спочатку підтвердь участь у вечірці — напиши /start 🎄")
        return

    if not user.get("color_id"):
        await message.answer(
            "Ти ще не обрав свій образ. Почни з вибору кольору через /start 🎨"
        )
        return

    color = get_color_by_id(user["color_id"])
    if not color:
        await message.answer("Не можу знайти твій колір, напиши організатору.")
        return

    if user.get("task_index") is not None and color["tasks"]:
        try:
            task_text = color["tasks"][user["task_index"]]
        except IndexError:
            task_text = "Завдання ще не задано."
    else:
        task_text = "Завдання ще не задано."

    dish_txt = user.get("dish") or "ще не вказана"
    drink_txt = user.get("drink") or "ще не вказаний"

    spoiler_plain = (
        f"Колір: {color['emoji']} {color['name']}\n"
        f"Роль: {color['role']}\n"
        f"Завдання: {task_text}\n\n"
        f"Страва: {dish_txt}\n"
        f"Напій: {drink_txt}"
    )
    spoiler_html = f'<span class="tg-spoiler">{spoiler_plain}</span>'

    text = (
        "Ось вся інформація по твоєму образу на вечірку:\n\n"
        f"{spoiler_html}\n\n"
        "Якщо хочеш змінити страву/напій — натисни «⭐ Фідбек / питання» і напиши організатору "
        "або просто ще раз обери «🍽 Моя страва і напій» (якщо додамо цю кнопку окремо 😉)."
    )
    await message.answer(text)


@router.message(F.text == "📜 Гості та меню")
async def guests_menu_for_user(message: Message):
    lines = ["📜 <b>Гості та меню</b>"]
    has_any = False

    for uid, data in USERS.items():
        if not data.get("participant"):
            continue
        has_any = True

        name = data.get("name") or f"Гість {uid}"
        if data.get("color_id"):
            c = get_color_by_id(data["color_id"])
            color_txt = f"{c['emoji']} {c['name']}" if c else "-"
            role_txt = c["role"] if c else "-"
        else:
            color_txt = "-"
            role_txt = "-"

        dish_txt = data.get("dish") or "—"
        drink_txt = data.get("drink") or "—"
        santa_txt = "✅" if data.get("santa_joined") else "❌"

        lines.append(
            f"• <b>{name}</b>\n"
            f"  Образ: {color_txt}\n"
            f"  Роль: {role_txt}\n"
            f"  Страва: {dish_txt}\n"
            f"  Напій: {drink_txt}\n"
            f"  У грі Миколайчика: {santa_txt}\n"
        )

    if not has_any:
        lines.append("Поки ще ніхто не додав свої дані 🤔")

    await message.answer("\n".join(lines))


@router.message(F.text == "🎅 Мій Миколайчик")
async def my_santa(message: Message):
    user = get_user(message.from_user.id)

    if not user.get("participant"):
        await message.answer("Спочатку підтвердь, що ти будеш на вечірці — натисни /start 🎄")
        return

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


@router.message(F.text == "⭐ Фідбек / питання")
async def feedback_menu(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Загальний фідбек", callback_data="fb_general")],
            [
                InlineKeyboardButton(
                    text="❓ Питання про Миколайчика",
                    callback_data="fb_santa_question",
                )
            ],
        ]
    )
    await message.answer(
        "Тут ти можеш залишити загальний фідбек або поставити питання про гру «Таємний Миколайчик».",
        reply_markup=kb,
    )


@router.message(F.text == "📞 Звʼязатись з організатором")
async def contact_organizer(message: Message):
    text = (
        "📞 <b>Звʼязок з організатором</b>\n\n"
        "Найчастіші питання:\n"
        "• Не можу обрати/змінити колір — напиши, який хочеш, і ми все вручну поправимо.\n"
        "• Хочу змінити страву/напій — просто напиши новий варіант.\n"
        "• Передумав(ла) йти / не впевнений(а) — напиши, і ми спокійно все переробимо.\n"
        "• Є інше питання — теж пишеш сюди 😌\n\n"
        "Натисни кнопку нижче, щоб відправити повідомлення організатору."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉ Написати організатору", callback_data="ask_org"
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

    if user.get("color_id"):
        col = get_color_by_id(user["color_id"])
        if col and col["taken_by"] == user_id:
            col["taken_by"] = None

    user.update(_base_user_template())
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
    PENDING_ACTION[callback.from_user.id] = "msg_santa"
    await callback.message.answer(
        "Напиши повідомлення, яке я анонімно перешлю твоєму Миколайчику 👇\n\n"
        "Щоб відповісти ще раз — знову обери в меню «✉ Написати моєму Миколайчику»."
    )


@router.callback_query(F.data == "ask_santa_admin")
async def cb_ask_santa_admin(callback: CallbackQuery):
    PENDING_ACTION[callback.from_user.id] = "ask_santa_admin"
    await callback.message.answer(
        "Напиши своє питання про Таємного Миколайчика.\n"
        "Я перешлю його організатору. Можеш додати «анонімно» у текст."
    )


@router.callback_query(F.data == "fb_general")
async def cb_fb_general(callback: CallbackQuery):
    PENDING_ACTION[callback.from_user.id] = "fb_general"
    await callback.message.answer(
        "Напиши, будь ласка, свій фідбек про вечірку / підготовку / бота. "
        "Можеш вказати, чи хочеш залишитись анонімним."
    )


@router.callback_query(F.data == "fb_santa_question")
async def cb_fb_santa_question(callback: CallbackQuery):
    PENDING_ACTION[callback.from_user.id] = "ask_santa_admin"
    await callback.message.answer(
        "Напиши своє питання про Таємного Миколайчика. "
        "Якщо хочеш анонімно — просто додай «анонімно» у текст."
    )


@router.callback_query(F.data == "ask_org")
async def cb_ask_org(callback: CallbackQuery):
    PENDING_ACTION[callback.from_user.id] = "ask_org"
    await callback.message.answer(
        "Напиши своє повідомлення організатору. "
        "Якщо хочеш анонімно — додай слово «анонімно» у текст."
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


# ================== АДМІН ==================
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Ти не виглядаєш як організатор цієї тусовки 😏")
        return
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
        if data.get("color_id"):
            c = get_color_by_id(data["color_id"])
            color_txt = f"{c['emoji']} {c['name']}" if c else "-"
            role_txt = c["role"] if c else "-"
        else:
            color_txt = "-"
            role_txt = "-"

        dish_txt = data.get("dish") or "—"
        drink_txt = data.get("drink") or "—"
        santa_txt = "✅" if data.get("santa_joined") else "❌"
        gift_txt = "🎁" if data.get("santa_gift_ready") else "—"

        lines.append(
            f"• <b>{name}</b>\n"
            f"  Колір: {color_txt}\n"
            f"  Роль: {role_txt}\n"
            f"  Страва: {dish_txt}\n"
            f"  Напій: {drink_txt}\n"
            f"  Santa: {santa_txt} | Подарунок: {gift_txt}\n"
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

@router.callback_query(F.data == "admin_colors")
async def admin_colors(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return

    lines = ["🎨 <b>Кольори і ролі</b>"]
    for c in COLORS:
        if c["taken_by"]:
            u = USERS.get(c["taken_by"])
            owner = u["name"] if u and u.get("name") else f"id {c['taken_by']}"
        else:
            owner = "вільний"
        lines.append(
            f"{c['emoji']} <b>{c['name']}</b> — роль: {c['role']} | {owner}"
        )

    await callback.message.edit_text("\n".join(lines), reply_markup=admin_menu_kb())


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
        except Exception:
            pass

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
    except Exception:
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
    if uid in PENDING_ACTION:
        PENDING_ACTION.pop(uid, None)
        await message.answer(
            "Скасовано ✅ Можеш користуватись меню нижче.", reply_markup=main_menu_kb(get_user(uid))
        )
    else:
        await message.answer("Нічого скасовувати 😉", reply_markup=main_menu_kb(get_user(uid)))


# ================== УНІВЕРСАЛЬНИЙ ХЕНДЛЕР ==================
@router.message()
async def universal_handler(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    bot: Bot = message.bot
    action = PENDING_ACTION.pop(user_id, None)

    if not action:
        await message.answer(
            "Я тебе почув 👀 Користуйся кнопками нижче:",
            reply_markup=main_menu_kb(user),
        )
        return

        # --- Введення коду вечірки ---
    if action == "enter_party_code":
        code = message.text.strip().upper()
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

        # код вірний
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

    # --- Страва ---
    if action == "set_dish":
        user["dish"] = message.text.strip()
        await message.answer(
            "Записав твою страву 🍽️\n"
            "Тепер напиши, будь ласка, який <b>напій</b> ти плануєш принести "
            "(алкогольний або безалкогольний)."
        )
        PENDING_ACTION[user_id] = "set_drink"
        await save_data()
        return

    if action == "set_drink":
        user["drink"] = message.text.strip()
        await message.answer(
            f"Супер! Я записав:\n"
            f"• Страва: {user['dish']}\n"
            f"• Напій: {user['drink']}\n\n"
            "Памʼятай, що страва бажано має підходити під твій колір образу 😉",
            reply_markup=main_menu_kb(user),
        )
        await save_data()
        return

    # --- Santa wish ---
    if action == "set_santa_wish":
        txt = message.text.strip()
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
        target_id = user.get("santa_child_id") if action == "msg_child" else user.get("santa_id")
        if not target_id:
            await message.answer("Схоже, зараз немає активного співрозмовника у грі 🤔")
            return
        prefix = (
            "✉ Тобі повідомлення від твого Таємного Миколайчика:\n\n"
            if action == "msg_child"
            else "✉ Тобі повідомлення від твого підопічного у грі «Таємний Миколайчик»:\n\n"
        )
        try:
            await bot.send_message(target_id, prefix + message.text)
            await message.answer("Я передав твоє повідомлення ✉")
        except Exception:
            await message.answer("Не зміг доставити повідомлення 😔")
        return

    # --- Question to admin about Santa ---
    if action == "ask_santa_admin":
        text = message.text.strip()
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
        except Exception:
            await message.answer("Не зміг передати питання організатору 😔")
        return

    # --- General feedback ---
    if action == "fb_general":
        text = message.text.strip()
        lower = text.lower()
        anonymous = "анонім" in lower

        if anonymous:
            header = "⭐ Анонімний фідбек:\n\n"
        else:
            header = (
                f"⭐ Фідбек від {user.get('name') or user_id} "
                f"(@{user.get('username') or '-'}):\n\n"
            )

        try:
            await bot.send_message(ADMIN_ID, header + text)
            await message.answer("Дякую за фідбек! Я передав його організатору 🫶")
        except Exception:
            await message.answer("Не зміг передати фідбек організатору 😔")
        return

    # --- Contact organizer directly ---
    if action == "ask_org":
        text = message.text.strip()
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
            await bot.send_message(ADMIN_ID, header + text)
            await message.answer(
                "Я передав твоє повідомлення організатору ✅",
                reply_markup=main_menu_kb(user),
            )
        except Exception:
            await message.answer("Не зміг передати повідомлення організатору 😔")
        return

    # --- Admin: set budget ---
    if action == "admin_set_budget":
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        SANTA.budget_text = message.text.strip()
        await save_data()
        await message.answer(f"Оновив бюджет для Миколайчика: {SANTA.budget_text}")
        return

    # --- Admin: set santa description ---
    if action == "admin_set_santa_desc":
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        SANTA.description = message.text.strip()
        await save_data()
        await message.answer("Зберіг опис гри Таємного Миколайчика.")
        return

    # --- Admin: broadcast to all participants ---
    if action == "admin_broadcast":
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        text = message.text
        sent = 0
        for uid, data in USERS.items():
            if not data.get("participant"):
                continue
            try:
                await bot.send_message(uid, text)
                sent += 1
            except Exception:
                pass
        await message.answer(f"Розіслав оголошення {sent} учасникам 🎄")
        return

        # --- Admin: створити / оновити вечірку (wizard) ---
    if action == "admin_party_name":
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        PARTY["name"] = message.text.strip()
        apply_party_to_globals()
        await save_data()
        PENDING_ACTION[user_id] = "admin_party_location"
        await message.answer(
            "Супер! Тепер введи <b>локацію</b> (адресу) вечірки.\n"
            "Наприклад: «Київ, вул. Таємна 7»."
        )
        return

    if action == "admin_party_location":
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        PARTY["location"] = message.text.strip()
        apply_party_to_globals()
        await save_data()
        PENDING_ACTION[user_id] = "admin_party_dates"
        await message.answer(
            "Ок! Тепер введи текст про дату/час.\n"
            "Наприклад: «26 грудня, з 18:00 до відкриття метро» або «24–25 грудня, 19:00»."
        )
        return

    if action == "admin_party_dates":
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        PARTY["dates_text"] = message.text.strip()
        apply_party_to_globals()
        PARTY["active"] = True
        PARTY["code"] = generate_party_code()
        await save_data()

        await message.answer(
            "Готово! Я оновив вечірку:\n\n"
            f"Назва: <b>{PARTY_NAME}</b>\n"
            f"Локація: {PARTY_LOCATION}\n"
            f"Дати: {PARTY_DATES_TEXT}\n"
            f"Код для гостей: <code>{PARTY['code']}</code>\n\n"
            "Відправ цей код гостям. Без нього вони не зможуть зайти в бота 😉",
            reply_markup=admin_menu_kb(),
        )
        return

    # --- Admin: card to channel ---
    if action == "admin_card":
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

    # fallback
    await message.answer(
        "Я тебе почув 👀 Користуйся кнопками нижче:",
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
