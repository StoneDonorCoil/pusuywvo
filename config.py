"""Bot configuration."""

BOT_TOKEN = "8790371252:AAEpzGjwN0sgAbkuWrX79WyNbCK9NJnVnxE"

# Admin Telegram user ID — set your own ID here.
# To find your ID, send /myid to @userinfobot in Telegram.
ADMIN_ID = None  # e.g. 123456789

# Payment details
PAYMENT_CARD = "5599 0021 3690 6395"
PAYMENT_NAME = "Шибакова Клавдия Сергеевна"
PAYMENT_METHOD = "ЮMoney / Перевод на карту"

# Subcategories with prices and channel invite links
# Replace invite links with your actual private channel links
SUBCATEGORIES = {
    "programming": {
        "name": "💻 Программирование",
        "price": 1000,
        "description": "Полный курс по программированию: Python, JavaScript, веб-разработка и многое другое.",
        "channel_link": "https://t.me/+XXXXXX",  # Replace with real link
    },
    "design": {
        "name": "🎨 Дизайн и Графика",
        "price": 500,
        "description": "Уроки дизайна: Figma, Photoshop, Illustrator, UI/UX и графический дизайн.",
        "channel_link": "https://t.me/+YYYYYY",  # Replace with real link
    },
    "smm": {
        "name": "📱 SMM и Маркетинг",
        "price": 100,
        "description": "Курсы по продвижению в соцсетях, таргетированной рекламе и контент-маркетингу.",
        "channel_link": "https://t.me/+ZZZZZZ",  # Replace with real link
    },
}

# Support contacts
SUPPORT_CONTACTS = [
    {"name": "Администратор", "username": "@admin_username"},
    {"name": "Техподдержка", "username": "@support_username"},
]
