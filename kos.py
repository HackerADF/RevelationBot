import aiosqlite
import asyncio
import os

async def create_kos_db():
    if os.path.exists("kos.db"):
        os.remove("kos.db")
        print("Existing database deleted.")

    async with aiosqlite.connect("kos.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kos (
                username TEXT PRIMARY KEY,
                timestamp INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                reason TEXT NOT NULL
            );
        """)
        await db.commit()
        print("New kos.db created with UNIX timestamp support.")

# Run the DB setup
if __name__ == "__main__":
    asyncio.run(create_kos_db())
