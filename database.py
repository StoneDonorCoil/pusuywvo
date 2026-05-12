"""SQLite database for users and orders."""

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
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()


async def add_user(user_id: int, username: str | None, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name),
        )
        await db.commit()


async def create_order(user_id: int, username: str | None, subcategory: str, price: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, subcategory, price) VALUES (?, ?, ?, ?)",
            (user_id, username, subcategory, price),
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
        await db.execute(
            "UPDATE orders SET status = 'rejected' WHERE id = ?",
            (order_id,),
        )
        await db.commit()


async def get_order(order_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None


async def get_user_orders(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        users_count = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM orders")
        orders_count = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE status = 'confirmed'")
        confirmed_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COALESCE(SUM(price), 0) FROM orders WHERE status = 'confirmed'"
        )
        total_revenue = (await cursor.fetchone())[0]

        return {
            "users": users_count,
            "orders": orders_count,
            "confirmed": confirmed_count,
            "revenue": total_revenue,
        }
