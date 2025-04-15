import telebot
from telebot import types
from sqlalchemy import create_engine, Column, Integer, String, Date, Text, ForeignKey, DateTime, Sequence, BigInteger
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from contextlib import contextmanager
import re
import logging

# Конфигурация
CONFIG = {
    "",
    "",
    ""
}

# Настройка логирования
logging.basicConfig(level=logging.INFO, filename='bot.log', format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота
bot = telebot.TeleBot(CONFIG["TELEGRAM_TOKEN"])

# Базовый класс для моделей
Base = declarative_base()


# Модели БД
class User(Base):
    __tablename__ = 'users'
    user_id = Column(BigInteger, primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    position = Column(String(100))
    department = Column(String(100))
    email = Column(String(100), unique=True, nullable=False)


class Application(Base):
    __tablename__ = 'applications'
    application_id = Column(Integer, Sequence('applications_application_id_seq'), primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    type = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)
    reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Log(Base):
    __tablename__ = 'logs'
    log_id = Column(Integer, Sequence('logs_log_id_seq'), primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    action = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


# Инициализация базы данных
engine = create_engine(CONFIG["DB_URL"])
Base.metadata.create_all(engine)
SessionFactory = sessionmaker(bind=engine)


# Контекстный менеджер для работы с БД
@contextmanager
def db_session():
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка базы данных: {e}")
        raise e
    finally:
        session.close()


# Клавиатуры
class Keyboards:
    @staticmethod
    def main_menu():
        return types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏠 В главное меню")

    @staticmethod
    def action():
        return types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏖️ Отпуск", "🤒 Больничный", "📋 Мои заявки")

    @staticmethod
    def vacation_type():
        return types.ReplyKeyboardMarkup(resize_keyboard=True).add(
            "🌴 Ежегодный основной оплачиваемый",
            "🌞 Ежегодный дополнительный оплачиваемый",
            "🏝️ Без сохранения заработной платы",
            "🏠 В главное меню"
        )


# Утилитные функции
def send_message(chat_id, text, reply_markup=None):
    try:
        msg = bot.send_message(chat_id, text, reply_markup=reply_markup)
        logger.info(f"Сообщение отправлено {chat_id}: {text}")
        return msg
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения {chat_id}: {e}")
        raise


def validate_date(date_str, allow_past=False):
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        if not allow_past and date_obj < datetime.now():
            return False, "Дата в прошлом"
        return True, date_obj
    except ValueError:
        return False, "Неверный формат (ГГГГ-ММ-ДД)"


def validate_email(email):
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email)), "Неверный email" if not re.match(email_pattern, email) else None


def handle_main_menu_return(message, next_step=None, *args):
    if message.text == "🏠 В главное меню":
        back_to_main_menu(message)
        return True
    if next_step:
        bot.register_next_step_handler(message, next_step, *args)
    return False


# Обработчики
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    with db_session() as session:
        user = session.query(User).filter_by(user_id=chat_id).first()
        if user:
            send_message(chat_id, "Вы зарегистрированы", Keyboards.action())
        else:
            send_message(chat_id, "Введите имя:", Keyboards.main_menu())
            bot.register_next_step_handler(message, register_first_name)


@bot.message_handler(func=lambda m: m.text == "🏠 В главное меню")
def back_to_main_menu(message):
    chat_id = message.chat.id
    with db_session() as session:
        user = session.query(User).filter_by(user_id=chat_id).first()
        send_message(chat_id, "Выберите действие:", Keyboards.action() if user else Keyboards.main_menu())


@bot.message_handler(func=lambda m: m.text == "🏖️ Отпуск")
def handle_vacation(message):
    chat_id = message.chat.id
    with db_session() as session:
        user = session.query(User).filter_by(user_id=chat_id).first()
        if not user:
            send_message(chat_id, "Сначала зарегистрируйтесь с помощью /start")
            return
    send_message(chat_id, "Тип отпуска:", Keyboards.vacation_type())


@bot.message_handler(func=lambda m: m.text == "🤒 Больничный")
def handle_sick_leave(message):
    chat_id = message.chat.id
    with db_session() as session:
        user = session.query(User).filter_by(user_id=chat_id).first()
        if not user:
            send_message(chat_id, "Сначала зарегистрируйтесь с помощью /start")
            return
    send_message(chat_id, "Дата начала (ГГГГ-ММ-ДД):", Keyboards.main_menu())
    bot.register_next_step_handler(message, application_start_date, "больничный")


@bot.message_handler(func=lambda m: m.text == "📋 Мои заявки")
def handle_my_applications(message):
    chat_id = message.chat.id
    with db_session() as session:
        user = session.query(User).filter_by(user_id=chat_id).first()
        if not user:
            send_message(chat_id, "Сначала зарегистрируйтесь с помощью /start")
            return
        apps = session.query(Application).filter_by(user_id=chat_id).order_by(Application.application_id.desc()).all()
        if not apps:
            send_message(chat_id, "У вас нет заявок", Keyboards.action())
            return
        markup = types.InlineKeyboardMarkup()
        for app in apps:
            btn_text = f"#{app.application_id} ({app.type}, {app.status})"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"view_{app.application_id}"))
        send_message(chat_id, "Ваши заявки:", markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("view_"))
def view_application(call):
    chat_id = call.message.chat.id
    app_id = int(call.data.split("_")[1])
    with db_session() as session:
        app = session.query(Application).filter_by(application_id=app_id, user_id=chat_id).first()
        if app:
            text = (f"Заявка #{app.application_id}\n"
                    f"Тип: {app.type}\n"
                    f"С: {app.start_date}\n"
                    f"По: {app.end_date}\n"
                    f"Статус: {app.status}\n"
                    f"Причина: {app.reason or 'Не указана'}")
            markup = types.InlineKeyboardMarkup()
            if app.status == "на рассмотрении":
                markup.add(types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{app_id}"))
            send_message(chat_id, text, markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
def edit_application(call):
    chat_id = call.message.chat.id
    app_id = int(call.data.split("_")[1])
    with db_session() as session:
        app = session.query(Application).filter_by(application_id=app_id, user_id=chat_id).first()
        if app and app.status == "на рассмотрении":
            send_message(chat_id, "Новая дата начала (ГГГГ-ММ-ДД):", Keyboards.main_menu())
            bot.register_next_step_handler(call.message, edit_application_start_date, app_id)


def edit_application_start_date(message, app_id):
    chat_id = message.chat.id
    if handle_main_menu_return(message):
        return
    is_valid, result = validate_date(message.text)
    if not is_valid:
        send_message(chat_id, f"❌ {result}", Keyboards.main_menu())
        handle_main_menu_return(message, edit_application_start_date, app_id)
        return
    send_message(chat_id, "Новая дата окончания (ГГГГ-ММ-ДД):", Keyboards.main_menu())
    bot.register_next_step_handler(message, edit_application_end_date, app_id, result)


def edit_application_end_date(message, app_id, start_date):
    chat_id = message.chat.id
    if handle_main_menu_return(message):
        return
    is_valid, result = validate_date(message.text)
    if not is_valid or result < start_date:
        send_message(chat_id, f"❌ {result if not is_valid else 'Конец раньше начала'}", Keyboards.main_menu())
        handle_main_menu_return(message, edit_application_end_date, app_id, start_date)
        return
    send_message(chat_id, "Новая причина:", Keyboards.main_menu())
    bot.register_next_step_handler(message, edit_application_reason, app_id, start_date, result)


def edit_application_reason(message, app_id, start_date, end_date):
    chat_id = message.chat.id
    if handle_main_menu_return(message):
        return
    with db_session() as session:
        app = session.query(Application).filter_by(application_id=app_id, user_id=chat_id).first()
        if app and app.status == "на рассмотрении":
            app.start_date = start_date.date()
            app.end_date = end_date.date()
            app.reason = message.text
            app.updated_at = datetime.utcnow()
            session.add(Log(user_id=chat_id, action=f"Редактирование заявки #{app_id}"))
            send_message(chat_id, "✅ Заявка обновлена", Keyboards.action())
            send_message(CONFIG["HR_CHAT_ID"],
                         f"Заявка #{app_id} от {chat_id} обновлена: {app.type} с {app.start_date} по {app.end_date}. Причина: {app.reason}")


@bot.message_handler(
    func=lambda m: m.text in ["🌴 Ежегодный основной оплачиваемый", "🌞 Ежегодный дополнительный оплачиваемый",
                              "🏝️ Без сохранения заработной платы"])
def handle_vacation_type(message):
    vacation_types = {
        "🌴 Ежегодный основной оплачиваемый": "ежегодный основной оплачиваемый",
        "🌞 Ежегодный дополнительный оплачиваемый": "ежегодный дополнительный оплачиваемый",
        "🏝️ Без сохранения заработной платы": "без сохранения заработной платы"
    }
    app_type = vacation_types[message.text]
    send_message(message.chat.id, "Дата начала (ГГГГ-ММ-ДД):", Keyboards.main_menu())
    bot.register_next_step_handler(message, application_start_date, app_type)


# Регистрация
def register_first_name(message):
    if handle_main_menu_return(message):
        return
    send_message(message.chat.id, "Фамилия:", Keyboards.main_menu())
    bot.register_next_step_handler(message, register_last_name, message.text)


def register_last_name(message, first_name):
    if handle_main_menu_return(message):
        return
    send_message(message.chat.id, "Должность:", Keyboards.main_menu())
    bot.register_next_step_handler(message, register_position, first_name, message.text)


def register_position(message, first_name, last_name):
    if handle_main_menu_return(message):
        return
    send_message(message.chat.id, "Подразделение:", Keyboards.main_menu())
    bot.register_next_step_handler(message, register_department, first_name, last_name, message.text)


def register_department(message, first_name, last_name, position):
    if handle_main_menu_return(message):
        return
    send_message(message.chat.id, "Email:", Keyboards.main_menu())
    bot.register_next_step_handler(message, register_email, first_name, last_name, position, message.text)


def register_email(message, first_name, last_name, position, department):
    chat_id = message.chat.id
    if handle_main_menu_return(message):
        return
    is_valid, error = validate_email(message.text)
    if not is_valid:
        send_message(chat_id, f"❌ {error}", Keyboards.main_menu())
        bot.register_next_step_handler(message, register_email, first_name, last_name, position, department)
        return
    with db_session() as session:
        try:
            # Проверяем, существует ли пользователь с таким email
            existing_user = session.query(User).filter_by(email=message.text).first()
            if existing_user:
                send_message(chat_id, "❌ Этот email уже зарегистрирован", Keyboards.main_menu())
                logger.warning(f"Попытка регистрации с занятым email: {message.text} для chat_id {chat_id}")
                bot.register_next_step_handler(message, register_email, first_name, last_name, position, department)
                return

            # Создаем нового пользователя
            new_user = User(
                user_id=chat_id,
                first_name=first_name,
                last_name=last_name,
                position=position,
                department=department,
                email=message.text
            )
            session.add(new_user)
            session.flush()  # Принудительно записываем изменения

            # Логируем действие
            session.add(Log(user_id=chat_id, action="Регистрация пользователя"))
            session.flush()  # Убеждаемся, что лог тоже записан

            # Проверяем, что пользователь действительно сохранен
            saved_user = session.query(User).filter_by(user_id=chat_id).first()
            if not saved_user:
                raise Exception("Пользователь не был сохранен в базе данных")

            logger.info(f"Пользователь {chat_id} успешно зарегистрирован: {first_name} {last_name}, {message.text}")
            send_message(chat_id, "✅ Регистрация завершена", Keyboards.action())
        except Exception as e:
            logger.error(f"Ошибка при регистрации пользователя {chat_id}: {str(e)}")
            send_message(chat_id, f"❌ Ошибка регистрации: {str(e)}. Попробуйте снова с /start", Keyboards.main_menu())


# Подача заявки
def application_start_date(message, app_type):
    chat_id = message.chat.id
    if handle_main_menu_return(message):
        return
    is_valid, result = validate_date(message.text)
    if not is_valid:
        send_message(chat_id, f"❌ {result}", Keyboards.main_menu())
        handle_main_menu_return(message, application_start_date, app_type)
        return
    send_message(chat_id, "Дата окончания (ГГГГ-ММ-ДД):", Keyboards.main_menu())
    bot.register_next_step_handler(message, application_end_date, app_type, result)


def application_end_date(message, app_type, start_date):
    chat_id = message.chat.id
    if handle_main_menu_return(message):
        return
    is_valid, result = validate_date(message.text)
    if not is_valid or result < start_date:
        send_message(chat_id, f"❌ {result if not is_valid else 'Конец раньше начала'}", Keyboards.main_menu())
        handle_main_menu_return(message, application_end_date, app_type, start_date)
        return
    send_message(chat_id, "Причина:", Keyboards.main_menu())
    bot.register_next_step_handler(message, application_reason, app_type, start_date, result)


def application_reason(message, app_type, start_date, end_date):
    chat_id = message.chat.id
    if handle_main_menu_return(message):
        return
    with db_session() as session:
        app = Application(user_id=chat_id, start_date=start_date.date(), end_date=end_date.date(),
                          type=app_type, status="на рассмотрении", reason=message.text)
        session.add(app)
        session.flush()
        app_id = app.application_id
        session.add(Log(user_id=chat_id, action=f"Подача заявки #{app_id}"))
        send_message(CONFIG["HR_CHAT_ID"],
                     f"Заявка #{app_id} от {chat_id}: {app_type} с {start_date.date()} по {end_date.date()}. Причина: {message.text}")
        send_message(chat_id, "✅ Заявка подана", Keyboards.action())


# Запуск бота
if __name__ == "__main__":
    try:
        logger.info("Запуск бота...")
        bot.polling(none_stop=True, timeout=20)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
        engine.dispose()
    except Exception as e:
        logger.error(f"Критическая ошибка бота: {str(e)}")
        engine.dispose()