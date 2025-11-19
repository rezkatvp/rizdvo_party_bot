import os
import asyncio
import random
from typing import Dict, Optional

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

# ====== НАЛАШТУВАННЯ З АРХІВУ / RAILWAY ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PARTY_CHAT_LINK = os.getenv("PARTY_CHAT_LINK")  # типу "https://t.me/your_chat"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не заданий в змінних середовища")

# ====== ПАМ'ЯТЬ У ПРОЦЕСІ (ДЛЯ ОДНІЄЇ ВЕЧІРКИ ЦЕ ОК) ======
router = Router()

# user_id -> дані
USERS: Dict[int, Dict] = {}

# кольори / ролі / завдання
COLORS = [
    {
        "id": 1,
        "emoji": "🔴",
        "name": "Червоний",
        "role": "Вогняний Різдвяний Хайп-мейкер",
        "task": "Твоє завдання — хоча б тричі за вечір підбурити людей до тосту або чірсу. Робиш це весело, але ненавʼязливо 😉",
        "taken_by": None,
    },
    {
        "id": 2,
        "emoji": "🟢",
        "name": "Зелений",
        "role": "Головний Ялинковий Декоратор",
        "task": "Твоє завдання — непомітно переконати мінімум трьох людей зробити з тобою фотку біля чогось зеленого.",
        "taken_by": None,
    },
    {
        "id": 3,
        "emoji": "🔵",
        "name": "Синій",
        "role": "Сніговий Chill-майстер",
        "task": "Твоє завдання — мінімум тричі за вечір зʼявитись поруч, коли хтось каже «холодно» або «жарко», і видати якусь холодну/снігову фразу 😏",
        "taken_by": None,
    },
    {
        "id": 4,
        "emoji": "🟡",
        "name": "Жовтий",
        "role": "Сонце Різдвяної Тусовки",
        "task": "Твоє завдання — протягом вечора хоч тричі врятувати ніякову паузу якимось жартом або історією.",
        "taken_by": None,
    },
    {
        "id": 5,
        "emoji": "🟣",
        "name": "Фіолетовий",
        "role": "Маг Таємних Подарунків",
        "task": "Твоє завдання — ненавʼязливо підкинути комусь маленьку несподіванку: записку, стікер, милий комплімент.",
        "taken_by": None,
    },
    {
        "id": 6,
        "emoji": "🧡",
        "name": "Помаранчевий",
        "role": "Мандариновий Контрабандист",
        "task": "Твоє завдання — мінімум тричі за вечір якось згадати мандаринки або апельсини й під це підвести якийсь прикол.",
        "taken_by": None,
    },
]

# чи вже запущений Таємний Миколайчик (роздані пари)
SANTA_STARTED = False

# кому наступне повідомлення переслати (для анонімного чату)
# user_id -> target_user_id
NEXT_MESSAGE_TARGET: Dict[int, int] = {}


# ====== ДОПОМІЖНІ ======
def get_user(user_id: int) -> Dict:
    if user_id not in USERS:
        USERS[user_id] = {
            "participant": False,
            "color_id": None,
            "santa_joined": False,
            "santa_wish": None,
            "child_id": None,
            "santa_id": None,
            "dish": None,
            "name": None,
            "username": None,
        }
    return USERS[user_id]


def get_color_by_id(color_id: int) -> Optional[Dict]:
    for c in COLORS:
        if c["id"] == color_id:
            return c
    return None


def get_available_colors():
    return [c for c in COLORS if c["taken_by"] is None]


def main_menu_kb(user: Dict) -> ReplyKeyboardMarkup:
    buttons = []

    row1 = [
        KeyboardButton(text="🎨 Мій колір"),
        KeyboardButton(text="🧩 Моє завдання"),
    ]
    buttons.append(row1)

    row2 = [KeyboardButton(text="🍲 Моя страва")]
    buttons.append(row2)

    if SANTA_STARTED and user.get("santa_joined"):
        row3 = [KeyboardButton(text="🎅 Мій Миколайчик")]
        buttons.append(row3)

    row_chat = [KeyboardButton(text="💬 Чат вечірки")]
    buttons.append(row_chat)

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
    )


def colors_inline_kb() -> InlineKeyboardMarkup:
    buttons = []
    available = get_available_colors()
    if not available:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Усі кольори вже розібрали 😅", callback_data="noop")]
        ])
    row = []
    for c in available:
        text = f"{c['emoji']} {c['name']}"
        row.append(InlineKeyboardButton(text=text, callback_data=f"color:{c['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def santa_menu_inline_kb(user: Dict) -> InlineKeyboardMarkup:
    buttons = []

    if not user.get("santa_joined"):
        buttons.append([
            InlineKeyboardButton(text="✅ Хочу брати участь", callback_data="santa_join"),
        ])
        buttons.append([
            InlineKeyboardButton(text="❌ Не хочу, пас", callback_data="santa_leave"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="🚪 Вийти з гри", callback_data="santa_leave"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def santa_chat_inline_kb(user: Dict) -> InlineKeyboardMarkup:
    buttons = []
    if user.get("child_id"):
        buttons.append([
            InlineKeyboardButton(text="✉ Написати підопічному", callback_data="msg_child"),
        ])
    if user.get("santa_id"):
        buttons.append([
            InlineKeyboardButton(text="✉ Написати моєму Миколайчику", callback_data="msg_santa"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Нема з ким писати 😅", callback_data="noop")]])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Список гостей", callback_data="admin_guests"),
            ],
            [
                InlineKeyboardButton(text="🎅 Згенерувати пари Миколайчика", callback_data="admin_gen_pairs"),
            ],
            [
                InlineKeyboardButton(text="📨 Розіслати підопічних", callback_data="admin_notify_pairs"),
            ],
        ]
    )


# ====== ХЕНДЛЕРИ КОРИСТУВАЧА ======
@router.message(CommandStart())
async def cmd_start(message: Message):
    user = get_user(message.from_user.id)
    user["name"] = message.from_user.full_name
    user["username"] = message.from_user.username

    text = (
        "🎄 Привіт, я твій новорічний бот-дружбан!\n\n"
        "Я допоможу:\n"
        "• зареєструватися на вечірку,\n"
        "• обрати свій 🎨 колір-образ,\n"
        "• отримати таємну роль і завдання,\n"
        "• залетіти в гру 🎅 «Таємний Миколайчик».\n\n"
        "Поїхали? Ти точно будеш на вечірці?"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎉 Так, я буду!", callback_data="party_yes"),
            ],
            [
                InlineKeyboardButton(text="🙈 Я просто дивлюсь", callback_data="party_no"),
            ],
        ]
    )

    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "party_yes")
async def cb_party_yes(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user["participant"] = True

    await callback.message.edit_text(
        "Круто, записав тебе як учасника вечірки 🎄\n\n"
        "Спочатку оберемо твій 🎨 *персональний колір*.\n"
        "Кожен колір можна зайняти лише один раз!",
        reply_markup=colors_inline_kb(),
    )


@router.callback_query(F.data == "party_no")
async def cb_party_no(callback: CallbackQuery):
    await callback.message.edit_text(
        "Окей, можеш просто підглядати за підготовкою 😉\n"
        "Якщо передумаєш — знову натисни /start."
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
        await callback.answer("Цей колір вже забрали, обери інший 🙈", show_alert=True)
        return

    # Якщо у користувача вже був колір — звільнити
    if user.get("color_id"):
        old = get_color_by_id(user["color_id"])
        if old and old["taken_by"] == callback.from_user.id:
            old["taken_by"] = None

    color["taken_by"] = callback.from_user.id
    user["color_id"] = color_id

    text = (
        f"{color['emoji']} Твій колір на вечірку: *{color['name']}*.\n\n"
        f"Твоя роль: *{color['role']}*\n\n"
        f"Твоє таємне завдання на вечірку (ніхто не має знати 👀):\n"
        f"||{color['task']}||\n\n"
        "Можеш переглядати це в меню: *🎨 Мій колір* та *🧩 Моє завдання*.\n\n"
        "А тепер можна зареєструватися в грі 🎅 «Таємний Миколайчик» або додати свою страву 🍲."
    )

    await callback.message.edit_text(text)
    await callback.message.answer(
        "Ось твоє меню учасника 🎄",
        reply_markup=main_menu_kb(user),
    )


# ===== КНОПКИ МЕНЮ ГОСТЯ =====
@router.message(F.text == "🎨 Мій колір")
async def my_color(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("color_id"):
        await message.answer("Ти ще не обрав свій колір. Натисни /start і пройди реєстрацію 🎨")
        return

    color = get_color_by_id(user["color_id"])
    await message.answer(
        f"Твій колір: {color['emoji']} *{color['name']}*",
        reply_markup=main_menu_kb(user),
        parse_mode="Markdown",
    )


@router.message(F.text == "🧩 Моє завдання")
async def my_task(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("color_id"):
        await message.answer("Спочатку обери колір, тоді дам тобі завдання 😉")
        return
    color = get_color_by_id(user["color_id"])
    await message.answer(
        f"Твоя роль: *{color['role']}*\n\n"
        f"Твоє завдання:\n{color['task']}",
        reply_markup=main_menu_kb(user),
        parse_mode="Markdown",
    )


@router.message(F.text == "🍲 Моя страва")
async def my_dish(message: Message):
    user = get_user(message.from_user.id)
    if user.get("dish"):
        await message.answer(
            f"Ти плануєш принести: *{user['dish']}*.\n"
            f"Якщо хочеш змінити — просто напиши новий варіант.",
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            "Напиши, будь ласка, що ти плануєш принести (страва/напій)."
        )

    # наступне текстове повідомлення сприймемо як страву
    NEXT_MESSAGE_TARGET.pop(message.from_user.id, None)
    # позначимо спеціальним значенням
    NEXT_MESSAGE_TARGET[message.from_user.id] = -1


@router.message(F.text == "🎅 Мій Миколайчик")
async def my_santa(message: Message):
    user = get_user(message.from_user.id)
    if not user.get("santa_joined"):
        # показуємо меню вступу
        text = (
            "🎅 *Таємний Миколайчик*\n\n"
            "Гра, де кожен таємно дарує комусь подарунок.\n"
            "Бюджет: до ~500 грн (можна адаптувати).\n"
            "Подарунок — щось приємне, душевне і без трешу 🙃\n\n"
            "Хочеш залетіти в гру?"
        )
        await message.answer(text, reply_markup=santa_menu_inline_kb(user), parse_mode="Markdown")
        return

    if not SANTA_STARTED:
        await message.answer(
            "Ти вже в грі, але пари ще не розподілені. Чекаємо, поки організатор запустить Миколайчика 🎅"
        )
        return

    child_id = user.get("child_id")
    santa_id = user.get("santa_id")

    text_parts = ["🎅 *Твій Миколайчик*"]

    if child_id:
        child = USERS.get(child_id)
        text_parts.append(
            f"\n\nТвій підопічний:\n*{child.get('name', 'Гість')}*"
        )
        if child.get("santa_wish"):
            text_parts.append(
                f"\nЙого/її побажання:\n_{child['santa_wish']}_"
            )
        else:
            text_parts.append("\nВін/вона обрав(ла) варіант: «Сюрприз» 🎁")

    if santa_id:
        # про самого Санту нічого не розкриваємо
        text_parts.append("\n\nВ тебе також є свій Таємний Миколайчик — але хто це, я не скажу 😏")

    text_parts.append("\n\nМожеш анонімно написати:\n• своєму підопічному\n• своєму Миколайчику")

    await message.answer(
        "\n".join(text_parts),
        reply_markup=santa_chat_inline_kb(user),
        parse_mode="Markdown",
    )


@router.message(F.text == "💬 Чат вечірки")
async def party_chat(message: Message):
    if PARTY_CHAT_LINK:
        await message.answer(f"Ось наш загальний чат вечірки 💬\n{PARTY_CHAT_LINK}")
    else:
        await message.answer("Організатор ще не додав посилання на чат вечірки 🤔")


# ====== КОЛБЕКИ ТАЄМНОГО МИКОЛАЙЧИКА ======
@router.callback_query(F.data == "santa_join")
async def cb_santa_join(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user["santa_joined"] = True

    await callback.message.edit_text(
        "Ти в грі 🎅\n\n"
        "Напиши, будь ласка, що ти хотів/ла б отримати, або що точно не дарувати.\n"
        "Якщо хочеш повний сюрприз — напиши просто «Сюрприз».",
    )

    # наступне повідомлення від юзера буде його побажанням
    NEXT_MESSAGE_TARGET.pop(callback.from_user.id, None)
    NEXT_MESSAGE_TARGET[callback.from_user.id] = -2


@router.callback_query(F.data == "santa_leave")
async def cb_santa_leave(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user["santa_joined"] = False
    user["santa_wish"] = None
    user["child_id"] = None
    user["santa_id"] = None
    await callback.message.edit_text("Добре, я виключив тебе з гри Таємного Миколайчика 🎅")


@router.callback_query(F.data == "msg_child")
async def cb_msg_child(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("child_id"):
        await callback.answer("У тебе поки немає підопічного 🤔", show_alert=True)
        return
    NEXT_MESSAGE_TARGET[callback.from_user.id] = user["child_id"]
    await callback.message.answer(
        "Напиши повідомлення, яке я перешлю твоєму підопічному анонімно 👇"
    )


@router.callback_query(F.data == "msg_santa")
async def cb_msg_santa(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user.get("santa_id"):
        await callback.answer("У тебе поки немає Миколайчика 🤔", show_alert=True)
        return
    NEXT_MESSAGE_TARGET[callback.from_user.id] = user["santa_id"]
    await callback.message.answer(
        "Напиши повідомлення, яке я перешлю твоєму Миколайчику анонімно 👇"
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


# ====== АДМІН ======
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Ти не виглядаєш як організатор цієї тусовки 😏")
        return

    await message.answer(
        "Привіт, організаторе 🎄 Що робимо?",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(F.data == "admin_guests")
async def admin_guests(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ти не адмін 🙃", show_alert=True)
        return

    lines = ["👥 *Гості:*"]
    if not USERS:
        lines.append("Поки що нікого немає.")
    else:
        for uid, data in USERS.items():
            if not data.get("participant"):
                continue
            name = data.get("name") or f"id {uid}"
            color_txt = "—"
            if data.get("color_id"):
                c = get_color_by_id(data["color_id"])
                if c:
                    color_txt = f"{c['emoji']} {c['name']}"
            dish_txt = data.get("dish") or "не вказав(ла)"
            santa_txt = "так" if data.get("santa_joined") else "ні"

            lines.append(f"• {name} | Колір: {color_txt} | Страва: {dish_txt} | Миколайчик: {santa_txt}")

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(F.data == "admin_gen_pairs")
async def admin_gen_pairs(callback: CallbackQuery):
    global SANTA_STARTED
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ти не адмін 🙃", show_alert=True)
        return

    santa_players = [uid for uid, data in USERS.items() if data.get("santa_joined")]
    if len(santa_players) < 2:
        await callback.answer("В грі замало людей для пар 😅", show_alert=True)
        return

    random.shuffle(santa_players)

    # обнуляємо старі пари
    for uid in santa_players:
        USERS[uid]["child_id"] = None
        USERS[uid]["santa_id"] = None

    # кільце: кожен дарує наступному, останній — першому
    n = len(santa_players)
    for i, santa_uid in enumerate(santa_players):
        child_uid = santa_players[(i + 1) % n]
        USERS[santa_uid]["child_id"] = child_uid
        USERS[child_uid]["santa_id"] = santa_uid

    SANTA_STARTED = True

    await callback.message.edit_text(
        f"Пари Таємного Миколайчика згенеровано 🎅\nУчасників у грі: {len(santa_players)}",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(F.data == "admin_notify_pairs")
async def admin_notify_pairs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Ти не адмін 🙃", show_alert=True)
        return

    bot: Bot = callback.message.bot

    count = 0
    for uid, data in USERS.items():
        if not data.get("santa_joined"):
            continue
        child_id = data.get("child_id")
        if not child_id:
            continue
        child = USERS.get(child_id)
        if not child:
            continue

        text_parts = [
            "🎅 *Твій підопічний у грі «Таємний Миколайчик»*",
            f"\nІмʼя: *{child.get('name', 'Гість')}*",
        ]
        if child.get("santa_wish"):
            text_parts.append(f"\nПобажання / анти-побажання:\n_{child['santa_wish']}_")
        else:
            text_parts.append("\nОбрав(ла) варіант «Сюрприз» 🎁")

        text_parts.append(
            "\n\nНе пались завчасно 😉\n"
            "Можеш написати йому/їй через меню: *🎅 Мій Миколайчик*."
        )

        try:
            await bot.send_message(uid, "\n".join(text_parts), parse_mode="Markdown")
            count += 1
        except Exception:
            pass

    await callback.message.edit_text(
        f"Розіслав інформацію про підопічних {count} учасникам 🎄",
        reply_markup=admin_menu_kb(),
    )


# ====== УНІВЕРСАЛЬНИЙ ХЕНДЛЕР ДЛЯ «НАСТУПНОГО ПОВІДОМЛЕННЯ» ======
@router.message()
async def catch_all(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)

    # Якщо це — "наступне повідомлення" для чогось
    if user_id in NEXT_MESSAGE_TARGET:
        target = NEXT_MESSAGE_TARGET.pop(user_id)

        # -1 = ми очікуємо страву
        if target == -1:
            user["dish"] = message.text.strip()
            await message.answer(
                f"Записав, що ти плануєш принести: *{user['dish']}* 🍲",
                parse_mode="Markdown",
                reply_markup=main_menu_kb(user),
            )
            return

        # -2 = ми очікуємо побажання для Миколайчика
        if target == -2:
            txt = message.text.strip()
            if txt.lower() in ("сюрприз", "surprise"):
                user["santa_wish"] = None
                await message.answer(
                    "Окей, записав: ти за сюрпризи 🎁\n"
                    "Пари роздамо трохи пізніше, чекай на мене 😉",
                    reply_markup=main_menu_kb(user),
                )
            else:
                user["santa_wish"] = txt
                await message.answer(
                    "Зберіг твої побажання для Таємного Миколайчика 🎅\n"
                    "Пари роздамо трохи пізніше, чекай на мене 😉",
                    reply_markup=main_menu_kb(user),
                )
            return

        # інакше target — це інший user_id (Santa-чат)
        target_user = USERS.get(target)
        if not target_user:
            await message.answer("Зараз не можу доставити це повідомлення 🤔")
            return

        bot: Bot = message.bot
        try:
            if user.get("child_id") == target:
                # пишемо підопічному
                text = (
                    "✉ Тобі повідомлення від твого Таємного Миколайчика:\n\n"
                    f"{message.text}"
                )
            elif user.get("santa_id") == target:
                text = (
                    "✉ Тобі повідомлення від твого підопічного у грі «Таємний Миколайчик»:\n\n"
                    f"{message.text}"
                )
            else:
                text = message.text

            await bot.send_message(target, text)
            await message.answer("Я передав твоє повідомлення анонімно ✉")
        except Exception:
            await message.answer("Не зміг доставити повідомлення 😔")
        return

    # Якщо це просто будь-яке інше повідомлення — пропонуємо меню
    await message.answer(
        "Я тебе почув 👀\nКористуйся кнопками нижче:",
        reply_markup=main_menu_kb(user),
    )


# ====== ЗАПУСК БОТА ======
async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("Bot is starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
