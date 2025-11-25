"""
Database Abstraction Layer - Support both SQLite and PostgreSQL
"""
import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import json

DATABASE_URL = os.getenv('DATABASE_URL')  # PostgreSQL: postgresql://user:pass@host/db
USE_POSTGRES = DATABASE_URL and DATABASE_URL.startswith('postgresql://')

class Database:
    @staticmethod
    def connect():
        """Connect to database (SQLite or PostgreSQL)"""
        if USE_POSTGRES:
            try:
                conn = psycopg2.connect(DATABASE_URL)
                conn.autocommit = False
                return conn
            except Exception as e:
                print(f"❌ PostgreSQL connection failed: {e}")
                print("⚠️ Falling back to SQLite...")
                return sqlite3.connect('warrior_subscriptions.db')
        else:
            return sqlite3.connect('warrior_subscriptions.db')
    
    @staticmethod
    def get_cursor(conn):
        """Get appropriate cursor for database type"""
        if isinstance(conn, psycopg2.extensions.connection):
            return conn.cursor(cursor_factory=RealDictCursor)
        else:
            conn.row_factory = sqlite3.Row
            return conn.cursor()
    
    @staticmethod
    def execute_query(query, params=None, fetch_one=False, fetch_all=False):
        """Execute query (abstracted for both databases)"""
        conn = Database.connect()
        try:
            c = Database.get_cursor(conn)
            
            if USE_POSTGRES:
                # Convert ? to %s for PostgreSQL
                query = query.replace('?', '%s')
                c.execute(query, params or ())
            else:
                c.execute(query, params or ())
            
            if fetch_one:
                result = c.fetchone()
            elif fetch_all:
                result = c.fetchall()
            else:
                result = None
            
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            print(f"❌ DB Error: {e}")
            raise
        finally:
            conn.close()
    
    @staticmethod
    def migrate_sqlite_to_postgres():
        """Migrate data from SQLite to PostgreSQL (one-time)"""
        if not USE_POSTGRES:
            print("ℹ️ PostgreSQL not configured, skipping migration")
            return
        
        print("🔄 Starting SQLite → PostgreSQL migration...")
        
        try:
            # Connect to both databases
            sqlite_conn = sqlite3.connect('warrior_subscriptions.db')
            sqlite_conn.row_factory = sqlite3.Row
            sqlite_c = sqlite_conn.cursor()
            
            postgres_conn = psycopg2.connect(DATABASE_URL)
            postgres_c = postgres_conn.cursor()
            
            # Tables to migrate
            tables = [
                'packages', 'subscriptions', 'pending_orders', 'renewals',
                'trial_members', 'referral_codes', 'commissions', 'discount_codes',
                'closed_periods', 'admin_logs'
            ]
            
            for table in tables:
                try:
                    # Get data from SQLite
                    sqlite_c.execute(f'SELECT * FROM {table}')
                    rows = sqlite_c.fetchall()
                    
                    if rows:
                        # Get column names
                        columns = [description[0] for description in sqlite_c.description]
                        
                        # Insert into PostgreSQL
                        for row in rows:
                            placeholders = ','.join(['%s'] * len(columns))
                            insert_query = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                            try:
                                postgres_c.execute(insert_query, tuple(row))
                            except Exception as e:
                                print(f"⚠️ Skipping row in {table}: {e}")
                        
                        postgres_conn.commit()
                        print(f"✅ Migrated {table}: {len(rows)} rows")
                except Exception as e:
                    print(f"⚠️ Migration skipped for {table}: {e}")
            
            sqlite_conn.close()
            postgres_conn.close()
            print("✅ Migration complete!")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")

# Legacy SQLite wrapper for backward compatibility
def get_db_connection():
    """Get database connection (backward compatible)"""
    return Database.connect()

def execute_db_query(query, params=None, fetch_one=False, fetch_all=False):
    """Execute DB query (backward compatible)"""
    return Database.execute_query(query, params, fetch_one, fetch_all)
