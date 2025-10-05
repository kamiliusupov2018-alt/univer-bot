import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
import datetime
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    logging.error("BOT_TOKEN не установлен!")
    exit(1)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('univer.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS homeworks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER,
            task_text TEXT,
            deadline DATE,
            file_id TEXT,
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT,
            subject_id INTEGER,
            time TEXT,
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )
    ''')
    
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Расписание", callback_data="schedule")],
        [InlineKeyboardButton("📚 Домашние задания", callback_data="homeworks")],
        [InlineKeyboardButton("➕ Добавить предмет", callback_data="add_subject")],
        [InlineKeyboardButton("📝 Добавить домашку", callback_data="add_homework")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Привет! Я бот-помощник для учебного расписания и дедлайнов.\nВыберите действие:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "homeworks":
        await show_homeworks(query, context)
    elif query.data == "schedule":
        await show_schedule(query, context)
    elif query.data == "add_subject":
        await add_subject_handler(query, context)
    elif query.data == "add_homework":
        await add_homework_handler(query, context)
    elif query.data.startswith("subject_"):
        subject_id = int(query.data.split("_")[1])
        context.user_data['selected_subject'] = subject_id
        await query.edit_message_text(
            "Теперь отправьте описание задания и дату дедлайна в формате:\n"
            "Описание задания\nДД.ММ.ГГГГ\n\nНапример:\nРешить задачи 1-5 по математике\n25.12.2024"
        )

async def show_homeworks(query, context):
    conn = sqlite3.connect('univer.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT h.id, s.name, h.task_text, h.deadline, h.file_id
        FROM homeworks h
        JOIN subjects s ON h.subject_id = s.id
        ORDER BY h.deadline
    ''')
    
    homeworks = cursor.fetchall()
    conn.close()
    
    if not homeworks:
        await query.edit_message_text("Нет активных домашних заданий")
        return
    
    text = "📚 Активные домашние задания:\n\n"
    for hw in homeworks:
        try:
            deadline_date = datetime.datetime.strptime(hw[3], '%Y-%m-%d').date()
            days_left = (deadline_date - datetime.date.today()).days
            status = "✅" if days_left < 0 else "⏰"
            text += f"{status} {hw[1]}\n"
            text += f"📝 {hw[2]}\n"
            text += f"📅 Дедлайн: {hw[3]} ({days_left} дней)\n\n"
        except:
            continue
    
    await query.edit_message_text(text)

async def show_schedule(query, context):
    conn = sqlite3.connect('univer.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.day, sub.name, s.time
        FROM schedule s
        JOIN subjects sub ON s.subject_id = sub.id
        ORDER BY 
            CASE s.day
                WHEN 'понедельник' THEN 1
                WHEN 'вторник' THEN 2
                WHEN 'среда' THEN 3
                WHEN 'четверг' THEN 4
                WHEN 'пятница' THEN 5
                WHEN 'суббота' THEN 6
                ELSE 7
            END,
            s.time
    ''')
    
    schedule = cursor.fetchall()
    conn.close()
    
    if not schedule:
        await query.edit_message_text("Расписание не заполнено. Используйте команды для добавления.")
        return
    
    text = "📅 Расписание на неделю:\n\n"
    current_day = ""
    for lesson in schedule:
        if lesson[0] != current_day:
            current_day = lesson[0]
            text += f"\n📌 {current_day.capitalize()}:\n"
        text += f"🕒 {lesson[2]} - {lesson[1]}\n"
    
    await query.edit_message_text(text)

async def add_subject_handler(query, context):
    context.user_data['awaiting_subject'] = True
    await query.edit_message_text("Введите название предмета:")

async def add_homework_handler(query, context):
    conn = sqlite3.connect('univer.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name FROM subjects")
    subjects = cursor.fetchall()
    conn.close()
    
    if not subjects:
        await query.edit_message_text("Сначала добавьте предметы через кнопку 'Добавить предмет'")
        return
    
    keyboard = []
    for subject in subjects:
        keyboard.append([InlineKeyboardButton(subject[1], callback_data=f"subject_{subject[0]}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите предмет для домашнего задания:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    
    if user_data.get('awaiting_subject'):
        subject_name = update.message.text
        
        conn = sqlite3.connect('univer.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO subjects (name) VALUES (?)", (subject_name,))
        conn.commit()
        conn.close()
        
        user_data['awaiting_subject'] = False
        await update.message.reply_text(f"✅ Предмет '{subject_name}' успешно добавлен!")
        
    elif user_data.get('selected_subject'):
        text = update.message.text
        lines = text.split('\n')
        
        if len(lines) >= 2:
            task_text = lines[0]
            deadline_str = lines[1].strip()
            
            try:
                deadline = datetime.datetime.strptime(deadline_str, '%d.%m.%Y').date()
                
                conn = sqlite3.connect('univer.db')
                cursor = conn.cursor()
                
                # Получаем название предмета для сообщения
                cursor.execute("SELECT name FROM subjects WHERE id = ?", (user_data['selected_subject'],))
                subject_name = cursor.fetchone()[0]
                
                cursor.execute(
                    "INSERT INTO homeworks (subject_id, task_text, deadline) VALUES (?, ?, ?)",
                    (user_data['selected_subject'], task_text, deadline)
                )
                conn.commit()
                conn.close()
                
                await update.message.reply_text(
                    f"✅ Домашнее задание добавлено!\n"
                    f"📖 Предмет: {subject_name}\n"
                    f"📝 Задание: {task_text}\n"
                    f"📅 Дедлайн: {deadline_str}"
                )
                
                user_data['selected_subject'] = None
                
            except ValueError:
                await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ (например: 25.12.2024)")
        else:
            await update.message.reply_text("❌ Пожалуйста, отправьте описание и дату в указанном формате")

def main():
    # Инициализация базы данных
    init_db()
    print("База данных инициализирована!")
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    print("Бот запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
