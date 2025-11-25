#!/usr/bin/env python3
"""
Migration script: SQLite → PostgreSQL
Usage: python3 migrate_to_postgres.py
"""
import os
from db_handler import Database, USE_POSTGRES

if __name__ == '__main__':
    print("=" * 60)
    print("DiaryCrypto Bot: SQLite → PostgreSQL Migration")
    print("=" * 60)
    
    if not USE_POSTGRES:
        print("❌ DATABASE_URL not set or invalid!")
        print("ℹ️ Set DATABASE_URL environment variable to enable PostgreSQL")
        print("   Example: postgresql://user:password@localhost/diarycrypto")
        exit(1)
    
    Database.migrate_sqlite_to_postgres()
    print("\n✅ Migration complete! You can now deploy to Render.")
