from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QMessageBox, QDateEdit, QFileDialog,
    QLabel, QScrollArea, QComboBox, QInputDialog, QDialog
)
from PySide6.QtCore import Qt, QDate
from sqlalchemy import create_engine, Column, Integer, String, Date, Text, ForeignKey, DateTime, Sequence, BigInteger
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import io
import os
import logging
from logging.handlers import RotatingFileHandler
from telebot import TeleBot

# Конфигурация
CONFIG = {
    "DB_URL": "",
    "TELEGRAM_TOKEN": ""
}

# Настройка логирования с ротацией
handler = RotatingFileHandler('admin_panel.log', maxBytes=10*1024*1024, backupCount=5)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[handler])
logger = logging.getLogger(__name__)

# Инициализация Telegram-бота только для отправки сообщений
bot = TeleBot(CONFIG["TELEGRAM_TOKEN"], threaded=False)

# Базовый класс для моделей
Base = declarative_base()

# Константы для статусов
class ApplicationStatus:
    PENDING = "на рассмотрении"
    APPROVED = "одобрена"
    REJECTED = "отклонена"

# Централизованные стили
STYLES = {
    "nav_button": """
        QPushButton {
            padding: 8px;
            font-size: 12px;
            background-color: #f0f0f0;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
        }
        QPushButton:pressed {
            background-color: #d0d0d0;
        }
    """,
    "card": """
        QWidget {
            padding: 2px;
            border-bottom: 1px solid #ddd;
            background-color: #fafafa;
            margin: 0px;
        }
    """,
    "label": """
        QLabel {
            padding: 0px;
            margin: 0px;
        }
    """,
    "approve_button": """
        QPushButton {
            background-color: #4CAF50;
            color: white;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
    """,
    "reject_button": """
        QPushButton {
            background-color: #f44336;
            color: white;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #da190b;
        }
    """,
    "action_button": """
        QPushButton {
            padding: 8px;
            font-size: 12px;
            margin: 0px;
        }
    """
}

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
engine = create_engine(CONFIG["DB_URL"], pool_size=5, max_overflow=10)
Base.metadata.create_all(engine)
SessionFactory = sessionmaker(bind=engine)

# Функция уведомления пользователя через Telegram
def notify_user(app_id, status):
    session = SessionFactory()
    try:
        app = session.query(Application).filter_by(application_id=app_id).first()
        if app:
            status_text = "одобрена" if status == ApplicationStatus.APPROVED else "отклонена"
            try:
                bot.send_message(app.user_id, f"Ваша заявка #{app_id} {status_text}!")
                session.add(Log(user_id=app.user_id, action=f"Уведомление о статусе заявки #{app_id}: {status_text}"))
                session.commit()
                logger.info(f"Уведомление отправлено пользователю {app.user_id} о статусе заявки #{app_id}: {status_text}")
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление пользователю {app.user_id}: {e}")
                raise
    except Exception as e:
        logger.error(f"Ошибка при обработке уведомления для заявки #{app_id}: {e}")
    finally:
        session.close()

# Главное окно админ-панели
class AdminPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Панель администратора CRM")
        self.setGeometry(100, 100, 800, 600)
        self.session = SessionFactory()
        self.current_page = 1
        self.per_page = 20
        self.init_ui()
        logger.info("Панель администратора инициализирована")

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(2)

        # Навигация
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(5)
        self.btn_users = QPushButton("👤 Пользователи")
        self.btn_applications = QPushButton("📋 Заявки")
        self.btn_history = QPushButton("🕒 История заявок")
        self.btn_reports = QPushButton("📊 Отчеты")
        self.btn_logs = QPushButton("📜 Логи")
        for btn in [self.btn_users, self.btn_applications, self.btn_history, self.btn_reports, self.btn_logs]:
            self.apply_style(btn, "nav_button")
            nav_layout.addWidget(btn)
        main_layout.addLayout(nav_layout)

        # Фильтры
        filter_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по имени, фамилии или ID")
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Все", ApplicationStatus.PENDING, ApplicationStatus.APPROVED, ApplicationStatus.REJECTED])
        self.search_input.textChanged.connect(lambda: self.show_applications(page=1))
        self.status_filter.currentTextChanged.connect(lambda: self.show_applications(page=1))
        filter_layout.addWidget(QLabel("Фильтр:"))
        filter_layout.addWidget(self.search_input)
        filter_layout.addWidget(self.status_filter)
        main_layout.addLayout(filter_layout)

        # Область содержимого
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(1)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setAlignment(Qt.AlignTop)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.content_widget)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; } QWidget { margin: 0px; }")
        main_layout.addWidget(self.scroll)

        # Пагинация
        pagination_layout = QHBoxLayout()
        self.prev_page_btn = QPushButton("⬅️ Предыдущая")
        self.next_page_btn = QPushButton("Следующая ➡️")
        self.page_label = QLabel("Страница 1")
        self.apply_style(self.prev_page_btn, "action_button")
        self.apply_style(self.next_page_btn, "action_button")
        self.apply_style(self.page_label, "label")
        self.prev_page_btn.clicked.connect(self.prev_page)
        self.next_page_btn.clicked.connect(self.next_page)
        pagination_layout.addWidget(self.prev_page_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_page_btn)
        main_layout.addLayout(pagination_layout)

        # Подключение кнопок
        self.btn_users.clicked.connect(lambda: self.show_users(page=1))
        self.btn_applications.clicked.connect(lambda: self.show_applications(page=1))
        self.btn_history.clicked.connect(lambda: self.show_history(page=1))
        self.btn_reports.clicked.connect(self.show_reports)
        self.btn_logs.clicked.connect(lambda: self.show_logs(page=1))
        self.show_applications(page=1)

    def apply_style(self, widget, style_key):
        widget.setStyleSheet(STYLES[style_key])

    def add_header(self, text):
        header = QLabel(f"<b>{text}</b>")
        self.apply_style(header, "label")
        self.content_layout.addWidget(header)

    def clear_content(self):
        logger.info("Очистка контента")
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def log_action(self, user_id, action):
        try:
            self.session.add(Log(user_id=user_id, action=action))
            self.session.commit()
            logger.info(f"Лог: {action}")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Ошибка при записи лога: {e}")

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_content()

    def next_page(self):
        self.current_page += 1
        self.refresh_content()

    def refresh_content(self):
        if self.btn_applications.isDown():
            self.show_applications(self.current_page)
        elif self.btn_users.isDown():
            self.show_users(self.current_page)
        elif self.btn_history.isDown():
            self.show_history(self.current_page)
        elif self.btn_logs.isDown():
            self.show_logs(self.current_page)

    def show_users(self, page=1):
        logger.info(f"Показ пользователей, страница {page}")
        self.current_page = page
        self.clear_content()
        self.add_header("Список пользователей")
        offset = (page - 1) * self.per_page
        users = self.session.query(User).limit(self.per_page).offset(offset).all()
        if not users:
            no_data = QLabel("Нет пользователей")
            self.apply_style(no_data, "label")
            self.content_layout.addWidget(no_data)
        for user in users:
            user_widget = QWidget()
            user_layout = QHBoxLayout(user_widget)
            user_layout.setContentsMargins(0, 0, 0, 0)
            user_info = QLabel(f"ID: {user.user_id} | {user.first_name} {user.last_name} | {user.position or '-'} | {user.department or '-'} | {user.email}")
            edit_btn = QPushButton("✏️ Редактировать")
            delete_btn = QPushButton("🗑️ Удалить")
            edit_btn.clicked.connect(lambda _, u=user.user_id: self.edit_user(u))
            delete_btn.clicked.connect(lambda _, u=user.user_id: self.delete_user(u))
            user_layout.addWidget(user_info)
            user_layout.addStretch()
            user_layout.addWidget(edit_btn)
            user_layout.addWidget(delete_btn)
            self.apply_style(user_widget, "card")
            self.content_layout.addWidget(user_widget)
        self.page_label.setText(f"Страница {page}")

    def show_applications(self, page=1):
        logger.info(f"Показ заявок, страница {page}")
        self.current_page = page
        self.clear_content()
        self.add_header("Заявки")
        offset = (page - 1) * self.per_page
        query = self.session.query(Application, User).join(User)
        search_text = self.search_input.text().lower()
        if search_text:
            query = query.filter(
                (User.first_name.ilike(f"%{search_text}%")) |
                (User.last_name.ilike(f"%{search_text}%")) |
                (Application.application_id == search_text if search_text.isdigit() else False)
            )
        status = self.status_filter.currentText()
        if status != "Все":
            query = query.filter(Application.status == status)
        else:
            query = query.filter(Application.status == ApplicationStatus.PENDING)
        applications = query.limit(self.per_page).offset(offset).all()
        if not applications:
            no_data = QLabel("Нет заявок")
            self.apply_style(no_data, "label")
            self.content_layout.addWidget(no_data)
        for app, user in applications:
            self.add_application_card(app, user, history=(app.status != ApplicationStatus.PENDING))
        self.page_label.setText(f"Страница {page}")

    def show_history(self, page=1):
        logger.info(f"Показ истории заявок, страница {page}")
        self.current_page = page
        self.clear_content()
        self.add_header("История заявок")
        offset = (page - 1) * self.per_page
        apps = self.session.query(Application, User).join(User).filter(
            Application.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REJECTED])
        ).limit(self.per_page).offset(offset).all()
        if not apps:
            no_data = QLabel("История пуста")
            self.apply_style(no_data, "label")
            self.content_layout.addWidget(no_data)
        for app, user in apps:
            self.add_application_card(app, user, history=True)
        self.page_label.setText(f"Страница {page}")

    def format_application_text(self, app, user):
        return (
            f"#{app.application_id} | {user.first_name} {user.last_name} | "
            f"{app.type} | {app.start_date} — {app.end_date} | "
            f"Причина: {app.reason or '-'} | Статус: {app.status}"
        )

    def add_application_card(self, app, user, history=False):
        card_widget = QWidget()
        card_layout = QHBoxLayout(card_widget)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_text = self.format_application_text(app, user)
        card_label = QLabel(card_text)
        card_label.setWordWrap(True)
        if not history:
            approve_btn = QPushButton("✅")
            reject_btn = QPushButton("❌")
            approve_btn.setFixedSize(40, 40)
            reject_btn.setFixedSize(40, 40)
            self.apply_style(approve_btn, "approve_button")
            self.apply_style(reject_btn, "reject_button")
            approve_btn.clicked.connect(lambda: self.approve_application(app.application_id))
            reject_btn.clicked.connect(lambda: self.reject_application(app.application_id))
            card_layout.addWidget(card_label)
            card_layout.addStretch()
            card_layout.addWidget(approve_btn)
            card_layout.addWidget(reject_btn)
        else:
            card_layout.addWidget(card_label)
        self.apply_style(card_widget, "card")
        self.content_layout.addWidget(card_widget)

    def show_reports(self):
        logger.info("Показ отчетов")
        self.clear_content()
        self.add_header("Отчеты")
        report_btns = [
            ("Заявки за период", self.report_applications_period),
            ("Длительность по отделам", self.report_duration_departments),
            ("Заявки сотрудника", self.report_employee_applications)
        ]
        for text, callback in report_btns:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            self.apply_style(btn, "action_button")
            self.content_layout.addWidget(btn)

    def show_logs(self, page=1):
        logger.info(f"Показ логов, страница {page}")
        self.current_page = page
        self.clear_content()
        self.add_header("Логи")
        offset = (page - 1) * self.per_page
        logs = self.session.query(Log).order_by(Log.timestamp.desc()).limit(self.per_page).offset(offset).all()
        if not logs:
            no_data = QLabel("Нет логов")
            self.apply_style(no_data, "label")
            self.content_layout.addWidget(no_data)
        for log in logs:
            user = self.session.query(User).filter_by(user_id=log.user_id).first()
            log_text = f"{log.timestamp.strftime('%Y-%m-%d %H:%M')} | {user.first_name if user else log.user_id} | {log.action}"
            log_label = QLabel(log_text)
            self.apply_style(log_label, "label")
            self.content_layout.addWidget(log_label)
        self.page_label.setText(f"Страница {page}")

    def edit_user(self, user_id):
        logger.info(f"Редактирование пользователя {user_id}")
        user = self.session.query(User).filter_by(user_id=user_id).first()
        dialog = QDialog(self)
        dialog.setWindowTitle("Редактировать пользователя")
        layout = QVBoxLayout(dialog)
        first_name = QLineEdit(user.first_name)
        last_name = QLineEdit(user.last_name)
        position = QLineEdit(user.position or "")
        department = QLineEdit(user.department or "")
        email = QLineEdit(user.email)
        layout.addWidget(QLineEdit(f"ID: {user_id}", readOnly=True))
        layout.addWidget(first_name)
        layout.addWidget(last_name)
        layout.addWidget(position)
        layout.addWidget(department)
        layout.addWidget(email)
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(
            lambda: self.save_user(user_id, first_name.text(), last_name.text(), position.text(), department.text(), email.text(), dialog))
        layout.addWidget(save_btn)
        dialog.setStyleSheet("QWidget { padding: 10px; }")
        dialog.exec()

    def save_user(self, user_id, first_name, last_name, position, department, email, dialog):
        logger.info(f"Сохранение пользователя {user_id}")
        try:
            user = self.session.query(User).filter_by(user_id=user_id).first()
            user.first_name = first_name
            user.last_name = last_name
            user.position = position or None
            user.department = department or None
            user.email = email
            self.log_action(user_id, f"Редактирование данных пользователя администратором")
            self.session.commit()
            dialog.close()
            self.show_users(self.current_page)
        except Exception as e:
            self.session.rollback()
            logger.error(f"Ошибка при сохранении пользователя: {e}")
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить пользователя")

    def delete_user(self, user_id):
        logger.info(f"Удаление пользователя {user_id}")
        reply = QMessageBox.question(self, "Подтверждение", f"Удалить пользователя {user_id}?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            session = SessionFactory()
            try:
                # Удаляем все связанные заявки пользователя
                session.query(Application).filter_by(user_id=user_id).delete()

                # Удаляем все логи пользователя
                session.query(Log).filter_by(user_id=user_id).delete()

                # Удаляем самого пользователя
                user = session.query(User).filter_by(user_id=user_id).first()
                if user:
                    session.delete(user)
                    self.log_action(user_id, "Удаление пользователя администратором")
                    session.commit()
                    QMessageBox.information(self, "Успех", f"Пользователь {user_id} удален")
                else:
                    QMessageBox.warning(self, "Предупреждение", f"Пользователь с ID {user_id} не найден")

                self.show_users(self.current_page)
            except Exception as e:
                session.rollback()
                logger.error(f"Ошибка при удалении пользователя: {e}")
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить пользователя: {str(e)}")
            finally:
                session.close()

    def approve_application(self, app_id):
        logger.info(f"Одобрение заявки #{app_id}")
        try:
            app = self.session.query(Application).filter_by(application_id=app_id).first()
            if app and app.status == ApplicationStatus.PENDING:
                app.status = ApplicationStatus.APPROVED
                self.log_action(app.user_id, f"Одобрение заявки #{app_id} администратором")
                self.session.commit()
                notify_user(app_id, ApplicationStatus.APPROVED)
                QMessageBox.information(self, "Успех", f"Заявка #{app_id} одобрена")
            else:
                logger.warning(f"Заявка #{app_id} не найдена или не в статусе PENDING")
                QMessageBox.warning(self, "Предупреждение", f"Заявка #{app_id} не может быть одобрена")
            self.show_applications(self.current_page)
        except Exception as e:
            self.session.rollback()
            logger.error(f"Ошибка при одобрении заявки #{app_id}: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось одобрить заявку: {str(e)}")

    def reject_application(self, app_id):
        logger.info(f"Отклонение заявки #{app_id}")
        try:
            app = self.session.query(Application).filter_by(application_id=app_id).first()
            if app and app.status == ApplicationStatus.PENDING:
                reason, ok = QInputDialog.getText(self, "Причина отклонения", "Введите причину:")
                if ok:
                    app.status = ApplicationStatus.REJECTED
                    app.reason = f"{app.reason or ''} [Отклонено: {reason}]"
                    self.log_action(app.user_id, f"Отклонение заявки #{app_id} администратором")
                    self.session.commit()
                    notify_user(app_id, ApplicationStatus.REJECTED)
                    QMessageBox.information(self, "Успех", f"Заявка #{app_id} отклонена")
                else:
                    logger.info(f"Отклонение заявки #{app_id} отменено")
                    return
            else:
                logger.warning(f"Заявка #{app_id} не найдена или не в статусе PENDING")
                QMessageBox.warning(self, "Предупреждение", f"Заявка #{app_id} не может быть отклонена")
            self.show_applications(self.current_page)
        except Exception as e:
            self.session.rollback()
            logger.error(f"Ошибка при отклонении заявки #{app_id}: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось отклонить заявку: {str(e)}")

    def report_applications_period(self):
        logger.info("Генерация отчета: Заявки за период")
        dialog = QDialog(self)
        dialog.setWindowTitle("Выберите период")
        layout = QVBoxLayout(dialog)

        start_date_edit = QDateEdit(QDate.currentDate())
        start_date_edit.setCalendarPopup(True)
        start_date_edit.setDisplayFormat("yyyy-MM-dd")
        layout.addWidget(QLabel("Начало периода:"))
        layout.addWidget(start_date_edit)

        end_date_edit = QDateEdit(QDate.currentDate())
        end_date_edit.setCalendarPopup(True)
        end_date_edit.setDisplayFormat("yyyy-MM-dd")
        layout.addWidget(QLabel("Конец периода:"))
        layout.addWidget(end_date_edit)

        button_box = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Отмена")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        button_box.addWidget(ok_btn)
        button_box.addWidget(cancel_btn)
        layout.addLayout(button_box)

        if dialog.exec():
            start_date = start_date_edit.date().toPython()
            end_date = end_date_edit.date().toPython()
            apps = self.session.query(Application).filter(
                Application.start_date >= start_date,
                Application.end_date <= end_date
            ).all()
            if not apps:
                logger.info("Заявки за выбранный период не найдены")
                QMessageBox.information(self, "Информация", "Заявки за выбранный период отсутствуют")
                return
            self.generate_pdf_report("Заявки за период",
                                     [f"#{a.application_id} - {a.type}, {a.start_date} - {a.end_date}, {a.status}" for a in apps])
        else:
            logger.info("Выбор периода отменен")

    def report_duration_departments(self):
        logger.info("Генерация отчета: Длительность по отделам")
        year, ok = QInputDialog.getInt(self, "Год", "Введите год (ГГГГ):")
        if ok:
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31)
            apps = self.session.query(Application).filter(
                Application.start_date >= start_date.date(),
                Application.end_date <= end_date.date()
            ).all()
            dept_duration = {}
            for app in apps:
                user = self.session.query(User).filter_by(user_id=app.user_id).first()
                dept = user.department or "Без отдела"
                days = (app.end_date - app.start_date).days + 1
                dept_duration[dept] = dept_duration.get(dept, 0) + days
            self.generate_pdf_report("Длительность по отделам",
                                     [f"{dept}: {days} дней" for dept, days in dept_duration.items()])
        else:
            logger.info("Ввод года отменен")

    def report_employee_applications(self):
        logger.info("Генерация отчета: Заявки сотрудника")
        user_id, ok = QInputDialog.getInt(self, "ID сотрудника", "Введите ID сотрудника:")
        if ok:
            user = self.session.query(User).filter_by(user_id=user_id).first()
            if not user:
                logger.warning(f"Пользователь с ID {user_id} не найден")
                QMessageBox.warning(self, "Предупреждение", f"Пользователь с ID {user_id} не найден")
                return
            apps = self.session.query(Application).filter_by(user_id=user_id).all()
            if not apps:
                logger.info(f"Заявки для пользователя {user_id} не найдены")
                QMessageBox.information(self, "Информация", f"Заявки для {user.first_name} {user.last_name} отсутствуют")
                return
            title = f"Заявки сотрудника {user.first_name} {user.last_name}"
            self.generate_pdf_report(title,
                                     [f"#{a.application_id} - {a.type}, {a.start_date} - {a.end_date}, {a.status}" for a in apps])
        else:
            logger.info("Ввод ID сотрудника отменен")

    def generate_pdf_report(self, title, content_lines):
        logger.info(f"Генерация PDF отчета: {title}")
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            import os

            # 1. Настройка шрифтов
            try:
                # Проверяем наличие шрифта в разных местах
                font_paths = [
                    "DejaVuSans.ttf",  # Текущая директория
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
                    "C:/Windows/Fonts/DejaVuSans.ttf"  # Windows
                ]

                found_font = None
                for path in font_paths:
                    if os.path.exists(path):
                        found_font = path
                        break

                if not found_font:
                    raise FileNotFoundError("Шрифт DejaVuSans.ttf не найден")

                # Регистрируем шрифты
                pdfmetrics.registerFont(TTFont('DejaVuSans', found_font))
                pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', found_font))  # Используем тот же файл для bold

                # Создаем кастомные стили
                styles = getSampleStyleSheet()
                styles.add(ParagraphStyle(
                    name='DejaVuNormal',
                    fontName='DejaVuSans',
                    fontSize=10,
                    leading=12,
                    encoding='UTF-8'
                ))
                styles.add(ParagraphStyle(
                    name='DejaVuTitle',
                    fontName='DejaVuSans-Bold',
                    fontSize=14,
                    leading=16,
                    spaceAfter=12,
                    encoding='UTF-8'
                ))

            except Exception as font_error:
                logger.error(f"Ошибка шрифтов: {font_error}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Ошибка шрифтов",
                    "Не удалось загрузить шрифты. Убедитесь, что файл DejaVuSans.ttf доступен."
                )
                return

            # 2. Запрос места сохранения
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить отчет",
                f"{title.replace(' ', '_')}.pdf",
                "PDF Files (*.pdf)"
            )

            if not filename:
                return

            if not filename.lower().endswith('.pdf'):
                filename += '.pdf'

            # 3. Генерация PDF
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                encoding='UTF-8'
            )

            story = []

            # Добавляем заголовок
            story.append(Paragraph(title, styles['DejaVuTitle']))
            story.append(Spacer(1, 12))

            # Добавляем содержимое
            for line in content_lines:
                if line:  # Пропускаем пустые строки
                    story.append(Paragraph(str(line), styles['DejaVuNormal']))
                    story.append(Spacer(1, 6))

            try:
                doc.build(story)
            except Exception as build_error:
                logger.error(f"Ошибка построения PDF: {build_error}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Ошибка генерации",
                    f"Не удалось сгенерировать PDF:\n{build_error}"
                )
                return

            # 4. Сохранение файла
            try:
                with open(filename, 'wb') as f:
                    f.write(buffer.getvalue())

                logger.info(f"Отчет успешно сохранен: {filename}")
                QMessageBox.information(
                    self,
                    "Успех",
                    f"Отчет сохранен:\n{filename}"
                )
            except Exception as io_error:
                logger.error(f"Ошибка сохранения: {io_error}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Ошибка сохранения",
                    f"Не удалось сохранить файл:\n{io_error}"
                )

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Произошла непредвиденная ошибка:\n{e}"
            )

    def closeEvent(self, event):
        logger.info("Закрытие админ-панели")
        self.session.close()
        engine.dispose()
        event.accept()

if __name__ == "__main__":
    app = QApplication([])
    window = AdminPanel()
    window.show()
    app.exec()