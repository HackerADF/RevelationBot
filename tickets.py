import aiosqlite
import asyncio
import os

async def create_ticket_db():
    if os.path.exists("tickets.db"):
        os.remove("tickets.db")
        print("Existing database deleted.")
    async with aiosqlite.connect("tickets.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL
            );
        """)
        await db.commit()
        print("New ticket database created.")
asyncio.run(create_ticket_db())
