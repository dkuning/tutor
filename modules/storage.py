import sqlite3
import os

# Путь к базе данных
DB_PATH = 'database/tutor_bot.db'

# Создаём папку database, если её нет
os.makedirs('database', exist_ok=True)

def init_db():
    """Создаёт все необходимые таблицы при первом запуске"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Таблица репетиторов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tutors (
                tutor_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                bank TEXT NOT NULL
            )
        ''')

        # Таблица предметов (базовая)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        ''')

        # Таблица расписания: связь предмет-репетитор-цена (для всех или конкретного студента)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,  -- NULL = для всех студентов (дефолт)
                subject_id INTEGER NOT NULL,
                tutor_id TEXT NOT NULL,
                price INTEGER NOT NULL,
                FOREIGN KEY (subject_id) REFERENCES subjects (subject_id),
                FOREIGN KEY (tutor_id) REFERENCES tutors (tutor_id),
                UNIQUE(student_id, subject_id)
            )
        ''')

        # Таблица платежей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                tutor_id TEXT NOT NULL,
                price INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'NEW',
                FOREIGN KEY (subject_id) REFERENCES subjects (subject_id),
                FOREIGN KEY (tutor_id) REFERENCES tutors (tutor_id)
            )
        ''')

        # Заполняем начальные данные, если таблицы пустые
        cursor.execute("SELECT COUNT(*) FROM tutors")
        if cursor.fetchone()[0] == 0:
            tutors_data = [
                ('tutor_0', 'Репетитор', '0 (000) 000-00-00', 'Банк'),
            ]
            cursor.executemany("INSERT INTO tutors (tutor_id, name, phone, bank) VALUES (?, ?, ?, ?)", tutors_data)

        cursor.execute("SELECT COUNT(*) FROM subjects")
        if cursor.fetchone()[0] == 0:
            subjects_data = [('Предмет',),]
            cursor.executemany("INSERT INTO subjects (name) VALUES (?)", subjects_data)

        cursor.execute("SELECT COUNT(*) FROM schedule WHERE student_id IS NULL")
        if cursor.fetchone()[0] == 0:
            # Дефолтное расписание
            default_schedule = [
                (None, 'Предмет', 'tutor_0', 0),
            ]
            for student_id, subject_name, tutor_id, price in default_schedule:
                cursor.execute("SELECT subject_id FROM subjects WHERE name = ?", (subject_name,))
                subject_id = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO schedule (student_id, subject_id, tutor_id, price) VALUES (?, ?, ?, ?)",
                    (student_id, subject_id, tutor_id, price)
                )

        conn.commit()

def _insert_schedule_batch(cursor, data):
    """Вспомогательная функция для вставки расписания"""
    for student_id, subject_name, tutor_id, price in data:
        cursor.execute("SELECT subject_id FROM subjects WHERE name = ?", (subject_name,))
        subject_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO schedule (student_id, subject_id, tutor_id, price) VALUES (?, ?, ?, ?)",
            (student_id, subject_id, tutor_id, price)
        )

# === Запросы к БД ===

def get_tutor(tutor_id):
    """Получает репетитора по ID"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tutor_id, name, phone, bank FROM tutors WHERE tutor_id = ?", (tutor_id,))
        row = cursor.fetchone()
        if row:
            cols = ['tutor_id', 'name', 'phone', 'bank']
            return dict(zip(cols, row))
        return {'tutor_id': 'tutor_default', 'name': 'не указан', 'phone': 'не указан', 'bank': 'не указан'}

def get_subject(subject_id):
    """Получает предмет по ID"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT subject_id, name FROM subjects WHERE subject_id = ?", (subject_id,))
        row = cursor.fetchone()
        if row:
            cols = ['subject_id', 'name']
            return dict(zip(cols, row))
        return None

def get_schedule_for_student(student_id):
    """Получает расписание студента: предмет, репетитор, цена"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Сначала индивидуальные предметы
        cursor.execute('''
            SELECT s.subject_id, sub.name, s.tutor_id, s.price
            FROM schedule s
            JOIN subjects sub ON s.subject_id = sub.subject_id
            WHERE s.student_id = ?
            ORDER BY sub.name
        ''', (student_id,))
        rows = cursor.fetchall()
        if rows:
            return [dict(zip(['subject_id', 'name', 'tutor_id', 'price'], r)) for r in rows]

        # Или дефолтное
        cursor.execute('''
            SELECT s.subject_id, sub.name, s.tutor_id, s.price
            FROM schedule s
            JOIN subjects sub ON s.subject_id = sub.subject_id
            WHERE s.student_id IS NULL
            ORDER BY sub.name
        ''')
        rows = cursor.fetchall()
        return [dict(zip(['subject_id', 'name', 'tutor_id', 'price'], r)) for r in rows]

def add_payment_request(payment_event):
    """Добавляет новый запрос на оплату"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO payment_requests 
            (date, user_id, username, first_name, subject_id, tutor_id, price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW')
        ''', (
            payment_event['date'],
            payment_event['user_id'],
            payment_event['username'],
            payment_event['first_name'],
            payment_event['subject_id'],
            payment_event['tutor_id'],
            payment_event['price']
        ))
        conn.commit()
        return cursor.lastrowid

def get_active_payment_requests():
    """Возвращает активные платежи (со статусом 'NEW')"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pr.id, pr.date, pr.user_id, pr.username, pr.first_name, 
                   sub.name as subject, pr.tutor_id, pr.price, pr.status
            FROM payment_requests pr
            JOIN subjects sub ON pr.subject_id = sub.subject_id
            WHERE pr.status = 'NEW'
            ORDER BY pr.date
        ''')
        rows = cursor.fetchall()
        columns = ['id', 'date', 'user_id', 'username', 'first_name', 'subject', 'tutor_id', 'price', 'status']
        return [dict(zip(columns, row)) for row in rows]

def get_all_payment_requests():
    """Возвращает все платежи (все статусы)"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT pr.id, pr.date, pr.user_id, pr.username, pr.first_name, 
                   sub.name as subject, pr.tutor_id, pr.price, pr.status
            FROM payment_requests pr
            JOIN subjects sub ON pr.subject_id = sub.subject_id
            ORDER BY pr.date DESC
        ''')
        rows = cursor.fetchall()
        columns = ['id', 'date', 'user_id', 'username', 'first_name', 'subject', 'tutor_id', 'price', 'status']
        return [dict(zip(columns, row)) for row in rows]

def update_payment_status(payment_id, status):
    """Обновляет статус платежа"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE payment_requests SET status = ? WHERE id = ?', (status, payment_id))
        conn.commit()
        return cursor.rowcount > 0

def get_payment_by_id(payment_id):
    if payment_id:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM payment_requests WHERE id = ?', (payment_id,))
            row = cursor.fetchone()
            if row:
                cols = ['id', 'date', 'user_id', 'username', 'first_name', 'subject_id', 'tutor_id', 'price', 'status']
                return dict(zip(cols, row))
            return None
    else:
        return None