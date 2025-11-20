import os
import asyncio
import random
from typing import Dict, Optional, Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode

# ====== ENV CONFIG ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PARTY_CHAT_LINK = os.getenv("PARTY_CHAT_LINK")  # link to group/chat
PARTY_CHANNEL_ID = os.getenv("PARTY_CHANNEL_ID")  # channel username like @christmas_spectrum or numeric id

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не заданий в змінних середовища")

PARTY_NAME = "Різдвяний Спектр"
PARTY_LOCATION = "селище Бабинці"
PARTY_DATES_TEXT = "24–25 грудня 2025 року"

PARTY_RULES = (
    "📜 <b>Правила вечірки «Різдвяний Спектр»</b>\\n\\n"
    "1. У кожного гостя є свій персональний <b>колір-образ</b>. "
    "Це може бути одяг, аксесуар або хоча б один помітний елемент у своєму кольорі.\\n"
    "2. Разом з кольором ти отримуєш <b>роль</b> і <b>таємне мінізавдання</b>. "
    "Роль можна озвучувати й показувати, а завдання — під спойлером, щоб ніхто не бачив одразу 😉\\n"
    "3. Гра «Таємний Миколайчик» — це обовʼязкова частина вечірки. "
    "Якщо ти в ній, значить ти точно будеш на святі. Якщо виходиш із гри — вважається, що не приходиш.\\n"
    "4. Кожен гість приносить <b>страву</b> і <b>напій</b>. Бажано, щоб страва була у кольорі твого образу.\\n"
    "5. Поганий настрій, токсичність і «я тут постою» — не наш формат. Приходимо за атмосферою, сміхом і теплом 🥰\\n"
)

SANTA_BASE_RULES = (
    "🎅 <b>Таємний Миколайчик</b>\\n\\n"
    "• Кожен учасник таємно дарує подарунок іншому гостю.\\n"
    "• Ти можеш написати свої побажання — що хотів/ла б отримати або чого точно не треба дарувати, "
    "або обрати варіант «Сюрприз».\\n"
    "• Після запуску гри бот скаже, хто твій підопічний, але <b>ніхто</b> не дізнається, кому даруєш саме ти.\\n"
    "• Можна анонімно переписуватись зі своїм підопічним і зі своїм Миколайчиком через бота.\\n"
    "• Головне — увага і настрій, а не сума подарунка 🫶\\n"
)

router = Router()

# ====== IN-MEMORY STATE (для однієї вечірки цього достатньо) ======
class SantaConfig:
    def __init__(self) -> None:
        self.registration_open: bool = False
        self.started: bool = False
        self.budget_text: Optional[str] = None
        self.description: Optional[str] = None

SANTA = SantaConfig()

# user_id -> дані
USERS: Dict[int, Dict[str, Any]] = {}

# pending actions: user_id -> string key
PENDING_ACTION: Dict[int, str] = {}

# Santa & admin special pending context if треба
PENDING_CONTEXT: Dict[int, Any] = {}

# Кольори / ролі / завдання (можна буде редагувати в коді)
COLORS = [
    {
        "id": 1,
        "emoji": "🔴",
        "name": "Червоний",
        "role": "Вогняний Хайп-мейкер",
        "tasks": [
            "Хоча б тричі за вечір підбурити людей до тосту або чірсу.",
            "Додати «вогню» в ніякові паузи — коротким жартом або історією.",
            "Зробити так, щоб хоч один танець почався саме після твоєї фрази 😉",
        ],
        "taken_by": None,
    },
    {
        "id": 2,
        "emoji": "🟢",
        "name": "Зелений",
        "role": "Ялинковий Декоратор",
        "tasks": [
            "Переконати мінімум трьох людей зробити з тобою фото біля чогось зеленого.",
            "Запропонувати хоча б одному гостю «задекорувати» його образ чимось тимчасовим.",
            "Хоч раз за вечір сказати комусь: «Ти сьогодні як новорічна ялинка» 🎄",
        ],
        "taken_by": None,
    },
    {
        "id": 3,
        "emoji": "🔵",
        "name": "Синій",
        "role": "Сніговий Chill-майстер",
        "tasks": [
            "Коли хтось каже «холодно» — видати сніговий або зимовий жарт.",
            "Хоч раз за вечір запропонувати комусь «заморозити» момент на фото.",
            "Зробити хоча б одне фото, де всі зображують сніговиків ☃️",
        ],
        "taken_by": None,
    },
    {
        "id": 4,
        "emoji": "🟡",
        "name": "Жовтий",
        "role": "Сонце Тусовки",
        "tasks": [
            "Тричі врятувати ніякову паузу жартом або історією.",
            "Похвалити мінімум трьох людей за їх образи.",
            "Поширювати «сонячні» компліменти протягом вечора.",
        ],
        "taken_by": None,
    },
    {
        "id": 5,
        "emoji": "🟣",
        "name": "Фіолетовий",
        "role": "Маг Таємних Подарунків",
        "tasks": [
            "Підкинути комусь маленьку несподіванку: записку, стікер чи комплімент.",
            "Хоч раз за вечір організувати міні-обмін дрібницями між двома людьми.",
            "Зробити так, щоб хтось сказав «нічого собі, не очікував(ла)!»",
        ],
        "taken_by": None,
    },
    {
        "id": 6,
        "emoji": "🧡",
        "name": "Помаранчевий",
        "role": "Мандариновий Контрабандист",
        "tasks": [
            "Щонайменше тричі згадати мандарини/апельсини у розмові.",
            "Організувати момент, коли кілька людей одночасно щось їдять/п’ють помаранчевого кольору.",
            "Подарувати комусь маленьку «вітамінку настрою» 🍊",
        ],
        "taken_by": None,
    },
    # Далі можна додати ще до 14 кольорів за бажанням
]

def get_user(user_id: int) -> Dict[str, Any]:
    if user_id not in USERS:
        USERS[user_id] = {
            "participant": False,
            "color_id": None,
            "task_index": None,  # індекс обраного завдання в масиві tasks
            "santa_joined": False,
            "santa_wish": None,
            "santa_child_id": None,
            "santa_id": None,
            "santa_gift_ready": False,
            "dish": None,
            "drink": None,
            "name": None,
            "username": None,
        }
    return USERS[user_id]

def get_color_by_id(color_id: int) -> Optional[Dict[str, Any]]:
    for c in COLORS:
        if c["id"] == color_id:
            return c
    return None

def get_available_colors():
    return [c for c in COLORS if c["taken_by"] is None]

# ====== KEYBOARDS ======
def main_menu_kb(user: Dict[str, Any]) -> ReplyKeyboardMarkup:
    buttons = []

    buttons.append([
        KeyboardButton(text="🎨 Мій колір"),
        KeyboardButton(text="🧩 Моя роль і завдання"),
    ])

    buttons.append([
        KeyboardButton(text="🍲 Моя страва і напій"),
        KeyboardButton(text="ℹ️ Про вечірку"),
    ])

    if user.get("participant"):
        buttons.append([KeyboardButton(text="🎅 Мій Миколайчик")])

    buttons.append([KeyboardButton(text="💬 Чат вечірки")])
    buttons.append([KeyboardButton(text="⭐ Фідбек / питання")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def colors_inline_kb() -> InlineKeyboardMarkup:
    available = get_available_colors()
    if not available:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Усі кольори вже розібрали 😅", callback_data="noop")]]
        )
    rows = []
    row = []
    for c in available:
        text = f"{c['emoji']} {c['name']}"
        row.append(InlineKeyboardButton(text=text, callback_data=f"color:{c['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def santa_join_menu_kb(user: Dict[str, Any]) -> InlineKeyboardMarkup:
    if not SANTA.registration_open:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Реєстрація ще не відкрита", callback_data="noop")]]
        )
    rows = []
    if not user.get("santa_joined"):
        rows.append([InlineKeyboardButton(text="✅ Хочу брати участь", callback_data="santa_join")])
        rows.append([InlineKeyboardButton(text="❌ Не хочу, пас", callback_data="santa_leave")])
    else:
        rows.append([InlineKeyboardButton(text="🚪 Вийти з гри (і з вечірки)", callback_data="santa_leave")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def santa_chat_kb(user: Dict[str, Any]) -> InlineKeyboardMarkup:
    rows = []
    if user.get("santa_child_id"):
        rows.append([InlineKeyboardButton(text="✉ Написати підопічному", callback_data="msg_child")])
    if user.get("santa_id"):
        rows.append([InlineKeyboardButton(text="✉ Написати моєму Миколайчику", callback_data="msg_santa")])
    rows.append([InlineKeyboardButton(text="❓ Питання про Миколайчика", callback_data="ask_santa_admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Список гостей", callback_data="admin_guests")],
            [InlineKeyboardButton(text="🎨 Кольори/ролі", callback_data="admin_colors")],
            [InlineKeyboardButton(text="🎅 Налаштування Миколайчика", callback_data="admin_santa")],
            [InlineKeyboardButton(text="📢 Оголошення в канал", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="💌 Листівка в канал", callback_data="admin_card")],
        ]
    )

def admin_santa_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔓 Відкрити/закрити реєстрацію", callback_data="admin_toggle_santa_reg")],
        [InlineKeyboardButton(text="💰 Задати/змінити бюджет", callback_data="admin_set_budget")],
        [InlineKeyboardButton(text="📄 Задати опис гри", callback_data="admin_set_santa_desc")],
        [InlineKeyboardButton(text="🎲 Згенерувати пари", callback_data="admin_gen_pairs")],
        [InlineKeyboardButton(text="📨 Розіслати підопічних", callback_data="admin_notify_pairs")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ====== HANDLERS ======
@router.message(CommandStart())
async def cmd_start(message: Message):
    user = get_user(message.from_user.id)
    user["name"] = message.from_user.full_name
    user["username"] = message.from_user.username

    text = (
        f"🎄 Привіт, я бот вечірки <b>«{PARTY_NAME}»</b>!\\n\\n"
        f"Місце: {PARTY_LOCATION}\\n"
        f"Дати: {PARTY_DATES_TEXT}\\n\\n"
        "Я допоможу тобі:\\n"
        "• зареєструватися на вечірку,\\n"
        "• обрати свій 🎨 колір-образ,\\n"
        "• отримати роль і таємне завдання,\\n"
        "• залетіти в гру 🎅 «Таємний Миколайчик»,\\n"
        "• додати свою страву і напій.\\n\\n"
        "Ти будеш на вечірці?"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎉 Так, я буду!", callback_data="party_yes")],
            [InlineKeyboardButton(text="🙈 Я просто дивлюсь", callback_data="party_no")],
        ]
    )

    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data == "party_yes")
async def cb_party_yes(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user["participant"] = True

    await callback.message.edit_text(
        "Круто, записав тебе як учасника «Різдвяного Спектру» 🎄\\n\\n"
        "Спочатку оберемо твій персональний 🎨 колір. "
        "Кожен колір можна зайняти тільки один раз.",
        reply_markup=colors_inline_kb(),
    )

@router.callback_query(F.data == "party_no")
async def cb_party_no(callback: CallbackQuery):
    await callback.message.edit_text(
        "Окей, можеш просто підглядати за підготовкою 😉\\n"
        "Якщо передумаєш — напиши /start."
    )

@router.callback_query(F.data.startswith("color:"))
async def cb_choose_color(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("participant"):
        await callback.answer("Спочатку підтверди, що ти будеш на вечірці 😉", show_alert=True)
        return

    color_id = int(callback.data.split(":")[1])
    color = get_color_by_id(color_id)
    if not color:
        await callback.answer("Щось пішло не так з цим кольором 🤔", show_alert=True)
        return

    if color["taken_by"] and color["taken_by"] != callback.from_user.id:
        await callback.answer("Цей колір уже зайнятий, обери інший 🙈", show_alert=True)
        return

    # звільняємо старий колір, якщо був
    if user.get("color_id"):
        old = get_color_by_id(user["color_id"])
        if old and old["taken_by"] == callback.from_user.id:
            old["taken_by"] = None

    color["taken_by"] = callback.from_user.id
    user["color_id"] = color_id
    # вибираємо випадкове завдання для цього користувача
    if color["tasks"]:
        user["task_index"] = random.randint(0, len(color["tasks"]) - 1)
    else:
        user["task_index"] = None

    # формуємо текст зі спойлером для кольору і завдання
    spoiler_text = f"Колір: {color['emoji']} {color['name']}\\nЗавдання: "
    task_text = color["tasks"][user["task_index"]] if user["task_index"] is not None else "Завдання ще не задано."

    full_spoiler = f"{spoiler_text}{task_text}"
    spoiler_html = f"<span class=\"tg-spoiler\">{full_spoiler}</span>"

    text = (
        f"{color['emoji']} Твій колір на вечірку обрано!\\n\\n"
        f"Твоя роль: <b>{color['role']}</b>\\n\\n"
        "Твій колір і мінізавдання сховані під спойлером нижче. "
        "Натисни на затемнений текст, щоб відкрити його (інші побачать тільки якщо ти покажеш екран):\\n\\n"
        f"{spoiler_html}\\n\\n"
        "У будь-який момент ти можеш подивитись це в меню: "
        "«🎨 Мій колір» та «🧩 Моя роль і завдання».\\n\\n"
        "Далі я попрошу тебе додати страву і напій, а потім — залетіти в гру «Таємний Миколайчик» 🎅"
    )

    await callback.message.edit_text(text)
    await callback.message.answer(
        "Ось твоє меню учасника 🎄",
        reply_markup=main_menu_kb(user),
    )

# ====== GUEST MENU HANDLERS ======
@router.message(F.text == "ℹ️ Про вечірку")
async def about_party(message: Message):
    text = (
        f"🎄 <b>{PARTY_NAME}</b>\\n"
        f"📍 {PARTY_LOCATION}\\n"
        f"🗓 {PARTY_DATES_TEXT}\\n\\n"
        f"{PARTY_RULES}"
    )
    await message.answer(text)

@router.message(F.text == "🎨 Мій колір")
async def my_color(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("color_id"):
        await message.answer("Ти ще не обрав свій колір. Натисни /start і пройди реєстрацію 🎨")
        return
    color = get_color_by_id(user["color_id"])
    if not color:
        await message.answer("Не можу знайти твій колір, напиши організатору.")
        return

    task_text = None
    if user.get("task_index") is not None and color["tasks"]:
        try:
            task_text = color["tasks"][user["task_index"]]
        except IndexError:
            task_text = None

    spoiler = f"Колір: {color['emoji']} {color['name']}\\nЗавдання: {task_text or 'Завдання ще не задано.'}"
    spoiler_html = f"<span class=\"tg-spoiler\">{spoiler}</span>"

    text = (
        f"Твоя роль: <b>{color['role']}</b>\\n\\n"
        "Твій колір і мінізавдання сховані під спойлером нижче. "
        "Натисни на затемнений текст, щоб побачити їх:\\n\\n"
        f"{spoiler_html}"
    )
    await message.answer(text)

@router.message(F.text == "🧩 Моя роль і завдання")
async def my_role_task(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("color_id"):
        await message.answer("Спочатку обери колір, тоді я дам тобі роль і завдання 😉")
        return
    color = get_color_by_id(user["color_id"])
    if not color:
        await message.answer("Щось пішло не так з твоїм кольором. Напиши організатору.")
        return

    task_text = None
    if user.get("task_index") is not None and color["tasks"]:
        try:
            task_text = color["tasks"][user["task_index"]]
        except IndexError:
            task_text = None

    spoiler = f"Колір: {color['emoji']} {color['name']}\\nЗавдання: {task_text or 'Завдання ще не задано.'}"
    spoiler_html = f"<span class=\"tg-spoiler\">{spoiler}</span>"

    text = (
        f"Твоя роль: <b>{color['role']}</b>\\n\\n"
        "Твій колір і мінізавдання сховані під спойлером:\\n\\n"
        f"{spoiler_html}"
    )
    await message.answer(text)

@router.message(F.text == "🍲 Моя страва і напій")
async def my_dish_drink(message: Message):
    user = get_user(message.from_user.id)
    text = (
        "Кожен гість приносить <b>страву</b> і <b>напій</b>.\\n"
        "Бажано, щоб страва максимально пасувала до твого кольору образу.\\n\\n"
        "Спочатку напиши, будь ласка, <b>що ти плануєш принести як страву</b> "
        "(десерт, салат, закуска тощо)."
    )
    await message.answer(text)
    PENDING_ACTION[message.from_user.id] = "set_dish"

@router.message(F.text == "🎅 Мій Миколайчик")
async def my_santa(message: Message):
    user = get_user(message.from_user.id)

    if not user.get("participant"):
        await message.answer("Спочатку підтвердь, що ти будеш на вечірці — натисни /start 🎄")
        return

    if not SANTA.registration_open and not user.get("santa_joined"):
        await message.answer(
            "Організатор ще не відкрив реєстрацію на гру «Таємний Миколайчик». "
            "Трохи терпіння, скоро все запустимо 🎅"
        )
        return

    if not user.get("santa_joined"):
        # показуємо правила і кнопку вступу
        budget_part = f"Орієнтовний бюджет: <b>{SANTA.budget_text}</b>\\n" if SANTA.budget_text else ""
        desc_part = f"{SANTA.description}\\n\\n" if SANTA.description else ""
        text = (
            f"{SANTA_BASE_RULES}\\n"
            f"{budget_part}"
            f"{desc_part}"
            "Хочеш залетіти в гру?"
        )
        await message.answer(text, reply_markup=santa_join_menu_kb(user))
        return

    # уже в грі
    if not SANTA.started:
        await message.answer(
            "Ти вже в грі 🎅, але пари ще не розподілені. "
            "Чекаємо, поки організатор запустить жеребкування."
        )
        return

    # Santa вже запущений
    child_id = user.get("santa_child_id")
    santa_id = user.get("santa_id")

    parts = ["🎅 <b>Твій Миколайчик</b>"]

    if child_id:
        child = USERS.get(child_id)
        parts.append("\\n\\n<b>Твій підопічний:</b>")
        parts.append(child.get("name") or "Гість")
        wish = child.get("santa_wish")
        if wish:
            parts.append("\\nПобажання / анти-побажання:")
            parts.append(wish)
        else:
            parts.append("\\nОбрав(ла) варіант: «Сюрприз» 🎁")

    if santa_id:
        parts.append("\\n\\nУ тебе також є свій Таємний Миколайчик — але хто це, я не скажу 😏")

    parts.append("\\n\\nМожеш анонімно написати своєму підопічному або своєму Миколайчику.")

    await message.answer("\\n".join(parts), reply_markup=santa_chat_kb(user))

@router.message(F.text == "💬 Чат вечірки")
async def party_chat(message: Message):
    if PARTY_CHAT_LINK:
        await message.answer(
            "Ось наш чат вечірки. Там можна спілкуватися, обговорювати меню і кидати меми 💬\\n"
            f"{PARTY_CHAT_LINK}"
        )
    else:
        await message.answer("Організатор ще не додав посилання на чат вечірки 🤔")

@router.message(F.text == "⭐ Фідбек / питання")
async def feedback_menu(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Загальний фідбек", callback_data="fb_general")],
            [InlineKeyboardButton(text="❓ Питання про Миколайчика", callback_data="fb_santa_question")],
        ]
    )
    await message.answer(
        "Тут ти можеш залишити загальний фідбек або поставити питання про гру «Таємний Миколайчик».",
        reply_markup=kb,
    )

# ====== CALLBACKS: SANTA REG, CHAT, FEEDBACK ======
@router.callback_query(F.data == "santa_join")
async def cb_santa_join(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not SANTA.registration_open:
        await callback.answer("Реєстрація ще не відкрита 🙈", show_alert=True)
        return
    user["santa_joined"] = True
    user["santa_gift_ready"] = False
    await callback.message.edit_text(
        "Ти в грі «Таємний Миколайчик» 🎅\\n\\n"
        "Напиши, будь ласка, що ти хотів/ла б отримати або чого точно не треба дарувати.\\n"
        "Якщо хочеш повний сюрприз — напиши просто «Сюрприз».",
    )
    PENDING_ACTION[callback.from_user.id] = "set_santa_wish"

@router.callback_query(F.data == "santa_leave")
async def cb_santa_leave(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    # вихід з гри = вихід із вечірки
    user_id = callback.from_user.id

    # звільняємо колір
    if user.get("color_id"):
        col = get_color_by_id(user["color_id"])
        if col and col["taken_by"] == user_id:
            col["taken_by"] = None

    # обнуляємо все інше
    user.update({
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
    })

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
    await callback.message.answer("Напиши повідомлення, яке я анонімно перешлю твоєму підопічному 👇")

@router.callback_query(F.data == "msg_santa")
async def cb_msg_santa(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("santa_id"):
        await callback.answer("У тебе поки немає Миколайчика 🤔", show_alert=True)
        return
    PENDING_ACTION[callback.from_user.id] = "msg_santa"
    await callback.message.answer("Напиши повідомлення, яке я анонімно перешлю твоєму Миколайчику 👇")

@router.callback_query(F.data == "ask_santa_admin")
async def cb_ask_santa_admin(callback: CallbackQuery):
    PENDING_ACTION[callback.from_user.id] = "ask_santa_admin"
    await callback.message.answer(
        "Напиши своє питання про Таємного Миколайчика.\\n"
        "Я перешлю його організатору. Можеш написати, якщо хочеш, що ти хочеш залишитись анонімним."
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

@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()

# ====== ADMIN ======
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
    if not USERS:
        lines.append("Поки нікого немає.")
    else:
        for uid, data in USERS.items():
            if not data.get("participant"):
                continue
            name = data.get("name") or f"id {uid}"
            color_txt = "-"
            if data.get("color_id"):
                c = get_color_by_id(data["color_id"])
                if c:
                    color_txt = f"{c['emoji']} {c['name']}"
            role_txt = "-"
            if data.get("color_id"):
                c = get_color_by_id(data["color_id"])
                if c:
                    role_txt = c["role"]
            dish_txt = data.get("dish") or "—"
            drink_txt = data.get("drink") or "—"
            santa_txt = "✅" if data.get("santa_joined") else "❌"
            gift_txt = "🎁" if data.get("santa_gift_ready") else "—"

            # завдання під спойлер
            task_text = ""
            if data.get("task_index") is not None and data.get("color_id"):
                c = get_color_by_id(data["color_id"])
                if c and c["tasks"]:
                    try:
                        t = c["tasks"][data["task_index"]]
                        task_text = f"<span class=\\"tg-spoiler\\">{t}</span>"
                    except IndexError:
                        task_text = ""

            lines.append(
                f"• <b>{name}</b> | Колір: {color_txt} | Роль: {role_txt} | "
                f"Страва: {dish_txt} | Напій: {drink_txt} | Santa: {santa_txt} | Подарунок: {gift_txt}"
            )
            if task_text:
                lines.append(f"  Завдання: {task_text}")

    await callback.message.edit_text("\\n".join(lines), reply_markup=admin_menu_kb())

@router.callback_query(F.data == "admin_colors")
async def admin_colors(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return

    lines = ["🎨 <b>Кольори і ролі</b>"]
    for c in COLORS:
        owner = "вільний"
        if c["taken_by"]:
            u = USERS.get(c["taken_by"])
            if u and u.get("name"):
                owner = u["name"]
            else:
                owner = f"id {c['taken_by']}"
        lines.append(f"{c['emoji']} <b>{c['name']}</b> — роль: {c['role']} | {owner}")

    await callback.message.edit_text("\\n".join(lines), reply_markup=admin_menu_kb())

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
        "🎅 <b>Налаштування Таємного Миколайчика</b>\\n\\n"
        f"Реєстрація: {reg_state}\\n"
        f"Стан гри: {started_state}\\n"
        f"Бюджет: {budget}\\n"
        f"Опис: {desc}\\n"
    )
    await callback.message.edit_text(text, reply_markup=admin_santa_menu_kb())

@router.callback_query(F.data == "admin_toggle_santa_reg")
async def admin_toggle_santa_reg(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    SANTA.registration_open = not SANTA.registration_open
    await admin_santa(callback)

@router.callback_query(F.data == "admin_set_budget")
async def admin_set_budget(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    PENDING_ACTION[callback.from_user.id] = "admin_set_budget"
    await callback.message.answer("Напиши текст бюджету для гри (наприклад: «до 600 грн»).")

@router.callback_query(F.data == "admin_set_santa_desc")
async def admin_set_santa_desc(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Це тільки для адміна 🙃", show_alert=True)
        return
    PENDING_ACTION[callback.from_user.id] = "admin_set_santa_desc"
    await callback.message.answer("Напиши опис гри «Таємний Миколайчик» (що важливо знати гостям).")

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

    # обнуляємо старі пари
    for uid in santa_players:
        USERS[uid]["santa_child_id"] = None
        USERS[uid]["santa_id"] = None

    n = len(santa_players)
    for i, santa_uid in enumerate(santa_players):
        child_uid = santa_players[(i + 1) % n]
        USERS[santa_uid]["santa_child_id"] = child_uid
        USERS[child_uid]["santa_id"] = santa_uid

    SANTA.started = True

    await callback.message.edit_text(
        f"Пари Таємного Миколайчика згенеровано 🎲\\nУчасників у грі: {len(santa_players)}",
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
            "🎅 <b>Твій підопічний у грі «Таємний Миколайчик»</b>\\n",
            f"Імʼя: <b>{child.get('name', 'Гість')}</b>",
        ]
        wish = child.get("santa_wish")
        if wish:
            parts.append("\\nПобажання / анти-побажання:")
            parts.append(wish)
        else:
            parts.append("\\nОбрав(ла) варіант: «Сюрприз» 🎁")

        parts.append(
            "\\n\\nНе пались завчасно 😉 "
            "Можеш написати йому/їй через меню «🎅 Мій Миколайчик»."
        )
        text = "\\n".join(parts)
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
        "Напиши текст оголошення. Я надішлю його всім учасникам у приват.\\n"
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

# ====== UNIVERSAL MESSAGE HANDLER (pending actions) ======
@router.message()
async def universal_handler(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    bot: Bot = message.bot

    action = PENDING_ACTION.pop(user_id, None)

    # Якщо нема pending-дїї — просто показуємо меню
    if not action:
        await message.answer(
            "Я тебе почув 👀 Користуйся кнопками нижче:",
            reply_markup=main_menu_kb(user),
        )
        return

    # --- Страва ---
    if action == "set_dish":
        user["dish"] = message.text.strip()
        await message.answer(
            "Записав твою страву 🍽️\\n"
            "Тепер напиши, будь ласка, який <b>напій</b> ти плануєш принести "
            "(алкогольний або безалкогольний)."
        )
        PENDING_ACTION[user_id] = "set_drink"
        return

    if action == "set_drink":
        user["drink"] = message.text.strip()
        await message.answer(
            f"Супер! Я записав:\\n"
            f"• Страва: {user['dish']}\\n"
            f"• Напій: {user['drink']}\\n\\n"
            "Памʼятай, що страва бажано має підходити під твій колір образу 😉",
            reply_markup=main_menu_kb(user),
        )
        return

    # --- Santa wish ---
    if action == "set_santa_wish":
        txt = message.text.strip()
        if txt.lower() in ("сюрприз", "surprise"):
            user["santa_wish"] = None
            await message.answer(
                "Окей, записав, що ти за сюрпризи 🎁\\n"
                "Коли організатор запустить гру, я скажу тобі, хто твій підопічний.",
                reply_markup=main_menu_kb(user),
            )
        else:
            user["santa_wish"] = txt
            await message.answer(
                "Зберіг твої побажання для Таємного Миколайчика 🎅\\n"
                "Коли організатор запустить гру, я скажу тобі, хто твій підопічний.",
                reply_markup=main_menu_kb(user),
            )
        return

    # --- Santa messages ---
    if action == "msg_child":
        target_id = user.get("santa_child_id")
        if not target_id:
            await message.answer("Схоже, у тебе вже немає підопічного 🤔")
            return
        text = (
            "✉ Тобі повідомлення від твого Таємного Миколайчика:\\n\\n"
            f"{message.text}"
        )
        try:
            await bot.send_message(target_id, text)
            await message.answer("Я передав твоє повідомлення твоєму підопічному ✉")
        except Exception:
            await message.answer("Не зміг доставити повідомлення підопічному 😔")
        return

    if action == "msg_santa":
        target_id = user.get("santa_id")
        if not target_id:
            await message.answer("Схоже, у тебе немає Миколайчика 🤔")
            return
        text = (
            "✉ Тобі повідомлення від твого підопічного у грі «Таємний Миколайчик»:\\n\\n"
            f"{message.text}"
        )
        try:
            await bot.send_message(target_id, text)
            await message.answer("Я передав твоє повідомлення твоєму Миколайчику ✉")
        except Exception:
            await message.answer("Не зміг доставити повідомлення Миколайчику 😔")
        return

    # --- Question to admin about Santa ---
    if action == "ask_santa_admin":
        try:
            await bot.send_message(
                ADMIN_ID,
                f"❓ Питання про Миколайчика від {user.get('name') or user_id} (@{user.get('username') or '-'}):\\n\\n"
                f"{message.text}",
            )
            await message.answer("Я передав твоє питання організатору 🎅")
        except Exception:
            await message.answer("Не зміг передати питання організатору 😔")
        return

    # --- General feedback ---
    if action == "fb_general":
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⭐ Фідбек від {user.get('name') or user_id} (@{user.get('username') or '-'}):\\n\\n"
                f"{message.text}",
            )
            await message.answer("Дякую за фідбек! Я передав його організатору 🫶")
        except Exception:
            await message.answer("Не зміг передати фідбек організатору 😔")
        return

    # --- Admin: set budget ---
    if action == "admin_set_budget":
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        SANTA.budget_text = message.text.strip()
        await message.answer(f"Оновив бюджет для Миколайчика: {SANTA.budget_text}")
        return

    # --- Admin: set santa description ---
    if action == "admin_set_santa_desc":
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        SANTA.description = message.text.strip()
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

    # --- Admin: card to channel ---
    if action == "admin_card":
        if user_id != ADMIN_ID:
            await message.answer("Це тільки для адміна 🙃")
            return
        # превʼю + кнопка відправки в канал
        preview = (
            "Ось превʼю листівки, яку можна відправити в канал:\\n\\n"
            f"{message.text}\\n\\n"
            "Натисни кнопку нижче, щоб опублікувати в канал."
        )
        # зберігаємо текст у контексті
        PENDING_CONTEXT[user_id] = message.text
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Опублікувати в канал", callback_data="admin_card_publish")],
                [InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_card_cancel")],
            ]
        )
        await message.answer(preview, reply_markup=kb)
        return

    # fallback
    await message.answer(
        "Я тебе почув 👀 Користуйся кнопками нижче:",
        reply_markup=main_menu_kb(user),
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
    if not PARTY_CHANNEL_ID:
        await callback.message.answer(
            "PARTY_CHANNEL_ID не заданий, не знаю, куди відправити листівку. "
            "Додай змінну середовища і перезапусти сервіс."
        )
        return
    try:
        await callback.message.bot.send_message(PARTY_CHANNEL_ID, text)
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

# ====== RUN BOT ======
async def main():
    bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.include_router(router)
    print("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
"""
print(len(bot_code.splitlines()))
