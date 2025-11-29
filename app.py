# app.py
import logging
from flask import Flask, request, render_template, session, redirect, url_for
import pyotp
import os
from modules.storage import get_all_payment_requests

app = Flask(__name__, static_folder='static', template_folder='templates')

app.secret_key = os.environ.get('FLASK_SECRET_KEY')
if not app.secret_key:
    raise ValueError("Не задана переменная окружения FLASK_SECRET_KEY")

TOTP_SECRET = os.environ.get('TOTP_SECRET')
if not TOTP_SECRET:
    raise ValueError("Не задана переменная окружения TOTP_SECRET")

# Настройка логирования
LOG_DIR = './logs'
LOG_FILE = os.path.join(LOG_DIR, 'tutorApp.log')
logger = logging.getLogger('tutorApp')
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
def generate_totp():
    totp = pyotp.TOTP(TOTP_SECRET)
    return totp.now()

def verify_totp(token):
    totp = pyotp.TOTP(TOTP_SECRET)
    return totp.verify(token)

@app.route('/')
def index():
    if not is_logged_in():
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/auth', methods=['POST'])
def auth():
    token = request.form.get('otp')
    if verify_totp(token):
        session['logged_in'] = True
        return redirect(url_for('index'))
    else:
        # Перенаправляем обратно на login с параметром ошибки
        return redirect(url_for('login', error='invalid'))

@app.route('/payments')
def payments():
    if not is_logged_in():
        return redirect(url_for('login'))
    payments_list = get_all_payment_requests()
    return render_template('payments.html', payments=payments_list)


def is_logged_in():
    return session.get('logged_in', False)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
    logger.info(f"Приложение запущено на порту {port}")