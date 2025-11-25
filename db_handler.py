"""
Database Abstraction Layer - Support both SQLite and PostgreSQL
Smart wrapper that handles all query patterns automatically
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
    def _convert_query(query):
        """Convert SQLite placeholders (?) to PostgreSQL (%s)"""
        if USE_POSTGRES:
            # Simple replacement - works for most cases
            return query.replace('?', '%s')
        return query
    
    @staticmethod
    def execute(query, params=None, fetch_one=False, fetch_all=False, commit=True):
        """Universal execute function - handles both SQLite and PostgreSQL"""
        conn = Database.connect()
        try:
            c = Database.get_cursor(conn)
            query = Database._convert_query(query)
            
            if params:
                c.execute(query, params if isinstance(params, (list, tuple)) else (params,))
            else:
                c.execute(query)
            
            result = None
            if fetch_one:
                result = c.fetchone()
            elif fetch_all:
                result = c.fetchall()
            
            if commit:
                conn.commit()
            
            return result
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    @staticmethod
    def executemany(query, params_list, commit=True):
        """Execute multiple queries (for batch inserts)"""
        conn = Database.connect()
        try:
            c = Database.get_cursor(conn)
            query = Database._convert_query(query)
            c.executemany(query, params_list)
            
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
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
                'closed_periods'
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

# Legacy wrapper functions for smooth migration
def execute_query(query, params=None, fetch_one=False, fetch_all=False, commit=True):
    """Backward compatible wrapper"""
    return Database.execute(query, params, fetch_one, fetch_all, commit)

def execute_query_many(query, params_list):
    """Backward compatible wrapper for batch operations"""
    return Database.executemany(query, params_list)
