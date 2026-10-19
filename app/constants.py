"""Единые перечисления и константы предметной области (см. ТЗ п.4.1.5, 4.1.6)."""

# --- Роли пользователей (RBAC, ТЗ п.4.1.5) ---
ROLE_SUPERADMIN = "superadmin"     # суперадминистратор сети
ROLE_LOCATION_ADMIN = "admin"      # администратор локации
ROLE_HOST = "host"                 # ведущий квеста
ROLE_MANAGER = "manager"           # менеджер по продажам/бронированию
ROLE_ACCOUNTANT = "accountant"     # бухгалтер
ROLE_CLIENT = "client"             # клиент (публичный виджет)

ALL_ROLES = [
    ROLE_SUPERADMIN,
    ROLE_LOCATION_ADMIN,
    ROLE_HOST,
    ROLE_MANAGER,
    ROLE_ACCOUNTANT,
    ROLE_CLIENT,
]

STAFF_ROLES = [ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN, ROLE_HOST, ROLE_MANAGER, ROLE_ACCOUNTANT]

ROLE_LABELS = {
    ROLE_SUPERADMIN: "Суперадминистратор сети",
    ROLE_LOCATION_ADMIN: "Администратор локации",
    ROLE_HOST: "Ведущий квеста",
    ROLE_MANAGER: "Менеджер по продажам",
    ROLE_ACCOUNTANT: "Бухгалтер",
    ROLE_CLIENT: "Клиент",
}

# --- Статусы слота расписания ---
SLOT_AVAILABLE = "available"
SLOT_BOOKED = "booked"
SLOT_BLOCKED = "blocked"       # выведен из расписания (ремонт/тех.причины)
SLOT_COMPLETED = "completed"

# --- Статусы бронирования ---
BOOKING_CONFIRMED = "confirmed"
BOOKING_COMPLETED = "completed"
BOOKING_CANCELED = "canceled"
BOOKING_NO_SHOW = "no_show"

BOOKING_STATUS_LABELS = {
    BOOKING_CONFIRMED: "Подтверждено",
    BOOKING_COMPLETED: "Проведено",
    BOOKING_CANCELED: "Отменено",
    BOOKING_NO_SHOW: "Неявка",
}

# --- Каналы уведомлений ---
CHANNEL_EMAIL = "email"
CHANNEL_SMS = "sms"
CHANNEL_MESSENGER = "messenger"

# --- Типы уведомлений ---
NOTIF_BOOKING_CONFIRMED = "booking_confirmed"
NOTIF_REMINDER_24H = "reminder_24h"
NOTIF_REMINDER_2H = "reminder_2h"
NOTIF_NEW_BOOKING_FOR_ADMIN = "new_booking_admin"
NOTIF_REVIEW_REQUEST = "review_request"
NOTIF_BOOKING_CANCELED = "booking_canceled"

# --- Роли, которыми может управлять администратор локации (не суперадмин) ---
# Администратор локации не вправе создавать/блокировать/редактировать других
# администраторов и суперадминов — только «линейный» персонал своего филиала.
LOCATION_ADMIN_MANAGEABLE_ROLES = [ROLE_HOST, ROLE_MANAGER, ROLE_ACCOUNTANT]

# --- Лимиты (защита от чрезмерных запросов/раздувания данных) ---
MAX_SLOT_GENERATION_DAYS = 93     # не более ~3 месяцев расписания за одну операцию
MAX_REPORT_PERIOD_DAYS = 366      # период отчёта/экспорта
MAX_PUBLIC_SLOTS_RANGE_DAYS = 31  # диапазон публичного API свободных сеансов
MAX_TEXT_FIELD_LENGTH = 255       # причины отмены/заметки (длина колонок String(255))

# --- Блокировка учётной записи при переборе пароля ---
LOGIN_MAX_FAILED_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 15

# --- Статусы программы лояльности клиентов (CRM, ТЗ п.4.2.3) ---
LOYALTY_STATUSES = ["Новичок", "Друг квестов", "Постоянный гость", "VIP"]
