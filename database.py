"""SQLite database for users, orders, admins, ticket topics, products, categories, settings, security, and logs."""

import json

import aiosqlite

DB_PATH = "bot_data.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                subcategory TEXT NOT NULL,
                price INTEGER NOT NULL,
                payment_method TEXT DEFAULT 'карта',
                status TEXT DEFAULT 'pending',
                invite_link TEXT NOT NULL DEFAULT '',
                access_reissued_count INTEGER NOT NULL DEFAULT 0,
                last_access_reissue_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_topics (
                user_id INTEGER PRIMARY KEY,
                topic_id INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                emoji TEXT NOT NULL DEFAULT '📁',
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price INTEGER NOT NULL,
                channel_link TEXT NOT NULL DEFAULT '',
                channel_id TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_security (
                user_id INTEGER PRIMARY KEY,
                is_banned INTEGER NOT NULL DEFAULT 0,
                ban_reason TEXT NOT NULL DEFAULT '',
                banned_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT NOT NULL,
                user_id INTEGER,
                order_id INTEGER,
                context TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                admin_name TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS button_clicks (
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                last_clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, action)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS purchase_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                rating INTEGER,
                review_text TEXT NOT NULL DEFAULT '',
                needs_help INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(order_id, user_id)
            )
        """)
        # Migrations: all new fields are added without touching existing rows/data.
        migrations = [
            "ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'карта'",
            "ALTER TABLE orders ADD COLUMN invite_link TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN access_reissued_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN last_access_reissue_at TIMESTAMP",
            "ALTER TABLE orders ADD COLUMN review_request_sent INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN reminder_sent INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN cancelled_at TIMESTAMP",
            "ALTER TABLE products ADD COLUMN channel_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE products ADD COLUMN category_id INTEGER NOT NULL DEFAULT 0",
        ]
        for sql in migrations:
            try:
                await db.execute(sql)
            except Exception:
                pass
        await db.commit()


# ─── Settings ────────────────────────────────────────────────────────────────

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value),
        )
        await db.commit()


async def get_all_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT key, value FROM settings")
        return {row[0]: row[1] for row in await cursor.fetchall()}


async def seed_defaults(config_module):
    """Seed settings from config.py defaults if not already set."""
    defaults = {
        "payment_card": config_module.PAYMENT_CARD,
        "payment_name": config_module.PAYMENT_NAME,
        "payment_method": config_module.PAYMENT_METHOD,
        "stars_rate": str(config_module.STARS_RATE),
        "yookassa_token": config_module.YOOKASSA_PROVIDER_TOKEN,
        "cryptobot_token": config_module.CRYPTOBOT_TOKEN,
        "robokassa_login": config_module.ROBOKASSA_MERCHANT_LOGIN,
        "robokassa_password1": config_module.ROBOKASSA_PASSWORD1,
        "robokassa_password2": config_module.ROBOKASSA_PASSWORD2,
        "robokassa_test": "1" if config_module.ROBOKASSA_TEST_MODE else "0",
        "support_contacts": json.dumps(config_module.SUPPORT_CONTACTS, ensure_ascii=False),
        "ticket_group_id": str(config_module.TICKET_GROUP_ID),
        "welcome_message": "🎓 <b>Добро пожаловать!</b>\n\nЗдесь вы можете приобрести доступ к обучающим видеоматериалам.\n\nВыберите раздел:",
        "usd_rate": "90",
        "antispam_message_limit_per_minute": "12",
        "payment_button_cooldown_seconds": "8",
        "access_reissue_enabled": "1",
        "max_access_reissues_per_order": "3",
        "error_log_limit": "20",
        "pending_order_reminder_minutes": "60",
        "daily_backup_enabled": "1",
        "daily_backup_keep_days": "14",
        "review_request_delay_hours": "24",
        "watermark_enabled": "1",
        "watermark_project_name": "Edu Store",
    }
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in defaults.items():
            cursor = await db.execute("SELECT 1 FROM settings WHERE key = ?", (key,))
            if not await cursor.fetchone():
                await db.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)", (key, value),
                )
        await db.commit()


# ─── Categories ──────────────────────────────────────────────────────────────

async def add_category(name: str, description: str = "", emoji: str = "📁") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories")
        next_order = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "INSERT INTO categories (name, description, emoji, sort_order) VALUES (?, ?, ?, ?)",
            (name, description, emoji, next_order),
        )
        await db.commit()
        return cursor.lastrowid


async def update_category(cat_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in kwargs.items():
            if key in ("name", "description", "emoji", "active", "sort_order"):
                await db.execute(f"UPDATE categories SET {key} = ? WHERE id = ?", (value, cat_id))
        await db.commit()


async def delete_category(cat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        await db.commit()


async def get_category(cat_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_active_categories() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM categories WHERE active = 1 ORDER BY sort_order, id"
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_all_categories() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM categories ORDER BY sort_order, id")
        return [dict(r) for r in await cursor.fetchall()]


async def seed_default_categories():
    """Seed default categories if none exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM categories")
        count = (await cursor.fetchone())[0]
        if count == 0:
            defaults = [
                ("Видеоматериалы", "Обучающие видеокурсы по различным направлениям", "🎬", 1),
                ("Поддержка", "Свяжитесь с нами", "🆘", 2),
            ]
            for name, desc, emoji, order in defaults:
                await db.execute(
                    "INSERT INTO categories (name, description, emoji, sort_order) VALUES (?, ?, ?, ?)",
                    (name, desc, emoji, order),
                )
            await db.commit()


async def seed_default_products():
    """Seed default products if the products table is empty."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM products")
        count = (await cursor.fetchone())[0]
        if count == 0:
            # Find first category
            cursor2 = await db.execute("SELECT id FROM categories ORDER BY sort_order LIMIT 1")
            row = await cursor2.fetchone()
            cat_id = row[0] if row else 0
            defaults = [
                ("💻 Программирование", "Полный курс по программированию: Python, JavaScript, веб-разработка и многое другое.", 1000, cat_id, 1),
                ("🎨 Дизайн и Графика", "Уроки дизайна: Figma, Photoshop, Illustrator, UI/UX и графический дизайн.", 500, cat_id, 2),
                ("📱 SMM и Маркетинг", "Курсы по продвижению в соцсетях, таргетированной рекламе и контент-маркетингу.", 100, cat_id, 3),
            ]
            for name, desc, price, cid, order in defaults:
                await db.execute(
                    "INSERT INTO products (name, description, price, category_id, sort_order) VALUES (?, ?, ?, ?, ?)",
                    (name, desc, price, cid, order),
                )
            await db.commit()


# ─── Products ────────────────────────────────────────────────────────────────

async def add_product(name: str, description: str, price: int,
                      channel_link: str = "", channel_id: str = "",
                      category_id: int = 0) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM products")
        next_order = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "INSERT INTO products (name, description, price, channel_link, channel_id, category_id, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, description, price, channel_link, channel_id, category_id, next_order),
        )
        await db.commit()
        return cursor.lastrowid


async def update_product(product_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in kwargs.items():
            if key in ("name", "description", "price", "channel_link", "channel_id", "active", "sort_order", "category_id"):
                await db.execute(f"UPDATE products SET {key} = ? WHERE id = ?", (value, product_id))
        await db.commit()


async def delete_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()


async def get_product(product_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_active_products(category_id: int | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if category_id is not None:
            cursor = await db.execute(
                "SELECT * FROM products WHERE active = 1 AND category_id = ? ORDER BY sort_order, id",
                (category_id,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM products WHERE active = 1 ORDER BY sort_order, id"
            )
        return [dict(r) for r in await cursor.fetchall()]


async def get_all_products() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products ORDER BY sort_order, id")
        return [dict(r) for r in await cursor.fetchall()]


# ─── Users ───────────────────────────────────────────────────────────────────

async def add_user(user_id: int, username: str | None, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name),
        )
        await db.commit()


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users ORDER BY joined_at DESC")
        return [dict(r) for r in await cursor.fetchall()]


# ─── Admins ──────────────────────────────────────────────────────────────────

async def add_admin(user_id: int, username: str | None, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admins (user_id, username, added_by) VALUES (?, ?, ?)",
            (user_id, username, added_by),
        )
        await db.commit()


async def update_admin_username(user_id: int, username: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE admins SET username = ? WHERE user_id = ?", (username, user_id))
        await db.commit()


async def remove_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_all_admins() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM admins ORDER BY added_at")
        return [dict(r) for r in await cursor.fetchall()]


async def is_admin_in_db(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return await cursor.fetchone() is not None


# ─── Orders ──────────────────────────────────────────────────────────────────

async def create_order(user_id: int, username: str | None, subcategory: str,
                       price: int, payment_method: str = "карта") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, subcategory, price, payment_method) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, username, subcategory, price, payment_method),
        )
        await db.commit()
        return cursor.lastrowid


async def confirm_order(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (order_id,),
        )
        await db.commit()


async def reject_order(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        await db.commit()


async def get_order(order_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_orders(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        users_count = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM orders")
        orders_count = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE status = 'confirmed'")
        confirmed_count = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
        pending_count = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COALESCE(SUM(price), 0) FROM orders WHERE status = 'confirmed'"
        )
        total_revenue = (await cursor.fetchone())[0]
        return {
            "users": users_count, "orders": orders_count,
            "confirmed": confirmed_count, "pending": pending_count,
            "revenue": total_revenue,
        }


async def get_pending_orders() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE status = 'pending' ORDER BY created_at DESC"
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_all_orders(limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


# ─── Ticket Topics ───────────────────────────────────────────────────────────

async def get_topic_id(user_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT topic_id FROM ticket_topics WHERE user_id = ?", (user_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def save_topic_id(user_id: int, topic_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO ticket_topics (user_id, topic_id) VALUES (?, ?)",
            (user_id, topic_id),
        )
        await db.commit()


async def get_user_by_topic(topic_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM ticket_topics WHERE topic_id = ?", (topic_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


# ─── Security / Anti-spam / Error logs ───────────────────────────────────────

async def set_user_ban(user_id: int, is_banned: bool, reason: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_security (user_id, is_banned, ban_reason, banned_at, updated_at)
            VALUES (?, ?, ?, CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE NULL END, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                is_banned = excluded.is_banned,
                ban_reason = excluded.ban_reason,
                banned_at = excluded.banned_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, 1 if is_banned else 0, reason, 1 if is_banned else 0),
        )
        await db.commit()


async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT is_banned FROM user_security WHERE user_id = ?", (user_id,),
        )
        row = await cursor.fetchone()
        return bool(row and row[0])


async def get_banned_users(limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT us.user_id, us.ban_reason, us.banned_at, u.username, u.full_name
            FROM user_security us
            LEFT JOIN users u ON u.user_id = us.user_id
            WHERE us.is_banned = 1
            ORDER BY us.banned_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def register_button_click(user_id: int, action: str, cooldown_seconds: int) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds) for payment/access buttons."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT CAST(strftime('%s', 'now') AS INTEGER) - CAST(strftime('%s', last_clicked_at) AS INTEGER)
            FROM button_clicks
            WHERE user_id = ? AND action = ?
            """,
            (user_id, action),
        )
        row = await cursor.fetchone()
        elapsed = int(row[0]) if row and row[0] is not None else None
        if elapsed is not None and elapsed < cooldown_seconds:
            return False, max(1, cooldown_seconds - elapsed)
        await db.execute(
            """
            INSERT INTO button_clicks (user_id, action, last_clicked_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, action) DO UPDATE SET last_clicked_at = CURRENT_TIMESTAMP
            """,
            (user_id, action),
        )
        await db.commit()
        return True, 0


async def log_error(error_type: str, message: str, user_id: int | None = None,
                    order_id: int | None = None, context: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO error_logs (error_type, user_id, order_id, context, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (error_type, user_id, order_id, context[:500], str(message)[:1500]),
        )
        await db.commit()


async def get_error_logs(limit: int = 20, error_type: str | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if error_type:
            cursor = await db.execute(
                "SELECT * FROM error_logs WHERE error_type = ? ORDER BY created_at DESC LIMIT ?",
                (error_type, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM error_logs ORDER BY created_at DESC LIMIT ?", (limit,),
            )
        return [dict(r) for r in await cursor.fetchall()]


async def get_error_summary() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT error_type, COUNT(*) AS count, MAX(created_at) AS last_at
            FROM error_logs
            GROUP BY error_type
            ORDER BY count DESC, last_at DESC
            """
        )
        return [dict(r) for r in await cursor.fetchall()]


async def clear_error_logs(error_type: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if error_type:
            await db.execute("DELETE FROM error_logs WHERE error_type = ?", (error_type,))
        else:
            await db.execute("DELETE FROM error_logs")
        await db.commit()


async def log_admin_action(admin_id: int, admin_name: str, action: str, details: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO admin_logs (admin_id, admin_name, action, details)
            VALUES (?, ?, ?, ?)
            """,
            (admin_id, str(admin_name or "")[:200], str(action or "")[:250], str(details or "")[:1000]),
        )
        await db.commit()


async def get_admin_logs(limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM admin_logs ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def clear_admin_logs():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admin_logs")
        await db.commit()


async def purge_old_admin_logs(days: int = 7):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM admin_logs WHERE created_at < datetime('now', ?)",
            (f"-{int(days)} days",),
        )
        await db.commit()


async def save_order_invite_link(order_id: int, invite_link: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET invite_link = ? WHERE id = ?", (invite_link, order_id))
        await db.commit()


async def increment_order_reissue(order_id: int, invite_link: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE orders
            SET access_reissued_count = COALESCE(access_reissued_count, 0) + 1,
                last_access_reissue_at = CURRENT_TIMESTAMP,
                invite_link = CASE WHEN ? != '' THEN ? ELSE invite_link END
            WHERE id = ?
            """,
            (invite_link, invite_link, order_id),
        )
        await db.commit()


# ─── Admin convenience helpers ───────────────────────────────────────────────

async def get_orders_filtered(limit: int = 20, status: str | None = None,
                              payment_methods: list[str] | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if payment_methods:
            placeholders = ",".join("?" for _ in payment_methods)
            clauses.append(f"payment_method IN ({placeholders})")
            params.extend(payment_methods)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM orders{where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor = await db.execute(sql, tuple(params))
        return [dict(r) for r in await cursor.fetchall()]


async def get_user_order_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
        total = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'confirmed'", (user_id,))
        confirmed = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'pending'", (user_id,))
        pending = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status = 'rejected'", (user_id,))
        rejected = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COALESCE(SUM(price), 0) FROM orders WHERE user_id = ? AND status = 'confirmed'", (user_id,))
        revenue = (await cursor.fetchone())[0]
        return {
            "total": total,
            "confirmed": confirmed,
            "pending": pending,
            "rejected": rejected,
            "revenue": revenue,
        }


async def get_user_security(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM user_security WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def search_admin_items(query: str, limit: int = 10) -> dict:
    """Search orders and users by order ID, user ID, username, full name, or product name."""
    q = (query or "").strip()
    like = f"%{q.lstrip('@')}%"
    numeric = q.lstrip("-").isdigit()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        order_params = []
        user_params = []
        order_clauses = ["LOWER(COALESCE(o.username, '')) LIKE LOWER(?)",
                         "LOWER(COALESCE(p.name, '')) LIKE LOWER(?)",
                         "LOWER(COALESCE(o.payment_method, '')) LIKE LOWER(?)"]
        order_params.extend([like, like, like])
        user_clauses = ["LOWER(COALESCE(u.username, '')) LIKE LOWER(?)",
                        "LOWER(COALESCE(u.full_name, '')) LIKE LOWER(?)"]
        user_params.extend([like, like])
        if numeric:
            num = int(q)
            order_clauses.extend(["o.id = ?", "o.user_id = ?"])
            order_params.extend([num, num])
            user_clauses.append("u.user_id = ?")
            user_params.append(num)
        order_sql = f"""
            SELECT o.*
            FROM orders o
            LEFT JOIN products p ON p.id = CAST(o.subcategory AS INTEGER)
            WHERE {' OR '.join(order_clauses)}
            ORDER BY o.created_at DESC
            LIMIT ?
        """
        user_sql = f"""
            SELECT u.*
            FROM users u
            WHERE {' OR '.join(user_clauses)}
            ORDER BY u.joined_at DESC
            LIMIT ?
        """
        order_params.append(limit)
        user_params.append(limit)
        order_cursor = await db.execute(order_sql, tuple(order_params))
        user_cursor = await db.execute(user_sql, tuple(user_params))
        return {
            "orders": [dict(r) for r in await order_cursor.fetchall()],
            "users": [dict(r) for r in await user_cursor.fetchall()],
        }


# ─── Backups / reminders / reviews ───────────────────────────────────────

async def get_orders_for_review_requests(delay_hours: int = 24, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM orders
            WHERE status = 'confirmed'
              AND COALESCE(review_request_sent, 0) = 0
              AND confirmed_at IS NOT NULL
              AND confirmed_at <= datetime('now', ?)
            ORDER BY confirmed_at
            LIMIT ?
            """,
            (f"-{int(delay_hours)} hours", limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def mark_review_request_sent(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET review_request_sent = 1 WHERE id = ?", (order_id,))
        await db.commit()


async def save_purchase_review(order_id: int, user_id: int, rating: int | None = None,
                               review_text: str = "", needs_help: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO purchase_reviews (order_id, user_id, rating, review_text, needs_help)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(order_id, user_id) DO UPDATE SET
                rating = COALESCE(excluded.rating, purchase_reviews.rating),
                review_text = CASE WHEN excluded.review_text != '' THEN excluded.review_text ELSE purchase_reviews.review_text END,
                needs_help = CASE WHEN excluded.needs_help != 0 THEN excluded.needs_help ELSE purchase_reviews.needs_help END
            """,
            (order_id, user_id, rating, str(review_text or "")[:3000], 1 if needs_help else 0),
        )
        await db.commit()


async def get_purchase_reviews(limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT r.*, u.username, u.full_name, o.subcategory, o.price
            FROM purchase_reviews r
            LEFT JOIN users u ON u.user_id = r.user_id
            LEFT JOIN orders o ON o.id = r.order_id
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_pending_orders_for_reminder(minutes: int = 60, limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM orders
            WHERE status = 'pending'
              AND COALESCE(reminder_sent, 0) = 0
              AND created_at <= datetime('now', ?)
            ORDER BY created_at
            LIMIT ?
            """,
            (f"-{int(minutes)} minutes", limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def mark_order_reminder_sent(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET reminder_sent = 1 WHERE id = ?", (order_id,))
        await db.commit()


async def cancel_order(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'",
            (order_id,),
        )
        await db.commit()


async def get_all_orders_export() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM orders ORDER BY created_at DESC")
        return [dict(r) for r in await cursor.fetchall()]
