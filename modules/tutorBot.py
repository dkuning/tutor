import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
from dotenv import load_dotenv
import study
from datetime import datetime
from modules.storage import init_db, add_payment_request, get_active_payment_requests, update_payment_status, get_subject, get_tutor, get_schedule_for_student, get_payment_by_id

# Загружаем переменные из .env
load_dotenv()

# Создаём папку logs, если её нет
LOG_DIR = '../logs'
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'tutorBot.log')

# Настройка логирования
logger = logging.getLogger('tutorBot')
logger.setLevel(logging.INFO)

# Проверяем, есть ли уже обработчики
if not logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# Токен бота
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не задана переменная окружения TELEGRAM_BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

# Инициализация базы данных при запуске
init_db()

# Получаем белый список пользователей из .env
USER_WHITE_LIST_STR = os.environ.get("USER_WHITE_LIST", "")
USER_WHITE_LIST = []
if USER_WHITE_LIST_STR:
    try:
        USER_WHITE_LIST = [int(uid.strip()) for uid in USER_WHITE_LIST_STR.split(",") if uid.strip().isdigit()]
        logger.info(f"Белый список пользователей: {USER_WHITE_LIST}")
    except ValueError:
        logger.error("Некорректные данные в USER_WHITE_LIST. Должны быть числа, разделённые запятыми.")

PAY_LIST_STR = os.environ.get("PAY_LIST", "")
PAY_LIST = []
if PAY_LIST_STR:
    try:
        PAY_LIST = [int(uid.strip()) for uid in PAY_LIST_STR.split(",") if uid.strip().isdigit()]
        logger.info(f"Список родителей: {PAY_LIST}")
    except ValueError:
        logger.error("Некорректные данные в PAY_LIST. Должны быть числа, разделённые запятыми.")

# Обработчик доступа по белому списку ДОЛЖЕН быть первым в обработчиках!
@bot.message_handler(func=lambda message: message.chat.id not in USER_WHITE_LIST)
def access_msg(message):
    logger.info(f"Пользователь {message.from_user.id} отправил команду: {message.text}")
    bot.send_message(message.chat.id, '❌ Доступ ограничен. Обратитесь к администратору бота.')

# Обработчик команд /start и /help
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    logger.info(f"Пользователь {message.from_user.id} отправил команду: {message.text}")
    bot.send_message(message.chat.id, "Привет! Я помогаю тебе с оплатой услуг репетиторов.")

@bot.message_handler(commands=['study'])
def send_study(message):
    logger.info(f"Пользователь {message.from_user.id} отправил команду: {message.text}")
    msg_text, buttons = study.command_list_of_study(message.from_user.id)
    reply_message = message.from_user.first_name + ", " + msg_text
    markup = create_inline_keyboard(buttons)
    bot.send_message(message.chat.id, reply_message, reply_markup=markup)

@bot.message_handler(commands=['pay'])
def send_pay(message):
    if message.from_user.id not in PAY_LIST:
        logger.warning(f"Пользователю {message.from_user.id} запрещен доступ к команде /pay")
        bot.send_message(message.chat.id, '❌ Доступ к этой команде ограничен.')
        return

    logger.info(f"Пользователь {message.from_user.id} запросил список платежей")

    payment_requests = get_active_payment_requests()
    if not payment_requests:
        bot.send_message(message.chat.id, "Все оплачено! 🎉")
        return

    lines = ["Неоплаченные занятия:"]
    for i, req in enumerate(payment_requests, 1):
        lines.append(f"{i}. {req['date']} — {req['subject']} ({req['first_name']})")
    payment_text = "\n".join(lines)
    bot.send_message(message.chat.id, payment_text)

    buttons = []
    for req in payment_requests:
        text = f"Оплатить: {req['subject']} ({req['first_name']})"
        callback_data = f"pay_{req['id']}"
        buttons.append({'text': text, 'callback_data': callback_data})

    markup = create_inline_keyboard(buttons)
    bot.send_message(message.chat.id, "Выберите, что хотите оплатить", reply_markup=markup)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    logger.info(f"Пользователь {message.from_user.id} отправил сообщение: {message.text}")
    bot.send_message(message.chat.id, "Сообщение получено, но не обрабатывается.")

# Конструктор кнопок
def create_inline_keyboard(buttons):
    markup = InlineKeyboardMarkup()
    for btn in buttons:
        markup.add(InlineKeyboardButton(btn['text'], callback_data=btn['callback_data']))
    return markup

# Очистка кнопок в сообщении
def edit_message_reply_markup(chat_id, message_id):
    try:
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None
        )
    except Exception as e:
        logger.error(f"Ошибка при очистке кнопок в сообщении: {e}")

# Обработчик выбора предмета
@bot.callback_query_handler(func=lambda call: call.data.startswith('subject_'))
def handle_study_selection(call):
    logger.info(f"Пользователь {call.from_user.id} выбрал предмет: {call.data}")
    try:
        subject_id = int(call.data.replace('subject_', ''))
    except ValueError:
        bot.send_message(call.message.chat.id, "❌ Некорректный идентификатор предмета.")
        return

    bot.answer_callback_query(call.id, text=f"Выбран предмет ID: {subject_id}")
    edit_message_reply_markup(call.message.chat.id, call.message.message_id)

    # Получаем предмет по ID
    subject = get_subject(subject_id)
    if not subject:
        bot.send_message(call.message.chat.id, "❌ Предмет не найден.")
        return

    # Получаем расписание студента
    schedule = get_schedule_for_student(call.from_user.id)
    item = next((s for s in schedule if s['subject_id'] == subject_id), None)
    if not item:
        item = next((s for s in get_schedule_for_student(None) if s['subject_id'] == subject_id), None)
    if not item:
        bot.send_message(call.message.chat.id, "❌ Не удалось найти информацию о предмете.")
        return

    tutor = get_tutor(item['tutor_id'])
    price = item['price']

    # Формируем событие оплаты
    payment_event = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'user_id': call.from_user.id,
        'username': call.from_user.username,
        'first_name': call.from_user.first_name,
        'subject_id': subject_id,
        'tutor_id': tutor['tutor_id'],
        'price': price
    }

    # Сохраняем в БД
    payment_event_result = add_payment_request(payment_event)
    logger.info(f"Событие оплаты добавлено в БД: {get_payment_by_id(payment_event_result)}")

    bot.send_message(call.message.chat.id, f"📝 Отлично! Ты выбрал: *{subject['name']}*", parse_mode='Markdown')
    bot.send_message(call.message.chat.id, f"💰 Стоимость занятия: *{price} ₽*", parse_mode='Markdown')
    bot.send_message(call.message.chat.id, "Отправляем сообщение родителям — Папа, Мама, оплатите репетитора! 😉")

    for parent in PAY_LIST:
        if parent != call.from_user.id:
            try:
                bot.send_message(parent, f"👤 {call.from_user.first_name} выбрал занятие по предмету: *{subject['name']}*. Стоимость занятия: *{price} ₽*", parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения родителю {parent}: {e}")

# Обработчик оплаты - детали
@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
def handle_payment_details(call):
    edit_message_reply_markup(call.message.chat.id, call.message.message_id)

    payment_id = int(call.data.replace('pay_', ''))
    req = next((r for r in get_active_payment_requests() if r['id'] == payment_id), None)

    if not req:
        bot.answer_callback_query(call.id, text="Ошибка: платёж не найден или уже обработан")
        return

    tutor = get_tutor(req['tutor_id'])

    reply_message = (
        f"📄 *Детали оплаты*\n\n"
        f"📚 Предмет: *{req['subject']}*\n"
        f"🎓 Репетитор: {tutor['name']}\n"
        f"🏦 Банк: {tutor['bank']}\n"
        f"💰 Сумма: {req['price']} ₽\n\n"
        f"Выберите действие:"
    )

    buttons = [
        {'text': '✅ Подтвердить оплату', 'callback_data': f"payConfirm_{payment_id}"},
        {'text': '🕒 Оплатить позже', 'callback_data': f"payDelay_{payment_id}"},
        {'text': '❌ Отклонить оплату', 'callback_data': f"payCancel_{payment_id}"}
    ]
    markup = create_inline_keyboard(buttons)

    bot.send_message(call.message.chat.id, reply_message, parse_mode='Markdown', reply_markup=markup)

# Подтверждение оплаты
@bot.callback_query_handler(func=lambda call: call.data.startswith('payConfirm_'))
def handle_payment_confirm(call):
    edit_message_reply_markup(call.message.chat.id, call.message.message_id)
    payment_id = int(call.data.replace('payConfirm_', ''))
    req = next((r for r in get_active_payment_requests() if r['id'] == payment_id), None)

    if req:
        update_payment_status(payment_id, 'COMPLETE')
        payment_result = get_payment_by_id (payment_id)
        logger.info(f"Платёж подтверждён: {payment_result}")

        bot.answer_callback_query(call.id, text=f"Оплачено: {req['subject']}")
        bot.send_message(call.message.chat.id, f"✅ Вы оплатили занятие по *{req['subject']}* за *{req['price']} ₽*!", parse_mode='Markdown')
        bot.send_message(req['user_id'], f"✅ Занятие по *{req['subject']}* оплачено.", parse_mode='Markdown')

    else:
        bot.answer_callback_query(call.id, text="Ошибка: платёж не найден или уже обработан")

# Отмена оплаты
@bot.callback_query_handler(func=lambda call: call.data.startswith('payCancel_'))
def handle_payment_cancel(call):
    edit_message_reply_markup(call.message.chat.id, call.message.message_id)
    payment_id = int(call.data.replace('payCancel_', ''))
    req = next((r for r in get_active_payment_requests() if r['id'] == payment_id), None)

    if req:
        bot.answer_callback_query(call.id, text=f"Отменён платёж: {req['subject']}")
        bot.send_message(call.message.chat.id, f"❌ Платёж за *{req['subject']}* отменён.", parse_mode='Markdown')
        update_payment_status(payment_id, 'CANCEL')
        logger.info(f"Платёж отменён: {req}")
    else:
        bot.answer_callback_query(call.id, text="Ошибка: платёж не найден или уже обработан")

# Отложить оплату
@bot.callback_query_handler(func=lambda call: call.data.startswith('payDelay_'))
def handle_payment_delay(call):
    edit_message_reply_markup(call.message.chat.id, call.message.message_id)
    payment_id = int(call.data.replace('payDelay_', ''))
    req = next((r for r in get_active_payment_requests() if r['id'] == payment_id), None)

    if req:
        bot.answer_callback_query(call.id, text=f"Отложено: {req['subject']}")
        bot.send_message(call.message.chat.id, f"🕒 Платёж за *{req['subject']}* отложен.", parse_mode='Markdown')
        logger.info(f"Платёж отложен: {req}")
    else:
        bot.answer_callback_query(call.id, text="Ошибка: платёж не найден или уже обработан")

if __name__ == '__main__':
    logger.info("Telegram-бот запущен. Ожидание сообщений...")
    bot.polling(none_stop=True)