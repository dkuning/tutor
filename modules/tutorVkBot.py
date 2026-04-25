import os
import logging
from datetime import datetime

from dotenv import load_dotenv
from vkbottle import Callback, GroupEventType, GroupTypes, ShowSnackbarEvent
from vkbottle.bot import Bot, Message as BotMessage
from vkbottle.tools import Keyboard, Text, KeyboardButtonColor

from storage import init_db, get_student_by_vkid, get_schedule_for_student, get_schedule, get_subject,add_payment_request,get_payment_by_id,get_active_payment_requests,get_tutor,update_payment_status,get_student_by_tgid
from study import command_list_of_study
import json

load_dotenv()

# --- Настройка логирования ---
LOG_DIR = './logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'tutorVkBot.log')

logger = logging.getLogger('tutorVkBot')
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# --- Конфигурация ---
VK_TOKEN = os.environ.get("VK_BOT_TOKEN")
if not VK_TOKEN:
    raise ValueError("Не задана переменная окружения VK_BOT_TOKEN")
logger.debug("Получили токен VK")

USER_WHITE_LIST_STR = os.environ.get("VK_USER_WHITE_LIST", "")
USER_WHITE_LIST = []
if USER_WHITE_LIST_STR:
    try:
        USER_WHITE_LIST = [int(uid.strip()) for uid in USER_WHITE_LIST_STR.split(",") if uid.strip().isdigit()]
        logger.debug(f"Белый список пользователей ВК: {USER_WHITE_LIST}")
    except ValueError:
        logger.error("Некорректные данные в USER_WHITE_LIST. Должны быть числа.")

PAY_LIST_STR = os.environ.get("VK_PAY_LIST", "")
PAY_LIST = []
if PAY_LIST_STR:
    try:
        PAY_LIST = [int(uid.strip()) for uid in PAY_LIST_STR.split(",") if uid.strip().isdigit()]
        logger.debug(f"Список родителей ВК: {PAY_LIST}")
    except ValueError:
        logger.error("Некорректные данные в PAY_LIST.")

# --- Инициализация бота ---
bot = Bot(token=VK_TOKEN)
init_db()

# Общие функции
def get_json_payload (payload):
    try:
        result = json.loads(payload) if payload else {}
    except (json.JSONDecodeError, TypeError):
        result = {}
    return result

async def clear_keyboard_message(peer_id,conversation_message_id):
    logger.debug(str(peer_id) + " - Зачищаем сообщение с клавиатурой " + str(conversation_message_id))
    try:
        await bot.api.messages.edit(
            peer_id=peer_id,
            conversation_message_id=conversation_message_id,
            message='Выбор сделан',
            keyboard="{}"
        )
    except Exception as e:
        logger.warning(str(peer_id) + f" - Не удалось отредактировать сообщение: {e}")

async def delete_keyboard_message(peer_id,conversation_message_id):
    logger.debug(str(peer_id) + " - Удаляем сообщение с клавиатурой " + str(conversation_message_id))
    try:
        await bot.api.messages.delete(
            peer_id=peer_id,
            cmids=[conversation_message_id],
            delete_for_all=True
        )
    except Exception as e:
        logger.warning(str(peer_id) + f" - Не удалось удалить сообщение: {e}")

# --- Клавиатуры ---
def get_test_keyboard():
    keyboard = Keyboard(one_time=False, inline=True)
    keyboard.add(Callback("Тест_Кнопка_1", payload={"cmd": "btn1"}), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text("Тест_Кнопка_2", payload={"cmd": "btn2"}), color=KeyboardButtonColor.POSITIVE)
    return keyboard.get_json()

def get_main_keyboard():
    keyboard = Keyboard(one_time=False, inline=True)
    keyboard.add(Callback("Занятия", payload={"cmd": "lessons"}), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Callback("Платежи", payload={"cmd": "payments"}), color=KeyboardButtonColor.PRIMARY)
    return keyboard.get_json()

def generate_subject_keyboard(schedule):
    keyboard = Keyboard(inline=True)

    for lesson in schedule:
        schedule_id = lesson.get("schedule_id")
        subject_name = lesson.get("name")
        keyboard.add(Callback(subject_name, {"cmd": f"subject_{schedule_id}"}))
        keyboard.row()

    return keyboard.get_json()
# --- Обработчики ---

# Тесты
@bot.on.message(text=["Тест", "тест"])
async def test(message: BotMessage):
    sent = await message.answer("Доступные тесты", keyboard=get_test_keyboard())
    logger.debug ("Сообщение с inline клавиатурой: "+ str(sent))

@bot.on.message(text=["Тест_Кнопка_2"])
async def test_but_2 (message: BotMessage):
    logger.debug("Получено сообщение:" + str(message))
    await clear_keyboard_message(message.peer_id, message.conversation_message_id-1) # всегда зачищаем предыдущее сообщение с inline-клавиатурой

# Общий обработчик событий с callback-кнопок
@bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=GroupTypes.MessageEvent)
async def handle_message_event(event: GroupTypes.MessageEvent):
    logger.debug(f"{event.object.user_id} - Получено событие: {event}")
    await delete_keyboard_message(event.object.peer_id, event.object.conversation_message_id) # всегда удаляем предыдущее сообщение с inline-клавиатурой
    cmd = event.object.payload.get("cmd")
    event_id = event.object.event_id
    peer_id = event.object.peer_id
    user_id = event.object.user_id
    msg_str = "Выбрана команда: " + cmd

    await bot.api.messages.send_message_event_answer(
        event_id=event.object.event_id,
        user_id=event.object.user_id,
        peer_id=event.object.peer_id,
        event_data=ShowSnackbarEvent(text=msg_str).model_dump_json(),
    )

    if cmd == "lessons":
        logger.info(f"{event.object.user_id} - Пользователь запросил список занятий")
        student_id = get_student_by_vkid(event.object.user_id)['tg_id']
        schedule = get_schedule_for_student(student_id)
        keyboard = generate_subject_keyboard(schedule)
        await bot.api.messages.send(
            peer_id=event.object.peer_id,
            message="Выберите предмет:",
            keyboard=keyboard,
            random_id=0
        )

    if cmd.startswith("subject_"):
        schedule_id = cmd.replace('subject_', '')
        logger.info(f"{event.object.user_id} - Пользователь выбрал элемент расписания {schedule_id}")
        logger.info(f"{event.object.user_id} - Формируем событие оплаты")
        student = get_student_by_vkid(event.object.user_id)
        schedule = get_schedule(schedule_id)
        payment_event = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'user_id': student['tg_id'],
            'username': student['name'],
            'first_name': student['name'],
            'subject_id': schedule['subject_id'],
            'tutor_id': schedule['tutor_id'],
            'price': schedule['price']
        }

        # Сохраняем в БД
        payment_event_result = add_payment_request(payment_event)
        logger.info(f"{event.object.user_id} - Событие оплаты добавлено в БД: {get_payment_by_id(payment_event_result)}")

        subject = get_subject(schedule['subject_id'])
        reply_msg = f"Отлично! Ты выбрал: *{subject['name']}*"
        reply_msg = reply_msg + f"\nСтоимость занятия: {schedule['price']} ₽"
        reply_msg = reply_msg + f"\n\nОтправляем сообщение родителям — Папа, Мама, оплатите репетитора! 😉"
        await bot.api.messages.send(
            peer_id=event.object.peer_id,
            message=reply_msg,
            random_id=0
        )

    if cmd == "payments":
        logger.info(f"{event.object.user_id} - Пользователь запросил список платежей")

        # Проверка доступа (белый список родителей)
        if event.object.user_id not in PAY_LIST:
            logger.warning(f"Пользователь {event.object.user_id} пытается получить доступ к платежам без прав")
            await bot.api.messages.send(
                peer_id=event.object.peer_id,
                message="❌ Доступ к этой команде ограничен.",
                random_id=0
            )
            return

        payment_requests = get_active_payment_requests()
        if not payment_requests:
            await bot.api.messages.send(
                peer_id=event.object.peer_id,
                message="✅ Все оплачено! 🎉",
                random_id=0
            )
            return

        # Формируем список неоплаченных
        lines = ["⚠ Неоплаченные занятия:"]
        for i, req in enumerate(payment_requests, 1):
            lines.append(f"{i}. {req['date']} — {req['subject']} ({req['first_name']})")
        lines.append("\nВыберите, что хотите оплатить:")
        payment_text = "\n".join(lines)

        # Генерируем inline-клавиатуру с кнопками для каждого платежа
        keyboard = Keyboard(inline=True)
        for req in payment_requests:
            text = f"Оплатить: {req['subject']}"
            keyboard.add(Callback(text, payload={"cmd": f"pay_{req['id']}", "payment_id": req["id"]}))
            keyboard.row()

        await bot.api.messages.send(
            peer_id=event.object.peer_id,
            message=payment_text,
            keyboard=keyboard.get_json(),
            random_id=0
        )

    if cmd.startswith("pay_"):
        try:
            payment_id = int(cmd.split("_")[1])
        except (IndexError, ValueError):
            await bot.api.messages.send_message_event_answer(
                event_id=event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=ShowSnackbarEvent(text="❌ Неверный идентификатор платежа").model_dump_json(),
            )
            return

        req = next((r for r in get_active_payment_requests() if r["id"] == payment_id), None)
        if not req:
            await bot.api.messages.send_message_event_answer(
                event_id=event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=ShowSnackbarEvent(text="❌ Платёж не найден").model_dump_json(),
            )
            return

        tutor = get_tutor(req["tutor_id"])
        reply_msg = (
            f"📄 Детали оплаты:\n\n"
            f"📚 Предмет: {req['subject']}\n"
            f"🎓 Репетитор: {tutor['name']}\n"
            f"🏦 Банк: {tutor['bank']}\n"
            f"💰 Сумма: {req['price']} ₽\n\n"
            f"Выберите действие:"
        )

        keyboard = Keyboard(inline=True)
        keyboard.add(Callback("✅ Подтвердить", {"cmd": f"payConfirm_{payment_id}"}))
        keyboard.row()
        keyboard.add(Callback("🕒 Отложить", {"cmd": f"payDelay_{payment_id}"}))
        keyboard.row()
        keyboard.add(Callback("❌ Отменить", {"cmd": f"payCancel_{payment_id}"}))

        await bot.api.messages.send(
            peer_id=peer_id,
            message=reply_msg,
            keyboard=keyboard.get_json(),
            random_id=0
        )

    if cmd.startswith("payConfirm_"):
        try:
            payment_id = int(cmd.replace("payConfirm_", ""))
        except ValueError:
            return

        req = next((r for r in get_active_payment_requests() if r["id"] == payment_id), None)
        if not req:
            await bot.api.messages.send_message_event_answer(
                event_id=event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=ShowSnackbarEvent(text="❌ Платёж не найден").model_dump_json(),
            )
            return

        update_payment_status(payment_id, "COMPLETE")
        logger.info(f"Платёж подтверждён: {get_payment_by_id(payment_id)}")

        # Уведомление плательщика
        reply_msg = f"✅ Вы оплатили занятие по *{req['subject']}* за *{req['price']} ₽*!"
        await bot.api.messages.send(
            peer_id=peer_id,
            message=reply_msg,
            random_id=0
        )

        # Уведомление ученика
        reply_msg = f"✅ Занятие по *{req['subject']}* оплачено."
        student_vk_id = get_student_by_tgid(req['user_id'])['vk_id']
        if student_vk_id:
            try:
                await bot.api.messages.send(
                    peer_id=student_vk_id,
                    message=reply_msg,
                    random_id=0
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить ученика {req['user_id']}: {e}")

    if cmd.startswith("payCancel_"):
        try:
            payment_id = int(cmd.replace("payCancel_", ""))
        except ValueError:
            return

        req = next((r for r in get_active_payment_requests() if r["id"] == payment_id), None)
        if not req:
            await bot.api.messages.send_message_event_answer(
                event_id=event.object.event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=ShowSnackbarEvent(text="❌ Платёж не найден").model_dump_json(),
            )
            return

        update_payment_status(payment_id, "CANCEL")
        logger.info(f"Платёж отменён: {req}")

        await bot.api.messages.send_message_event_answer(
            event_id=event.object.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=ShowSnackbarEvent(text=f"❌ Отменено: {req['subject']}").model_dump_json(),
        )

    if cmd.startswith("payDelay_"):
        try:
            payment_id = int(cmd.replace("payDelay_", ""))
        except ValueError:
            return

        req = next((r for r in get_active_payment_requests() if r["id"] == payment_id), None)
        if not req:
            await bot.api.messages.send_message_event_answer(
                event_id=event.object.event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=ShowSnackbarEvent(text="❌ Платёж не найден").model_dump_json(),
            )
            return

        logger.info(f"Платёж отложен: {req}")

        await bot.api.messages.send_message_event_answer(
            event_id=event.object.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=ShowSnackbarEvent(text=f"🕒 Отложено: {req['subject']}").model_dump_json(),
        )

# Главное меню
@bot.on.message(text=["Меню", "назад", "отмена"])
async def main_menu(message: BotMessage):
    await message.answer("Выберите действие:", keyboard=get_main_keyboard())

# Занятия
@bot.on.message(text="Занятия")
async def send_study(message: BotMessage):

    logger.info(f"Пользователь {message.from_id} запросил список занятий")
    msg_text, buttons = command_list_of_study(message.from_id)
    try:
        user = await bot.api.users.get(message.from_id)
        first_name = user[0].first_name
    except (KeyError, IndexError, Exception):
        first_name = "Пользователь"
    reply_msg = f"{first_name}, {msg_text}"

    keyboard = Keyboard()
    for i, btn in enumerate(buttons):
        if i % 2 == 0 and i != 0:
            keyboard.row()
        keyboard.add(Text(btn['text']), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text("Назад"), color=KeyboardButtonColor.NEGATIVE)

    await message.answer(reply_msg, keyboard=keyboard.get_json())

# Платежи
@bot.on.message(text="Платежи")
async def send_payments(message: BotMessage):
    if message.from_id not in PAY_LIST:
        logger.warning(f"Пользователь {message.from_id} пытается получить доступ к платежам")
        await message.answer("❌ Доступ ограничен.")
        return

    logger.info(f"Пользователь {message.from_id} запросил список платежей")
    requests = get_active_payment_requests()
    if not requests:
        await message.answer("✅ Все оплачено!")
        return

    lines = ["⚠ Неоплаченные занятия:"]
    for i, r in enumerate(requests, 1):
        lines.append(f"{i}. {r['date']} — {r['subject']} ({r['first_name']})")
    await message.answer("\n".join(lines))

    keyboard = Keyboard(one_time=True)
    for req in requests:
        keyboard.add_row()
        keyboard.add_button(Text(f"pay_{req['id']}"), color="positive")
    keyboard.add_row()
    keyboard.add_button(Text("Назад"), color="negative")
    await message.answer("Выберите для обработки:", keyboard=keyboard.get_json())
    await bot.state_dispenser.set(message.peer_id, "awaiting_payment_action")

# Приветствие / Реакция на любую неизвестную команду
@bot.on.message()
async def send_welcome(message: BotMessage):
    logger.info(f"Пользователь {message.from_id} отправил: {message.text}")
    await message.answer(
        "Привет! Я помогаю с оплатой услуг репетиторов.\nНабери 'Меню' для просмотра стартовых команд",
    )

# --- Запуск ---
if __name__ == "__main__":
    logger.info("VK-бот запущен. Ожидание сообщений...")
    bot.run_forever()