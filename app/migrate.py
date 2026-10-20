"""Explicit deployment step: python -m app.migrate."""
import asyncio

from dotenv import load_dotenv

load_dotenv()


async def main():
    from app.db import db
    try:
        await db.connect()
        await db.init_tables()
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
