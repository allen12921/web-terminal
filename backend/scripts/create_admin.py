#!/usr/bin/env python3
"""Seed the first admin user. Run with: python scripts/create_admin.py"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite
from database import DB_PATH, init_db
from services.auth import hash_password


async def main():
    await init_db()
    username = input("Admin username [admin]: ").strip() or "admin"
    email = input("Admin email: ").strip()
    password = input("Admin password: ").strip()
    if not password:
        print("Password cannot be empty")
        sys.exit(1)

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO users (username, email, hashed_password, is_admin) VALUES (?, ?, ?, 1)",
                (username, email, hash_password(password)),
            )
            await db.commit()
            print(f"Admin user '{username}' created successfully.")
        except aiosqlite.IntegrityError:
            print(f"User '{username}' already exists.")


asyncio.run(main())
