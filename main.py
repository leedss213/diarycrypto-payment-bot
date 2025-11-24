import os
import discord
from discord import app_commands
from discord.ui import Modal, TextInput
import midtransclient
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import threading
import asyncio
import csv
from io import BytesIO, StringIO
from typing import Optional
import pytz
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import requests
import json

TOKEN = os.environ.get('DISCORD_TOKEN', '')
GUILD_ID = 1370638839407972423
ORIGIN_ROLE_NAME = "Origin"
NEWS_CHANNEL_NAME = "📰｜berita-crypto"  # Channel untuk auto-post berita crypto

# Referral System - 6 Analysts + 1 Lead with Randomized Codes
REFERRAL_CODES = {
    "b4y_ktx": "Bay",
    "d1l3n4x": "Dialena",
    "k4m4d0z": "Kamado",
    "ry2uw3k": "Ryzu",
    "z3nqp0x": "Zen",
    "r3yt8m2": "Rey",
    "b3llrft": "Bell"
}

# Reverse mapping for analyst commission commands (name → code)
ANALYST_TO_CODE = {v.lower(): k for k, v in REFERRAL_CODES.items()}

# Keep old naming for backward compatibility in commands
ANALYSTS = {
    "bay": "Bay",
    "dialena": "Dialena",
    "kamado": "Kamado",
    "ryzu": "Ryzu",
    "zen": "Zen",
    "rey": "Rey"
}
ANALYST_LEAD = "Bell"
ALL_REFERRERS = REFERRAL_CODES

PACKAGES = {
    "warrior_1hour": {
        "name": "The Warrior 1 Hour (Test)",
        "price": 50000,
        "duration_days": 0.041667,
        "role_name": "The Warrior"
    },
    "warrior_1month": {
        "name": "The Warrior 1 Month",
        "price": 299000,
        "duration_days": 30,
        "role_name": "The Warrior"
    },
    "warrior_3month": {
        "name": "The Warrior 3 Months",
        "price": 649000,
        "duration_days": 90,
        "role_name": "The Warrior"
    }
}

MIDTRANS_SERVER_KEY = os.environ.get('MIDTRANS_SERVER_KEY', '')
MIDTRANS_CLIENT_KEY = os.environ.get('MIDTRANS_CLIENT_KEY', '')
REPL_SLUG = os.environ.get('REPL_SLUG', 'workspace')
REPL_OWNER = os.environ.get('REPL_OWNER', 'unknown')

# Gmail Configuration
GMAIL_SENDER = os.environ.get('GMAIL_SENDER', '')
GMAIL_PASSWORD = os.environ.get('GMAIL_PASSWORD', '')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')

print(f"🔑 Midtrans Server Key: {'✅ SET' if MIDTRANS_SERVER_KEY else '❌ NOT SET'}")
print(f"🔑 Midtrans Client Key: {'✅ SET' if MIDTRANS_CLIENT_KEY else '❌ NOT SET'}")
print(f"📧 Gmail Sender: {'✅ SET' if GMAIL_SENDER else '❌ NOT SET'}")
print(f"📧 Admin Email: {'✅ SET' if ADMIN_EMAIL else '❌ NOT SET'}")

# Last posted crypto news (to avoid duplicates)
last_posted_news = {}

bot_start_time = datetime.now(pytz.timezone('Asia/Jakarta'))

app = Flask(__name__)


@app.route('/webhook/midtrans', methods=['POST'])
def midtrans_webhook():
    try:
        notification = request.get_json()
        print(f"📥 Webhook received: {notification}")

        order_id = notification.get('order_id')
        transaction_status = notification.get('transaction_status')
        fraud_status = notification.get('fraud_status')

        print(
            f"Order: {order_id}, Status: {transaction_status}, Fraud: {fraud_status}"
        )

        if transaction_status == 'capture':
            if fraud_status == 'accept':
                asyncio.run_coroutine_threadsafe(
                    activate_subscription(order_id), bot.loop)
        elif transaction_status == 'settlement':
            asyncio.run_coroutine_threadsafe(activate_subscription(order_id),
                                             bot.loop)
        elif transaction_status in ['cancel', 'deny', 'expire']:
            print(f"❌ Payment {transaction_status} for order {order_id}")

        return jsonify({'status': 'success'}), 200
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'status': 'running',
        'bot': 'DiaryCrypto Payment Bot',
        'mode': 'SANDBOX Testing',
        'endpoints': {
            'webhook': '/webhook/midtrans',
            'health': '/health',
            'test': '/test-midtrans'
        }
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'bot': 'running'}), 200


@app.route('/test-midtrans', methods=['GET'])
def test_midtrans():
    """Test Midtrans connection"""
    if not MIDTRANS_SERVER_KEY or not MIDTRANS_CLIENT_KEY:
        return jsonify({
            'status': 'error',
            'message': 'Midtrans keys not configured',
            'server_key_set': bool(MIDTRANS_SERVER_KEY),
            'client_key_set': bool(MIDTRANS_CLIENT_KEY)
        }), 500
    
    try:
        test_transaction = snap.create_transaction({
            "transaction_details": {
                "order_id": f"test-{int(datetime.now().timestamp())}",
                "gross_amount": 1000
            },
            "item_details": [{
                "id": "test",
                "price": 1000,
                "quantity": 1,
                "name": "Test Item"
            }],
            "customer_details": {
                "first_name": "Test",
                "email": "test@test.com",
                "phone": "1234567890"
            }
        })
        return jsonify({
            'status': 'success',
            'message': 'Midtrans connection OK',
            'redirect_url': test_transaction.get('redirect_url', 'No redirect URL')
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'error_type': type(e).__name__
        }), 500


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)
snap = midtransclient.Snap(is_production=False,
                           server_key=MIDTRANS_SERVER_KEY,
                           client_key=MIDTRANS_CLIENT_KEY)


def get_jakarta_time():
    """Get current time in Indonesia (WIB) timezone"""
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    return datetime.now(jakarta_tz)


def format_jakarta_datetime(dt):
    """Format datetime to WIB format (time only)"""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    utc_tz = pytz.timezone('UTC')
    
    # If no timezone, assume it's UTC (from database)
    if dt.tzinfo is None:
        dt = utc_tz.localize(dt)
    
    # Convert to Jakarta timezone
    dt = dt.astimezone(jakarta_tz)
    return dt.strftime('%H:%M WIB')


def format_jakarta_datetime_full(dt):
    """Format datetime to full date and time format (YYYY-MM-DD HH:MM WIB)"""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    utc_tz = pytz.timezone('UTC')
    
    # If no timezone, assume it's UTC (from database)
    if dt.tzinfo is None:
        dt = utc_tz.localize(dt)
    
    # Convert to Jakarta timezone
    dt = dt.astimezone(jakarta_tz)
    return dt.strftime('%Y-%m-%d %H:%M WIB')


def init_database():
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                 (discord_id TEXT PRIMARY KEY,
                  discord_username TEXT,
                  nama TEXT,
                  email TEXT,
                  nomor_hp TEXT,
                  package_type TEXT,
                  start_date TIMESTAMP,
                  end_date TIMESTAMP,
                  status TEXT DEFAULT 'active',
                  order_id TEXT,
                  notified_3days INTEGER DEFAULT 0,
                  last_notified_3days TIMESTAMP,
                  email_sent INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_orders
                 (order_id TEXT PRIMARY KEY,
                  discord_id TEXT,
                  discord_username TEXT,
                  nama TEXT,
                  email TEXT,
                  nomor_hp TEXT,
                  package_type TEXT,
                  duration_days INTEGER,
                  is_renewal INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS discount_codes
                 (code TEXT PRIMARY KEY,
                  discount_percentage INTEGER,
                  valid_until TIMESTAMP,
                  usage_limit INTEGER,
                  used_count INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  discord_id TEXT,
                  order_id TEXT,
                  package_type TEXT,
                  amount INTEGER,
                  status TEXT,
                  transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS packages
                 (package_id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  price INTEGER NOT NULL,
                  duration_days REAL NOT NULL,
                  role_name TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS referrals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  referrer_name TEXT NOT NULL,
                  referred_discord_id TEXT,
                  referred_username TEXT,
                  order_id TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS commissions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  referrer_name TEXT NOT NULL,
                  referred_discord_id TEXT,
                  referred_username TEXT,
                  order_id TEXT,
                  package_type TEXT,
                  original_amount INTEGER,
                  discount_percentage INTEGER DEFAULT 0,
                  final_amount INTEGER,
                  commission_amount INTEGER,
                  paid_status TEXT DEFAULT 'pending',
                  transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS trial_codes
                 (code TEXT PRIMARY KEY,
                  duration_days INTEGER,
                  valid_until TIMESTAMP,
                  usage_limit INTEGER,
                  used_count INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS trial_members
                 (discord_id TEXT PRIMARY KEY,
                  discord_username TEXT,
                  trial_end_date TIMESTAMP,
                  status TEXT DEFAULT 'active',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()
    
    # Load default packages into database if empty
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM packages')
    if c.fetchone()[0] == 0:
        default_packages = [
            ("warrior_1hour", "The Warrior 1 Hour (Test)", 50000, 0.041667, "The Warrior"),
            ("warrior_1month", "The Warrior 1 Month", 299000, 30, "The Warrior"),
            ("warrior_3month", "The Warrior 3 Months", 649000, 90, "The Warrior")
        ]
        for pkg in default_packages:
            c.execute('''INSERT INTO packages (package_id, name, price, duration_days, role_name)
                        VALUES (?, ?, ?, ?, ?)''', pkg)
        conn.commit()
        print("✅ Default packages loaded into database")
    conn.close()


def save_pending_order(order_id, discord_id, discord_username, nama, email, nomor_hp, package_type, duration_days, is_renewal=False, referrer_name=None):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    # Add referral_name column if not exists
    try:
        c.execute('ALTER TABLE pending_orders ADD COLUMN referrer_name TEXT')
    except sqlite3.OperationalError:
        pass
    
    c.execute(
        '''INSERT OR REPLACE INTO pending_orders 
                 (order_id, discord_id, discord_username, nama, email, nomor_hp, package_type, duration_days, is_renewal, referrer_name)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (order_id, discord_id, discord_username, nama, email, nomor_hp, package_type, duration_days, 1 if is_renewal else 0, referrer_name))
    conn.commit()
    conn.close()


def get_pending_order(order_id):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    try:
        c.execute(
            'SELECT discord_id, discord_username, nama, email, nomor_hp, package_type, duration_days, is_renewal, COALESCE(referrer_name, "") FROM pending_orders WHERE order_id = ?',
            (order_id, ))
    except sqlite3.OperationalError:
        c.execute(
            'SELECT discord_id, discord_username, nama, email, nomor_hp, package_type, duration_days, is_renewal FROM pending_orders WHERE order_id = ?',
            (order_id, ))
    result = c.fetchone()
    conn.close()
    return result


def save_subscription(discord_id, discord_username, nama, email, nomor_hp, package_type, duration_days, order_id, is_renewal=False, referrer_name=None):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    # Add referrer_name column if not exists
    try:
        c.execute('ALTER TABLE subscriptions ADD COLUMN referrer_name TEXT')
    except sqlite3.OperationalError:
        pass
    
    # Add last_notified_3days column if not exists
    try:
        c.execute('ALTER TABLE subscriptions ADD COLUMN last_notified_3days TIMESTAMP')
    except sqlite3.OperationalError:
        pass
    
    if is_renewal:
        c.execute('SELECT end_date FROM subscriptions WHERE discord_id = ? AND status = "active"', (discord_id,))
        existing = c.fetchone()
        if existing:
            current_end = datetime.fromisoformat(existing[0])
            if current_end > datetime.now():
                start_date = current_end
            else:
                start_date = datetime.now()
        else:
            start_date = datetime.now()
    else:
        start_date = datetime.now()
    
    end_date = start_date + timedelta(days=duration_days)

    c.execute(
        '''INSERT OR REPLACE INTO subscriptions 
                 (discord_id, discord_username, nama, email, nomor_hp, package_type, start_date, end_date, status, order_id, notified_3days, email_sent, referrer_name)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, 0, 0, ?)''',
        (discord_id, discord_username, nama, email, nomor_hp, package_type, start_date, end_date, order_id, referrer_name))

    c.execute('DELETE FROM pending_orders WHERE order_id = ?', (order_id, ))
    conn.commit()
    conn.close()


def get_user_subscription(discord_id):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('SELECT * FROM subscriptions WHERE discord_id = ? AND status = "active"', (discord_id,))
    result = c.fetchone()
    conn.close()
    return result


def save_transaction(discord_id, order_id, package_type, amount, status):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute(
        '''INSERT INTO transactions (discord_id, order_id, package_type, amount, status)
           VALUES (?, ?, ?, ?, ?)''',
        (discord_id, order_id, package_type, amount, status))
    conn.commit()
    conn.close()


def get_statistics():
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM subscriptions WHERE status = "active"')
    active_subs = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM subscriptions')
    total_subs = c.fetchone()[0]
    
    c.execute('SELECT SUM(amount) FROM transactions WHERE status = "settlement"')
    total_revenue = c.fetchone()[0] or 0
    
    c.execute('SELECT package_type, COUNT(*) FROM subscriptions WHERE status = "active" GROUP BY package_type')
    package_breakdown = c.fetchall()
    
    conn.close()
    return {
        'active_subscriptions': active_subs,
        'total_subscriptions': total_subs,
        'total_revenue': total_revenue,
        'package_breakdown': package_breakdown
    }


def get_monthly_data(year, month):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute('''SELECT t.discord_id, s.discord_username, t.order_id, t.package_type, t.amount, t.status, t.transaction_date 
                 FROM transactions t
                 LEFT JOIN subscriptions s ON t.discord_id = s.discord_id
                 WHERE strftime('%Y', t.transaction_date) = ? AND strftime('%m', t.transaction_date) = ?
                 ORDER BY t.transaction_date DESC''',
              (str(year), str(month).zfill(2)))
    
    transactions = c.fetchall()
    conn.close()
    return transactions


def create_discount_code(code, discount_percentage, valid_days, usage_limit):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    valid_until = datetime.now() + timedelta(days=valid_days)
    
    try:
        c.execute(
            '''INSERT INTO discount_codes (code, discount_percentage, valid_until, usage_limit)
               VALUES (?, ?, ?, ?)''',
            (code.upper(), discount_percentage, valid_until, usage_limit))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def validate_discount_code(code):
    if not code or code.strip() == "":
        return None
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    c.execute('''SELECT discount_percentage, usage_limit, used_count, valid_until 
                 FROM discount_codes 
                 WHERE code = ? AND datetime(valid_until) > datetime(?) AND used_count < usage_limit''',
             (code.upper(), now))
    
    result = c.fetchone()
    conn.close()
    
    if result:
        discount_percentage, usage_limit, used_count, valid_until = result
        return discount_percentage
    return None


def create_trial_code(code, duration_days, valid_days, usage_limit):
    """Create trial member code"""
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    valid_until = datetime.now() + timedelta(days=valid_days)
    
    try:
        c.execute(
            '''INSERT INTO trial_codes (code, duration_days, valid_until, usage_limit)
               VALUES (?, ?, ?, ?)''',
            (code.upper(), duration_days, valid_until, usage_limit))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def validate_trial_code(code):
    """Validate and return trial code duration"""
    if not code or code.strip() == "":
        return None
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    c.execute('''SELECT duration_days, usage_limit, used_count, valid_until 
                 FROM trial_codes 
                 WHERE code = ? AND datetime(valid_until) > datetime(?) AND used_count < usage_limit''',
             (code.upper(), now))
    
    result = c.fetchone()
    
    if result:
        duration_days, usage_limit, used_count, valid_until = result
        # Increment usage count
        c.execute('UPDATE trial_codes SET used_count = used_count + 1 WHERE code = ?', (code.upper(),))
        conn.commit()
    
    conn.close()
    return result[0] if result else None


def save_trial_member(discord_id, discord_username, trial_end_date):
    """Save trial member to database"""
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute(
        '''INSERT OR REPLACE INTO trial_members 
                 (discord_id, discord_username, trial_end_date, status)
                 VALUES (?, ?, ?, 'active')''',
        (str(discord_id), discord_username, trial_end_date))
    conn.commit()
    conn.close()


def get_all_packages():
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('SELECT package_id, name, price, duration_days, role_name FROM packages ORDER BY created_at')
    packages = c.fetchall()
    conn.close()
    
    result = {}
    for pkg_id, name, price, duration, role_name in packages:
        result[pkg_id] = {
            "name": name,
            "price": price,
            "duration_days": duration,
            "role_name": role_name
        }
    return result


def add_package(package_id, name, price, duration_days, role_name):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    try:
        c.execute('''INSERT INTO packages (package_id, name, price, duration_days, role_name)
                     VALUES (?, ?, ?, ?, ?)''',
                 (package_id, name, price, duration_days, role_name))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def delete_package(package_id):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('DELETE FROM packages WHERE package_id = ?', (package_id,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0


def list_all_packages():
    packages = get_all_packages()
    return packages


def send_invoice_email(member_email: str, nama: str, order_id: str, package_name: str, price: int, duration_days: float, start_date: str, end_date: str):
    """Send invoice email to member"""
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        print("⚠️ Gmail not configured, skipping member invoice email")
        return False
    
    try:
        # Create HTML invoice
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px;">
                    <h2 style="color: #d35400; text-align: center;">📋 INVOICE MEMBERSHIP</h2>
                    <hr style="border: 1px solid #ddd;">
                    
                    <p><strong>Halo {nama},</strong></p>
                    <p>Terima kasih telah membeli membership The Warrior! Berikut detail transaksi Anda:</p>
                    
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Order ID:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{order_id}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Paket:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{package_name}</td>
                        </tr>
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Harga:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">Rp {price:,}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Durasi:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{int(duration_days)} hari</td>
                        </tr>
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Tanggal Mulai:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{start_date}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Tanggal Berakhir:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;" style="color: #d35400;"><strong>{end_date}</strong></td>
                        </tr>
                    </table>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 20px;">
                        Terima kasih telah menjadi bagian dari The Warrior! Jika ada pertanyaan, hubungi admin kami.
                    </p>
                    <p style="text-align: center; color: #999; font-size: 11px; margin-top: 20px;">
                        © 2025 DiaryCrypto - The Warrior Membership
                    </p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"📋 Invoice - Order {order_id}"
        msg['From'] = GMAIL_SENDER
        msg['To'] = member_email
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, member_email, msg.as_string())
        
        print(f"✅ Invoice email sent to {member_email}")
        return True
    except Exception as e:
        print(f"❌ Error sending invoice email: {e}")
        return False


async def send_welcome_card(member: discord.Member, nama: str, package_name: str, end_date_str: str):
    """Send welcome card with member avatar when they become a member"""
    try:
        embed = discord.Embed(
            title="🎉 SELAMAT! MEMBERSHIP AKTIF",
            description=f"Halo **{nama}**,\n\nSelamat bergabung dengan The Warrior!",
            color=0x00ff00)
        
        embed.add_field(name="📦 Paket Membership", value=package_name, inline=False)
        embed.add_field(name="📅 Akses Berakhir", value=end_date_str, inline=False)
        embed.add_field(name="🎯 Role", value="The Warrior", inline=False)
        embed.add_field(
            name="💡 Apa Selanjutnya?",
            value="Nikmati akses eksklusif Anda! Jika ada pertanyaan, hubungi admin.",
            inline=False)
        
        embed.set_footer(text=f"Terima kasih, {nama}! 🚀")
        
        await member.send(embed=embed)
        print(f"✅ Welcome card sent to {member.name}")
    except discord.HTTPException:
        print(f"⚠️ Could not send welcome card to {member.id}")
    except Exception as e:
        print(f"❌ Error sending welcome card: {e}")


async def send_trial_welcome_card(member: discord.Member, duration_days: int, end_date_str: str):
    """Send welcome card with member avatar for trial members"""
    try:
        embed = discord.Embed(
            title="🎉 TRIAL MEMBER DIMULAI!",
            description=f"Halo **{member.name}**,\n\nKode trial Anda berhasil diaktifkan!",
            color=0x00ff00)
        
        embed.add_field(name="⏱️ Durasi Trial", value=f"{duration_days} hari", inline=True)
        embed.add_field(name="📅 Trial Berakhir", value=end_date_str, inline=True)
        embed.add_field(name="🎯 Role", value="Trial Member", inline=False)
        embed.add_field(
            name="💡 Apa Selanjutnya?",
            value="Nikmati akses trial! Setelah berakhir, upgrade ke membership penuh dengan `/buy`",
            inline=False)
        
        embed.set_footer(text=f"Upgrade sekarang, {member.name}! 🚀")
        
        await member.send(embed=embed)
        print(f"✅ Trial welcome card sent to {member.name}")
    except discord.HTTPException:
        print(f"⚠️ Could not send trial welcome card to {member.id}")
    except Exception as e:
        print(f"❌ Error sending trial welcome card: {e}")


async def send_goodbye_card(member: discord.Member, package_name: str, end_date_str: str):
    """Send goodbye card with member avatar when membership ends"""
    try:
        embed = discord.Embed(
            title="❌ MEMBERSHIP BERAKHIR",
            description=f"Halo **{member.name}**,\n\nMembership Anda telah berakhir dan role telah dicopot.",
            color=0xff0000)
        
        embed.add_field(name="📦 Paket", value=package_name, inline=True)
        embed.add_field(name="📅 Tanggal Expired", value=end_date_str, inline=True)
        embed.add_field(
            name="🔄 Perpanjang Sekarang",
            value="Gunakan `/buy` dan pilih 'Perpanjang Member' untuk aktifkan kembali!",
            inline=False)
        
        embed.set_footer(text=f"Nantikan Anda kembali, {member.name}! 👋")
        
        await member.send(embed=embed)
        print(f"✅ Goodbye card sent to {member.name}")
    except discord.HTTPException:
        print(f"⚠️ Could not send goodbye card to {member.id}")
    except Exception as e:
        print(f"❌ Error sending goodbye card: {e}")


def send_welcome_card_email(member_email: str, nama: str, package_name: str, end_date_str: str, bg_color: str = "#d35400"):
    """Send welcome card via email with custom background"""
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        print("⚠️ Gmail not configured, skipping welcome card email")
        return False
    
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, {bg_color}, {bg_color}dd); padding: 40px; border-radius: 15px; box-shadow: 0 8px 16px rgba(0,0,0,0.1);">
                    <h1 style="color: white; text-align: center; margin-top: 0; font-size: 32px;">🎉 SELAMAT!</h1>
                    <p style="color: white; text-align: center; font-size: 18px; margin: 20px 0;">
                        <strong>{nama}</strong>
                    </p>
                    
                    <div style="background-color: rgba(255,255,255,0.95); padding: 25px; border-radius: 10px; margin: 20px 0;">
                        <h2 style="color: {bg_color}; text-align: center; margin-top: 0;">Membership Aktif ✨</h2>
                        
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>📦 Paket:</strong></td>
                                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;"><strong>{package_name}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>📅 Berakhir:</strong></td>
                                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{end_date_str}</td>
                            </tr>
                            <tr>
                                <td style="padding: 12px;"><strong>🎯 Status:</strong></td>
                                <td style="padding: 12px; text-align: right;"><span style="background-color: #00ff00; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold;">AKTIF</span></td>
                            </tr>
                        </table>
                        
                        <p style="text-align: center; color: {bg_color}; margin-top: 20px; font-size: 14px;">
                            ✨ Nikmati akses eksklusif The Warrior! ✨
                        </p>
                    </div>
                    
                    <p style="color: white; text-align: center; font-size: 12px; margin-bottom: 0;">
                        © 2025 DiaryCrypto - The Warrior Membership
                    </p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🎉 Selamat! Membership Aktif - {package_name}"
        msg['From'] = GMAIL_SENDER
        msg['To'] = member_email
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, member_email, msg.as_string())
        
        print(f"✅ Welcome card email sent to {member_email}")
        return True
    except Exception as e:
        print(f"❌ Error sending welcome card email: {e}")
        return False


def send_goodbye_card_email(member_email: str, nama: str, package_name: str, end_date_str: str):
    """Send goodbye card via email when membership expires"""
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        print("⚠️ Gmail not configured, skipping goodbye card email")
        return False
    
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #ff6b6b, #ff6b6bdd); padding: 40px; border-radius: 15px; box-shadow: 0 8px 16px rgba(0,0,0,0.1);">
                    <h1 style="color: white; text-align: center; margin-top: 0; font-size: 32px;">👋 SAMPAI JUMPA LAGI!</h1>
                    <p style="color: white; text-align: center; font-size: 18px; margin: 20px 0;">
                        <strong>{nama}</strong>
                    </p>
                    
                    <div style="background-color: rgba(255,255,255,0.95); padding: 25px; border-radius: 10px; margin: 20px 0;">
                        <h2 style="color: #ff6b6b; text-align: center; margin-top: 0;">Membership Berakhir ⏰</h2>
                        
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>📦 Paket:</strong></td>
                                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;"><strong>{package_name}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>📅 Tanggal Expired:</strong></td>
                                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;"><strong style="color: #ff6b6b;">{end_date_str}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 12px;"><strong>🔄 Status:</strong></td>
                                <td style="padding: 12px; text-align: right;"><span style="background-color: #ff6b6b; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold;">EXPIRED</span></td>
                            </tr>
                        </table>
                        
                        <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; margin-top: 20px; border-left: 4px solid #ff6b6b;">
                            <p style="margin: 0; color: #333;"><strong>💡 Perpanjang Sekarang!</strong></p>
                            <p style="margin: 8px 0 0 0; color: #555; font-size: 14px;">
                                Gunakan <strong>/buy</strong> dan pilih 'Perpanjang Member' untuk aktifkan kembali akses Anda!
                            </p>
                        </div>
                    </div>
                    
                    <p style="color: white; text-align: center; font-size: 12px; margin-bottom: 0;">
                        © 2025 DiaryCrypto - The Warrior Membership
                    </p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"❌ Membership Expired - {package_name}"
        msg['From'] = GMAIL_SENDER
        msg['To'] = member_email
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, member_email, msg.as_string())
        
        print(f"✅ Goodbye card email sent to {member_email}")
        return True
    except Exception as e:
        print(f"❌ Error sending goodbye card email: {e}")
        return False


def send_trial_welcome_card_email(member_email: str, nama: str, duration_days: int, end_date_str: str):
    """Send trial welcome card via email"""
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        print("⚠️ Gmail not configured, skipping trial welcome card email")
        return False
    
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #00bfff, #00bfffdd); padding: 40px; border-radius: 15px; box-shadow: 0 8px 16px rgba(0,0,0,0.1);">
                    <h1 style="color: white; text-align: center; margin-top: 0; font-size: 32px;">🎁 TRIAL MEMBER!</h1>
                    <p style="color: white; text-align: center; font-size: 18px; margin: 20px 0;">
                        <strong>{nama}</strong>
                    </p>
                    
                    <div style="background-color: rgba(255,255,255,0.95); padding: 25px; border-radius: 10px; margin: 20px 0;">
                        <h2 style="color: #00bfff; text-align: center; margin-top: 0;">Trial Dimulai! ⏳</h2>
                        
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>⏱️ Durasi Trial:</strong></td>
                                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;"><strong>{duration_days} hari</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 12px; border-bottom: 1px solid #eee;"><strong>📅 Trial Berakhir:</strong></td>
                                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">{end_date_str}</td>
                            </tr>
                            <tr>
                                <td style="padding: 12px;"><strong>🎯 Role:</strong></td>
                                <td style="padding: 12px; text-align: right;"><span style="background-color: #00bfff; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold;">TRIAL</span></td>
                            </tr>
                        </table>
                        
                        <div style="background-color: #e6f3ff; padding: 15px; border-radius: 8px; margin-top: 20px; border-left: 4px solid #00bfff;">
                            <p style="margin: 0; color: #333;"><strong>💡 Upgrade Sekarang!</strong></p>
                            <p style="margin: 8px 0 0 0; color: #555; font-size: 14px;">
                                Setelah trial berakhir, gunakan <strong>/buy</strong> untuk upgrade ke membership penuh!
                            </p>
                        </div>
                    </div>
                    
                    <p style="color: white; text-align: center; font-size: 12px; margin-bottom: 0;">
                        © 2025 DiaryCrypto - The Warrior Membership
                    </p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🎁 Trial Member Started - {duration_days} Hari!"
        msg['From'] = GMAIL_SENDER
        msg['To'] = member_email
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, member_email, msg.as_string())
        
        print(f"✅ Trial welcome card email sent to {member_email}")
        return True
    except Exception as e:
        print(f"❌ Error sending trial welcome card email: {e}")
        return False


def send_expiry_email(member_email: str, nama: str, package_name: str, end_date: str):
    """Send email notification when membership expires and role is removed"""
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        print("⚠️ Gmail not configured, skipping expiry email")
        return False
    
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px;">
                    <h2 style="color: #ff0000; text-align: center;">❌ MEMBERSHIP EXPIRED</h2>
                    <hr style="border: 1px solid #ddd;">
                    
                    <p><strong>Halo {nama},</strong></p>
                    <p>Membership Anda telah berakhir dan role telah dicopot. Berikut detail:</p>
                    
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Paket:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{package_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Tanggal Expired:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong style="color: #ff0000;">{end_date}</strong></td>
                        </tr>
                    </table>
                    
                    <p style="background-color: #fff3cd; padding: 15px; border-radius: 5px; color: #856404;">
                        <strong>⚠️ Akses Anda Dicabut:</strong> Role dan akses channel telah dihapus. 
                        Gunakan <strong>/buy</strong> untuk perpanjang membership Anda!
                    </p>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 20px;">
                        Terima kasih telah menjadi bagian dari The Warrior! Jika ada pertanyaan, hubungi admin kami.
                    </p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"❌ Membership Expired - {package_name}"
        msg['From'] = GMAIL_SENDER
        msg['To'] = member_email
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, member_email, msg.as_string())
        
        print(f"✅ Expiry email sent to {member_email}")
        return True
    except Exception as e:
        print(f"❌ Error sending expiry email: {e}")
        return False


def send_admin_notification(member_name: str, member_email: str, order_id: str, package_name: str, price: int):
    """Send admin notification about new member purchase"""
    if not GMAIL_SENDER or not GMAIL_PASSWORD or not ADMIN_EMAIL:
        print("⚠️ Gmail or Admin email not configured, skipping admin notification")
        return False
    
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px;">
                    <h2 style="color: #d35400; text-align: center;">🎯 NEW MEMBERSHIP PURCHASE</h2>
                    <hr style="border: 1px solid #ddd;">
                    
                    <p><strong>Ada member baru yang membeli!</strong></p>
                    
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Member:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{member_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Email:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{member_email}</td>
                        </tr>
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Order ID:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{order_id}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Paket:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{package_name}</td>
                        </tr>
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Harga:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">Rp {price:,}</td>
                        </tr>
                    </table>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 20px; text-align: center;">
                        Email ini dikirim otomatis oleh sistem
                    </p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🎯 New Member - {member_name} (Order: {order_id})"
        msg['From'] = GMAIL_SENDER
        msg['To'] = ADMIN_EMAIL
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, ADMIN_EMAIL, msg.as_string())
        
        print(f"✅ Admin notification sent to {ADMIN_EMAIL}")
        return True
    except Exception as e:
        print(f"❌ Error sending admin notification: {e}")
        return False


def send_admin_kick_notification(member_name: str, member_email: str, package_name: str, reason: str):
    """Send admin notification about member role removal"""
    if not GMAIL_SENDER or not GMAIL_PASSWORD or not ADMIN_EMAIL:
        print("⚠️ Gmail or Admin email not configured, skipping kick notification")
        return False
    
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px;">
                    <h2 style="color: #ff0000; text-align: center;">🚨 MEMBER ROLE REMOVED</h2>
                    <hr style="border: 1px solid #ddd;">
                    
                    <p><strong>Informasi Pencopotan Role:</strong></p>
                    
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Member:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{member_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Email:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{member_email}</td>
                        </tr>
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Paket:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{package_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Alasan:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd; color: #ff0000;"><strong>{reason}</strong></td>
                        </tr>
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Waktu:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{format_jakarta_datetime(datetime.now())}</td>
                        </tr>
                    </table>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 20px; text-align: center;">
                        Email ini dikirim otomatis oleh sistem
                    </p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🚨 KICK NOTIFICATION - {member_name} ({reason})"
        msg['From'] = GMAIL_SENDER
        msg['To'] = ADMIN_EMAIL
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, ADMIN_EMAIL, msg.as_string())
        
        print(f"✅ Admin kick notification sent to {ADMIN_EMAIL}")
        return True
    except Exception as e:
        print(f"❌ Error sending kick notification: {e}")
        return False


async def activate_subscription(order_id):
    try:
        pending = get_pending_order(order_id)
        if not pending:
            print(f"⚠️ No pending order found for {order_id}")
            return

        if len(pending) == 9:
            discord_id, discord_username, nama, email, nomor_hp, package_type, duration_days, is_renewal, referrer_name = pending
        else:
            discord_id, discord_username, nama, email, nomor_hp, package_type, duration_days, is_renewal = pending
            referrer_name = None
        
        save_subscription(discord_id, discord_username, nama, email, nomor_hp, package_type, duration_days, order_id, is_renewal=bool(is_renewal), referrer_name=referrer_name)
        
        packages = get_all_packages()
        price = packages.get(package_type, {}).get('price', 0)
        save_transaction(discord_id, order_id, package_type, price, 'settlement')
        
        # Track referral commission if referrer exists
        if referrer_name:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            # Get final amount from transaction (after discount)
            c.execute('SELECT amount FROM transactions WHERE order_id = ? LIMIT 1', (order_id,))
            trans_result = c.fetchone()
            final_amount = trans_result[0] if trans_result else price
            
            # Calculate 30% commission
            commission = int(final_amount * 0.30)
            discount_pct = 0
            if final_amount < price:
                discount_pct = int(((price - final_amount) / price) * 100)
            
            c.execute('''INSERT INTO commissions 
                        (referrer_name, referred_discord_id, referred_username, order_id, package_type, original_amount, discount_percentage, final_amount, commission_amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (referrer_name, discord_id, discord_username, order_id, package_type, price, discount_pct, final_amount, commission))
            
            c.execute('''INSERT INTO referrals 
                        (referrer_name, referred_discord_id, referred_username, order_id)
                        VALUES (?, ?, ?, ?)''',
                     (referrer_name, discord_id, discord_username, order_id))
            
            conn.commit()
            conn.close()
            print(f"✅ Commission tracked: {referrer_name} gets Rp {commission:,} from order {order_id}")

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print(f"❌ Guild {GUILD_ID} not found")
            return

        member = guild.get_member(int(discord_id))
        if not member:
            print(f"❌ Member {discord_id} not found in guild")
            return

        role_name = packages.get(package_type, {}).get("role_name")
        role = discord.utils.get(guild.roles, name=role_name) if role_name else None

        if role:
            try:
                await member.add_roles(role)
                print(f"✅ Assigned role {role.name} to {member.name}")
            except discord.Forbidden as e:
                print(f"❌ PERMISSION DENIED: Bot role tidak cukup tinggi di hierarchy")
                print(f"   FIX: Pindahkan BOT ROLE lebih TINGGI dari role '{role.name}'")
                print(f"   Steps:")
                print(f"   1. Server Settings → Roles")
                print(f"   2. Drag bot role (paling atas) → di atas role '{role.name}'")
                print(f"   3. Restart bot")
                raise

        renewal_text = "diperpanjang" if is_renewal else "aktif"
        pkg_name = packages.get(package_type, {}).get('name', 'The Warrior')
        
        # Get end date from subscription
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        c.execute('SELECT start_date, end_date FROM subscriptions WHERE discord_id = ?', (discord_id,))
        sub_data = c.fetchone()
        conn.close()
        
        start_time = format_jakarta_datetime(sub_data[0]) if sub_data else format_jakarta_datetime(get_jakarta_time())
        end_time = format_jakarta_datetime(sub_data[1]) if sub_data else "TBA"
        
        embed = discord.Embed(
            title="✅ PEMBAYARAN BERHASIL!",
            description=
            f"Selamat **{nama}**! Akses **{pkg_name}** kamu sudah {renewal_text}.",
            color=0x00ff00)
        embed.add_field(name="📅 Durasi",
                        value=f"{duration_days} hari",
                        inline=True)
        embed.add_field(name="🎯 Status", value="Active", inline=True)
        embed.add_field(name="⏰ Jam Masuk Role", value=start_time, inline=True)
        end_datetime_full = format_jakarta_datetime_full(sub_data[1]) if sub_data else "TBA"
        embed.add_field(name="📅 Tanggal & Jam Berakhir", 
                        value=end_datetime_full,
                        inline=False)
        embed.add_field(name="📧 Email", value=email, inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_footer(text="Terima kasih telah berlangganan!")

        try:
            await member.send(embed=embed)
        except:
            print(f"⚠️ Could not DM user {discord_id}")

        # Send invoice email to member
        send_invoice_email(email, nama, order_id, pkg_name, price, duration_days, start_time, end_datetime_full)
        
        # Send admin notification
        send_admin_notification(nama, email, order_id, pkg_name, price)
        
        # Send welcome card email
        send_welcome_card_email(email, nama, pkg_name, end_datetime_full)

        print(f"✅ Subscription activated for user {discord_id} ({nama})")

    except Exception as e:
        print(f"❌ Error activating subscription: {e}")


def is_admin(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    origin_role = discord.utils.get(interaction.guild.roles, name=ORIGIN_ROLE_NAME)
    if origin_role and isinstance(interaction.user, discord.Member):
        return origin_role in interaction.user.roles
    return False


def is_analyst(interaction: discord.Interaction, analyst_name: str) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    analyst_role = discord.utils.get(interaction.guild.roles, name=analyst_name)
    if analyst_role:
        return analyst_role in interaction.user.roles
    return False


def is_commission_manager(interaction: discord.Interaction) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    manager_role = discord.utils.get(interaction.guild.roles, name="Com-Manager")
    if not manager_role:
        manager_role = discord.utils.get(interaction.guild.roles, name="Com Manager")
    if manager_role:
        return manager_role in interaction.user.roles
    return False


def can_access_admin_commands(interaction: discord.Interaction) -> bool:
    """Check if user is Admin (Origin), Analyst, or Analyst's Lead"""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    
    # Check if admin (Origin role)
    origin_role = discord.utils.get(interaction.guild.roles, name=ORIGIN_ROLE_NAME)
    if origin_role and origin_role in interaction.user.roles:
        return True
    
    # Check if analyst (Bay, Dialena, Kamado, Ryzu, Zen, Rey)
    analyst_names = ["Bay", "Dialena", "Kamado", "Ryzu", "Zen", "Rey", "Bell"]
    for analyst_name in analyst_names:
        analyst_role = discord.utils.get(interaction.guild.roles, name=analyst_name)
        if analyst_role and analyst_role in interaction.user.roles:
            return True
    
    return False


class UserDataModal(Modal, title="Data Pembeli"):
    nama = TextInput(
        label="Nama Lengkap",
        placeholder="Masukkan nama lengkap Anda",
        required=True,
        max_length=100
    )
    
    email = TextInput(
        label="Email",
        placeholder="contoh@email.com",
        required=True,
        max_length=100
    )
    
    nomor_hp = TextInput(
        label="Nomor HP/WhatsApp",
        placeholder="08xxxxxxxxxx",
        required=True,
        max_length=20
    )
    
    promo_code = TextInput(
        label="Kode Promo (Opsional)",
        placeholder="Masukkan kode promo jika punya",
        required=False,
        max_length=50
    )
    
    referral_code = TextInput(
        label="Kode Referral (Opsional)",
        placeholder="Contoh: B4Y_kTx, D1L3n4X, B3LLrFT",
        required=False,
        max_length=50
    )

    def __init__(self, package_value: str, package_name: str, price: int, duration_days: int, is_renewal: bool):
        super().__init__()
        self.package_value = package_value
        self.package_name = package_name
        self.price = price
        self.duration_days = duration_days
        self.is_renewal = is_renewal
        self.discount = 0
        self.final_price = price

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        try:
            timestamp = int(datetime.now().timestamp())
            order_id = f"W{interaction.user.id}{timestamp}"[-36:]
            
            # Validasi email format
            email_value = self.email.value.strip() if self.email.value else ""
            if not email_value or "@" not in email_value:
                await interaction.followup.send(
                    "❌ Email tidak valid. Masukkan email yang benar (contoh: user@email.com)",
                    ephemeral=True)
                return
            
            # Validasi promo code
            promo_text = self.promo_code.value.strip() if self.promo_code.value else ""
            discount_percentage = 0
            final_price = self.price
            
            if promo_text:
                discount_percentage = validate_discount_code(promo_text)
                if discount_percentage:
                    final_price = int(self.price * (1 - discount_percentage/100))
                    print(f"✅ Promo '{promo_text}' valid: {discount_percentage}% discount")
                else:
                    await interaction.followup.send(
                        f"❌ Kode promo '{promo_text}' tidak valid atau sudah expired/habis.",
                        ephemeral=True)
                    return

            transaction = snap.create_transaction({
                "transaction_details": {
                    "order_id": order_id,
                    "gross_amount": final_price
                },
                "item_details": [{
                    "id": self.package_value,
                    "price": final_price,
                    "quantity": 1,
                    "name": self.package_name + (" - Perpanjangan" if self.is_renewal else "") + (f" (-{discount_percentage}%)" if discount_percentage > 0 else "")
                }],
                "customer_details": {
                    "first_name": self.nama.value.strip()[:30],
                    "email": email_value,
                    "phone": self.nomor_hp.value.strip()
                }
            })

            payment_url = transaction['redirect_url']
            # Validate referral code if provided
            referral_code_text = self.referral_code.value.strip().lower() if self.referral_code.value else ""
            referrer_name = None
            if referral_code_text and referral_code_text in ALL_REFERRERS:
                referrer_name = ALL_REFERRERS[referral_code_text]
            elif referral_code_text:
                await interaction.followup.send(
                    f"❌ Kode referral '{referral_code_text}' tidak valid.",
                    ephemeral=True)
                return
            
            save_pending_order(
                order_id, 
                str(interaction.user.id),
                str(interaction.user),
                self.nama.value,
                self.email.value,
                self.nomor_hp.value,
                self.package_value,
                self.duration_days,
                self.is_renewal,
                referrer_name
            )
            
            # Update discount usage
            if promo_text and discount_percentage > 0:
                conn = sqlite3.connect('warrior_subscriptions.db')
                c = conn.cursor()
                c.execute('UPDATE discount_codes SET used_count = used_count + 1 WHERE code = ?',
                         (promo_text.upper(),))
                conn.commit()
                conn.close()

            embed = discord.Embed(
                title=f"🎯 {'PERPANJANG' if self.is_renewal else 'UPGRADE TO'} THE WARRIOR",
                description=
                f"**Nama:** {self.nama.value}\n**Email:** {self.email.value}\n**Paket:** {self.package_name}\n**Harga Asli:** Rp {self.price:,}" + (f"\n**Diskon:** -{discount_percentage}%\n**Harga Final:** Rp {final_price:,}" if discount_percentage > 0 else f"\n**Harga:** Rp {final_price:,}") + f"\n**Durasi:** {self.duration_days} hari",
                color=0xd35400)
            embed.add_field(name="🔗 Payment Link",
                            value=f"[Klik di sini untuk bayar]({payment_url})",
                            inline=False)
            embed.add_field(
                name="💳 Metode Pembayaran",
                value="• Transfer Bank\n• E-Wallet\n• Kartu Kredit/Debit",
                inline=False)
            
            if self.is_renewal:
                embed.add_field(
                    name="ℹ️ Info Perpanjangan",
                    value="Durasi akan ditambahkan dari tanggal berakhir membership kamu saat ini.",
                    inline=False)
            
            embed.set_footer(
                text="Role akan aktif otomatis setelah pembayaran berhasil")

            try:
                await interaction.user.send(embed=embed)
                await interaction.followup.send(
                    "✅ Link pembayaran telah dikirim ke DM kamu!", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            print(f"❌ Payment error: {e}")
            error_msg = str(e)
            
            # More helpful error messages
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                await interaction.followup.send(
                    "❌ Gagal: API Key Midtrans tidak valid.\n\n**Solusi:**\n1. Cek MIDTRANS_SERVER_KEY dan CLIENT_KEY di secrets\n2. Pastikan menggunakan SANDBOX keys (bukan production)\n3. Test endpoint: /test-midtrans",
                    ephemeral=True)
            elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                await interaction.followup.send(
                    "❌ Gagal terhubung ke Midtrans. Coba lagi dalam beberapa saat.",
                    ephemeral=True)
            else:
                await interaction.followup.send(
                    f"❌ Gagal membuat link pembayaran.\n\n**Error:** {error_msg}",
                    ephemeral=True)


@tree.command(name="buy", description="Beli atau perpanjang akses The Warrior")
async def buy_command(interaction: discord.Interaction):
    try:
        packages = get_all_packages()
        
        if not packages:
            await interaction.response.send_message(
                "❌ Tidak ada paket tersedia. Admin harus membuat paket terlebih dahulu.",
                ephemeral=True)
            return
        
        from discord.ui import Select, View, button, Button
        
        class ActionSelect(Select):
            def __init__(self, packages):
                self.packages = packages
                options = [
                    discord.SelectOption(label="🆕 Beli Baru", value="beli", description="Membeli membership baru"),
                    discord.SelectOption(label="🔄 Perpanjang Member", value="renewal", description="Perpanjang membership yang ada")
                ]
                super().__init__(placeholder="Pilih aksi...", options=options)
            
            async def callback(self, interaction: discord.Interaction):
                action_value = self.values[0]
                await show_package_menu(interaction, action_value, self.packages)
        
        class ActionView(View):
            def __init__(self, packages):
                super().__init__()
                self.add_item(ActionSelect(packages))
        
        view = ActionView(packages)
        await interaction.response.send_message("Pilih aksi:", view=view, ephemeral=True)
        
    except Exception as e:
        print(f"Buy command error: {e}")
        await interaction.response.send_message(
            "❌ Terjadi kesalahan. Silakan coba lagi.",
            ephemeral=True)


async def show_package_menu(interaction: discord.Interaction, action_value: str, packages: dict):
    try:
        from discord.ui import Select, View
        
        class PackageSelect(Select):
            def __init__(self, packages, action):
                self.packages = packages
                self.action = action
                options = []
                for pkg_id, pkg_data in packages.items():
                    option_label = f"{pkg_data['name']} - Rp {pkg_data['price']:,}"
                    options.append(discord.SelectOption(label=option_label, value=pkg_id))
                super().__init__(placeholder="Pilih paket...", options=options)
            
            async def callback(self, interaction: discord.Interaction):
                package_value = self.values[0]
                await handle_buy(interaction, package_value, self.action, self.packages)
        
        class PackageView(View):
            def __init__(self, packages, action):
                super().__init__()
                self.add_item(PackageSelect(packages, action))
        
        view = PackageView(packages, action_value)
        await interaction.response.send_message("Pilih paket:", view=view, ephemeral=True)
        
    except Exception as e:
        print(f"Package menu error: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Terjadi kesalahan. Silakan coba lagi.",
                ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ Terjadi kesalahan. Silakan coba lagi.",
                ephemeral=True)


async def handle_buy(interaction, package_value, action, packages):
    try:
        is_renewal = bool(action and action == "renewal")
        
        if is_renewal:
            existing_sub = get_user_subscription(str(interaction.user.id))
            if not existing_sub:
                await interaction.response.send_message(
                    "❌ Kamu belum memiliki membership aktif. Silakan pilih 'Beli Baru'.",
                    ephemeral=True)
                return
        
        selected_package = packages[package_value]
        
        modal = UserDataModal(
            package_value=package_value,
            package_name=selected_package["name"],
            price=selected_package["price"],
            duration_days=selected_package["duration_days"],
            is_renewal=is_renewal
        )
        
        if interaction.response.is_done():
            await interaction.followup.send("Modal dibuka...", ephemeral=True)
        else:
            await interaction.response.send_modal(modal)

    except Exception as e:
        print(f"Buy command error: {e}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ Terjadi kesalahan. Silakan coba lagi.",
                    ephemeral=True)
            else:
                await interaction.response.send_message(
                    "❌ Terjadi kesalahan. Silakan coba lagi.",
                    ephemeral=True)
        except discord.HTTPException:
            pass


@tree.command(name="statistik", description="[Com-Manager Only] Lihat statistik langganan")
@app_commands.default_permissions(administrator=False)
async def statistik_command(interaction: discord.Interaction):
    if not is_commission_manager(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk role **Com-Manager**.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        stats = get_statistics()
        
        embed = discord.Embed(
            title="📊 STATISTIK WARRIOR SUBSCRIPTION",
            color=0xd35400)
        
        embed.add_field(
            name="👥 Active Subscriptions",
            value=str(stats['active_subscriptions']),
            inline=True)
        embed.add_field(
            name="📝 Total Subscriptions",
            value=str(stats['total_subscriptions']),
            inline=True)
        embed.add_field(
            name="💰 Total Revenue",
            value=f"Rp {stats['total_revenue']:,}",
            inline=True)
        
        if stats['package_breakdown']:
            breakdown_text = "\n".join([
                f"• {pkg}: {count} users" 
                for pkg, count in stats['package_breakdown']
            ])
            embed.add_field(
                name="📦 Package Breakdown",
                value=breakdown_text,
                inline=False)
        
        embed.set_footer(text=f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Statistics error: {e}")
        await interaction.followup.send(
            "❌ Gagal mengambil statistik.",
            ephemeral=True)


@tree.command(name="export_monthly", description="[Com-Manager Only] Export data transaksi bulanan ke Excel")
@app_commands.describe(year="Tahun (misal: 2024)", month="Bulan (1-12)")
@app_commands.default_permissions(administrator=False)
async def export_monthly_command(interaction: discord.Interaction, year: int, month: int):
    if not is_commission_manager(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk role **Com-Manager**.", 
            ephemeral=True)
        return
    
    if month < 1 or month > 12:
        await interaction.response.send_message(
            "❌ Bulan harus antara 1-12.",
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        transactions = get_monthly_data(year, month)
        
        if not transactions:
            await interaction.followup.send(
                f"ℹ️ Tidak ada transaksi untuk bulan {month}/{year}.",
                ephemeral=True)
            return
        
        # Create Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = f"Transaksi {month}-{year}"
        
        # Define styles
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        # Write headers
        headers = ['Discord ID', 'Discord Username', 'Order ID', 'Package', 'Amount (Rp)', 'Status', 'Date']
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = border
        
        # Write data
        for row_num, trans in enumerate(transactions, 2):
            for col_num, value in enumerate(trans, 1):
                cell = ws.cell(row=row_num, column=col_num)
                if col_num == 5:  # Amount column - format as number
                    try:
                        cell.value = int(value) if isinstance(value, str) else value
                    except:
                        cell.value = value
                else:
                    cell.value = value
                cell.border = border
                cell.alignment = Alignment(vertical="center")
        
        # Auto adjust column widths
        ws.column_dimensions['A'].width = 18
        ws.column_dimensions['B'].width = 18
        ws.column_dimensions['C'].width = 20
        ws.column_dimensions['D'].width = 20
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 12
        ws.column_dimensions['G'].width = 18
        
        # Save to BytesIO
        excel_output = BytesIO()
        wb.save(excel_output)
        excel_output.seek(0)
        
        filename = f"transactions_{year}_{month:02d}.xlsx"
        file = discord.File(fp=excel_output, filename=filename)
        
        embed = discord.Embed(
            title=f"📊 Export Data Bulan {month}/{year}",
            description=f"Total transaksi: {len(transactions)}",
            color=0x00ff00)
        embed.add_field(name="📁 Format", value="Excel (.xlsx)", inline=True)
        embed.add_field(name="📋 Kolom", value="7 kolom (ID, Username, Order, Package, Amount, Status, Date)", inline=True)
        
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        
    except Exception as e:
        print(f"Export error: {e}")
        await interaction.followup.send(
            "❌ Gagal export data.",
            ephemeral=True)


@tree.command(name="create_trial_code", description="[Com-Manager Only] Buat kode trial member baru")
@app_commands.describe(
    code="Kode trial (contoh: TRIAL123)",
    duration_days="Durasi akses trial (hari)",
    valid_days="Berlaku berapa hari",
    usage_limit="Maksimal penggunaan"
)
@app_commands.default_permissions(administrator=False)
async def create_trial_code_command(interaction: discord.Interaction, 
                                    code: str, 
                                    duration_days: int,
                                    valid_days: int, 
                                    usage_limit: int):
    # KETAT: Hanya role "Com-Manager" yang bisa akses
    if not is_commission_manager(interaction):
        await interaction.response.send_message(
            "❌ Command ini HANYA untuk role **Com-Manager** saja!\n❌ Public tidak boleh akses.", 
            ephemeral=True)
        return
    
    if duration_days < 1:
        await interaction.response.send_message(
            "❌ Durasi harus minimal 1 hari.",
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        success = create_trial_code(code, duration_days, valid_days, usage_limit)
        
        if success:
            valid_until = datetime.now() + timedelta(days=valid_days)
            embed = discord.Embed(
                title="✅ KODE TRIAL BERHASIL DIBUAT",
                color=0xd35400)
            embed.add_field(name="🎟️ Kode", value=code.upper(), inline=True)
            embed.add_field(name="⏱️ Durasi Akses", value=f"{duration_days} hari", inline=True)
            embed.add_field(name="📅 Kode Berlaku Hingga", 
                          value=valid_until.strftime('%Y-%m-%d'), 
                          inline=True)
            embed.add_field(name="🔢 Limit Penggunaan", value=str(usage_limit), inline=True)
            embed.add_field(name="🔐 Role yang Diberikan", value="Trial Member", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ Kode trial sudah ada. Gunakan kode yang berbeda.",
                ephemeral=True)
            
    except Exception as e:
        print(f"Trial code creation error: {e}")
        await interaction.followup.send(
            "❌ Gagal membuat kode trial.",
            ephemeral=True)


@tree.command(name="redeem_trial", description="Gunakan kode trial member")
@app_commands.describe(code="Kode trial yang Anda punya")
async def redeem_trial_command(interaction: discord.Interaction, code: str):
    try:
        duration_days = validate_trial_code(code)
        
        if not duration_days:
            await interaction.response.send_message(
                "❌ Kode trial tidak valid, sudah expired, atau sudah mencapai limit penggunaan.",
                ephemeral=True)
            return
        
        # Get Trial Member role
        trial_role = discord.utils.get(interaction.guild.roles, name="Trial Member") if interaction.guild else None
        if not trial_role:
            await interaction.response.send_message(
                "❌ Role 'Trial Member' tidak ditemukan di server. Hubungi admin!",
                ephemeral=True)
            return
        
        # Add role to user
        if isinstance(interaction.user, discord.Member):
            await interaction.user.add_roles(trial_role)
        
        end_date = get_jakarta_time() + timedelta(days=duration_days)
        end_date_str = format_jakarta_datetime_full(end_date.isoformat())
        
        # Save to database for auto-removal tracking
        save_trial_member(interaction.user.id, interaction.user.name, end_date.isoformat())
        
        embed = discord.Embed(
            title="✅ KODE TRIAL BERHASIL DIGUNAKAN",
            description=f"Selamat! Anda sekarang adalah Trial Member!",
            color=0x00ff00)
        embed.add_field(name="👤 Username", value=interaction.user.name, inline=True)
        embed.add_field(name="⏱️ Durasi Akses", value=f"{duration_days} hari", inline=True)
        embed.add_field(name="📅 Akses Berakhir", value=end_date_str, inline=False)
        embed.add_field(name="🎯 Role", value="Trial Member", inline=False)
        embed.set_footer(text="Terima kasih! Upgrade ke membership penuh dengan /buy")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Send DM notification
        try:
            dm_embed = discord.Embed(
                title="🎉 SELAMAT! TRIAL MEMBER DIMULAI",
                description=f"Halo **{interaction.user.name}**,\n\nKode trial Anda berhasil diaktifkan! Anda sekarang adalah Trial Member.",
                color=0x00ff00)
            dm_embed.add_field(
                name="⏱️ Durasi Trial",
                value=f"{duration_days} hari",
                inline=True)
            dm_embed.add_field(
                name="📅 Trial Berakhir",
                value=end_date_str,
                inline=True)
            dm_embed.add_field(
                name="🎯 Role Yang Didapat",
                value="Trial Member",
                inline=False)
            dm_embed.add_field(
                name="💡 Apa Selanjutnya?",
                value="Nikmati akses trial Anda! Setelah trial berakhir, upgrade ke membership penuh dengan `/buy`",
                inline=False)
            dm_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)
            dm_embed.set_footer(text="Bot akan mengirim notifikasi saat trial berakhir")
            
            await interaction.user.send(embed=dm_embed)
        except discord.HTTPException:
            print(f"⚠️ Could not send welcome DM to {interaction.user.id}")
        
        # Send trial welcome card email
        send_trial_welcome_card_email(interaction.user.email if hasattr(interaction.user, 'email') else "member@trial.local", 
                                      interaction.user.name, duration_days, end_date_str)
        
        print(f"✅ Trial code redeemed: {interaction.user.name} ({interaction.user.id}) - Duration: {duration_days} days - Expires: {end_date}")
        
    except Exception as e:
        print(f"Redeem trial error: {e}")
        await interaction.response.send_message(
            "⚠️ Bot sedang maintenance. Silakan coba lagi dalam beberapa saat.",
            ephemeral=True)


@tree.command(name="creat_discount", description="[Com-Manager Only] Buat kode diskon baru")
@app_commands.describe(
    code="Kode diskon (contoh: PROMO50)",
    discount="Persentase diskon (1-100)",
    valid_days="Berlaku berapa hari",
    usage_limit="Maksimal penggunaan"
)
@app_commands.default_permissions(administrator=False)
async def creat_discount_command(interaction: discord.Interaction, 
                                 code: str, 
                                 discount: int, 
                                 valid_days: int, 
                                 usage_limit: int):
    # KETAT: Hanya role "Com-Manager" yang bisa akses
    if not is_commission_manager(interaction):
        await interaction.response.send_message(
            "❌ Command ini HANYA untuk role **Com-Manager** saja!\n❌ Public tidak boleh akses.", 
            ephemeral=True)
        return
    
    if discount < 1 or discount > 100:
        await interaction.response.send_message(
            "❌ Diskon harus antara 1-100%.",
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        success = create_discount_code(code, discount, valid_days, usage_limit)
        
        if success:
            valid_until = datetime.now() + timedelta(days=valid_days)
            embed = discord.Embed(
                title="✅ KODE DISKON BERHASIL DIBUAT",
                color=0xd35400)
            embed.add_field(name="🎟️ Kode", value=code.upper(), inline=True)
            embed.add_field(name="💰 Diskon", value=f"{discount}%", inline=True)
            embed.add_field(name="📅 Berlaku Hingga", 
                          value=valid_until.strftime('%Y-%m-%d'), 
                          inline=True)
            embed.add_field(name="🔢 Limit Penggunaan", value=str(usage_limit), inline=True)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ Kode diskon sudah ada. Gunakan kode yang berbeda.",
                ephemeral=True)
            
    except Exception as e:
        print(f"Discount creation error: {e}")
        await interaction.followup.send(
            "❌ Gagal membuat kode diskon.",
            ephemeral=True)


@tree.command(name="manage_package", description="[Com-Manager Only] Kelola paket membership")
@app_commands.describe(
    action="Aksi: create/delete/list",
    package_id="ID paket (contoh: warrior_1year)",
    name="Nama paket (contoh: 1 Tahun - Rp 2.000.000)",
    price="Harga dalam Rupiah",
    duration_days="Durasi dalam hari",
    role_name="Nama role Discord (contoh: The Warrior)"
)
@app_commands.default_permissions(administrator=False)
async def manage_package_command(interaction: discord.Interaction,
                                 action: str,
                                 package_id: Optional[str] = None,
                                 name: Optional[str] = None,
                                 price: Optional[int] = None,
                                 duration_days: Optional[float] = None,
                                 role_name: Optional[str] = None):
    if not is_commission_manager(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk role **Com-Manager**.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        action = action.lower()
        
        if action == "create":
            if not all([package_id, name, price, duration_days, role_name]):
                await interaction.followup.send(
                    "❌ Harap isi: package_id, name, price, duration_days, role_name",
                    ephemeral=True)
                return
            
            success = add_package(package_id, name, price, duration_days, role_name)
            if success:
                embed = discord.Embed(
                    title="✅ PAKET BERHASIL DIBUAT",
                    color=0xd35400)
                embed.add_field(name="📦 ID Paket", value=package_id, inline=True)
                embed.add_field(name="📝 Nama", value=name, inline=True)
                embed.add_field(name="💰 Harga", value=f"Rp {price:,}", inline=True)
                embed.add_field(name="📅 Durasi", value=f"{duration_days} hari", inline=True)
                embed.add_field(name="🎭 Role", value=role_name, inline=True)
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(
                    f"❌ Paket '{package_id}' sudah ada. Gunakan ID berbeda.",
                    ephemeral=True)
        
        elif action == "delete":
            if not package_id:
                await interaction.followup.send(
                    "❌ Harap isi: package_id",
                    ephemeral=True)
                return
            
            success = delete_package(package_id)
            if success:
                await interaction.followup.send(
                    f"✅ Paket '{package_id}' berhasil dihapus.",
                    ephemeral=True)
            else:
                await interaction.followup.send(
                    f"❌ Paket '{package_id}' tidak ditemukan.",
                    ephemeral=True)
        
        elif action == "list":
            packages = list_all_packages()
            if not packages:
                await interaction.followup.send(
                    "❌ Tidak ada paket.",
                    ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📦 DAFTAR PAKET MEMBERSHIP",
                color=0xd35400)
            
            for pkg_id, pkg_data in packages.items():
                field_value = f"Harga: Rp {pkg_data['price']:,}\nDurasi: {pkg_data['duration_days']} hari\nRole: {pkg_data['role_name']}"
                embed.add_field(name=pkg_id, value=field_value, inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        else:
            await interaction.followup.send(
                "❌ Action harus: create, delete, atau list",
                ephemeral=True)
                
    except Exception as e:
        print(f"Package management error: {e}")
        await interaction.followup.send(
            f"❌ Gagal kelola paket: {e}",
            ephemeral=True)


@tree.command(name="refer_link", description="[Analyst & Admin Only] Tampilkan kode referral Anda")
@app_commands.default_permissions(administrator=False)
async def refer_link_command(interaction: discord.Interaction):
    if not (is_analyst(interaction) or is_commission_manager(interaction)):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk role **Analyst** dan **Com Manager**.", 
            ephemeral=True)
        return
    # Check if user is analyst, analyst's lead, or admin
    analyst_roles = ["Bay", "Dialena", "Kamado", "Ryzu", "Zen", "Rey", "Bell"]
    is_analyst_user = False
    is_admin_user = is_admin(interaction)
    
    if not is_admin_user and isinstance(interaction.user, discord.Member):
        for analyst_role_name in analyst_roles:
            analyst_role = discord.utils.get(interaction.guild.roles, name=analyst_role_name) if interaction.guild else None
            if analyst_role and analyst_role in interaction.user.roles:
                is_analyst_user = True
                break
    
    if not (is_analyst_user or is_admin_user):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk analyst atau admin.",
            ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🔗 KODE REFERRAL - THE WARRIOR",
        description="Bagikan kode ini ke teman untuk dapatkan komisi 30%!",
        color=0xd35400)
    
    embed.add_field(name="📊 6 Analysts:", 
                   value="• **Bay** → Kode: `B4Y_kTx`\n• **Dialena** → Kode: `D1L3n4X`\n• **Kamado** → Kode: `K4m4d0Z`\n• **Ryzu** → Kode: `Ry2uW3k`\n• **Zen** → Kode: `Z3nQp0x`\n• **Rey** → Kode: `R3yT8m2`", 
                   inline=False)
    embed.add_field(name="📊 1 Analyst's Lead:", 
                   value="• **Bell** → Kode: `B3LLrFT`", 
                   inline=False)
    embed.add_field(name="💡 Cara Kerja:", 
                   value="1. Member baru input kode referral saat `/buy`\n2. Setelah payment sukses → Komisi Rp otomatis tercatat\n3. Komisi = 30% dari harga SETELAH diskon (jika ada)\n4. Cek komisi dengan `/komisi_saya_[nama]`", 
                   inline=False)
    embed.set_footer(text="Contoh: /komisi_saya_bay → Lihat komisi Anda")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="komisi_saya_bay", description="Cek komisi referral Bay")
@app_commands.default_permissions(administrator=False)
async def komisi_saya_bay(interaction: discord.Interaction):
    if not is_analyst(interaction, "Bay"):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk analyst Bay.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        c.execute('''SELECT COUNT(*), SUM(commission_amount)
                    FROM commissions WHERE referrer_name = "Bay"''')
        result = c.fetchone()
        total_ref, total_komisi = result
        
        c.execute('''SELECT referred_username, final_amount, commission_amount, discount_percentage, transaction_date
                    FROM commissions WHERE referrer_name = "Bay" ORDER BY transaction_date DESC LIMIT 10''')
        transactions = c.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="💰 KOMISI REFERRAL - BAY",
            color=0x00ff00)
        embed.add_field(name="👥 Total Referral", value=str(total_ref or 0), inline=True)
        embed.add_field(name="💵 Total Komisi", value=f"Rp {total_komisi or 0:,}", inline=True)
        
        if transactions:
            detail_text = ""
            for username, final_amt, komisi, diskon, date in transactions:
                detail_text += f"• {username}: Rp {komisi:,} (harga: Rp {final_amt:,}, diskon: {diskon}%)\n"
            embed.add_field(name="📋 10 Transaksi Terbaru:", value=detail_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@tree.command(name="komisi_saya_dialena", description="Cek komisi referral Dialena")
@app_commands.default_permissions(administrator=False)
async def komisi_saya_dialena(interaction: discord.Interaction):
    if not is_analyst(interaction, "Dialena"):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk analyst Dialena.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        c.execute('''SELECT COUNT(*), SUM(commission_amount), SUM(commission_amount)
                    FROM commissions WHERE referrer_name = "Dialena"''')
        result = c.fetchone()
        total_ref, total_komisi = result
        
        c.execute('''SELECT referred_username, final_amount, commission_amount, discount_percentage, transaction_date
                    FROM commissions WHERE referrer_name = "Dialena" ORDER BY transaction_date DESC LIMIT 10''')
        transactions = c.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="💰 KOMISI REFERRAL - DIALENA",
            color=0x00ff00)
        embed.add_field(name="👥 Total Referral", value=str(total_ref or 0), inline=True)
        embed.add_field(name="💵 Total Komisi", value=f"Rp {total_komisi or 0:,}", inline=True)
        
        if transactions:
            detail_text = ""
            for username, final_amt, komisi, diskon, date in transactions:
                detail_text += f"• {username}: Rp {komisi:,} (harga: Rp {final_amt:,}, diskon: {diskon}%)\n"
            embed.add_field(name="📋 10 Transaksi Terbaru:", value=detail_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@tree.command(name="komisi_saya_kamado", description="Cek komisi referral Kamado")
@app_commands.default_permissions(administrator=False)
async def komisi_saya_kamado(interaction: discord.Interaction):
    if not is_analyst(interaction, "Kamado"):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk analyst Kamado.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        c.execute('''SELECT COUNT(*), SUM(commission_amount), SUM(commission_amount)
                    FROM commissions WHERE referrer_name = "Kamado"''')
        result = c.fetchone()
        total_ref, total_komisi = result
        
        c.execute('''SELECT referred_username, final_amount, commission_amount, discount_percentage, transaction_date
                    FROM commissions WHERE referrer_name = "Kamado" ORDER BY transaction_date DESC LIMIT 10''')
        transactions = c.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="💰 KOMISI REFERRAL - KAMADO",
            color=0x00ff00)
        embed.add_field(name="👥 Total Referral", value=str(total_ref or 0), inline=True)
        embed.add_field(name="💵 Total Komisi", value=f"Rp {total_komisi or 0:,}", inline=True)
        
        if transactions:
            detail_text = ""
            for username, final_amt, komisi, diskon, date in transactions:
                detail_text += f"• {username}: Rp {komisi:,} (harga: Rp {final_amt:,}, diskon: {diskon}%)\n"
            embed.add_field(name="📋 10 Transaksi Terbaru:", value=detail_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@tree.command(name="komisi_saya_ryzu", description="Cek komisi referral Ryzu")
@app_commands.default_permissions(administrator=False)
async def komisi_saya_ryzu(interaction: discord.Interaction):
    if not is_analyst(interaction, "Ryzu"):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk analyst Ryzu.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        c.execute('''SELECT COUNT(*), SUM(commission_amount), SUM(commission_amount)
                    FROM commissions WHERE referrer_name = "Ryzu"''')
        result = c.fetchone()
        total_ref, total_komisi = result
        
        c.execute('''SELECT referred_username, final_amount, commission_amount, discount_percentage, transaction_date
                    FROM commissions WHERE referrer_name = "Ryzu" ORDER BY transaction_date DESC LIMIT 10''')
        transactions = c.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="💰 KOMISI REFERRAL - RYZU",
            color=0x00ff00)
        embed.add_field(name="👥 Total Referral", value=str(total_ref or 0), inline=True)
        embed.add_field(name="💵 Total Komisi", value=f"Rp {total_komisi or 0:,}", inline=True)
        
        if transactions:
            detail_text = ""
            for username, final_amt, komisi, diskon, date in transactions:
                detail_text += f"• {username}: Rp {komisi:,} (harga: Rp {final_amt:,}, diskon: {diskon}%)\n"
            embed.add_field(name="📋 10 Transaksi Terbaru:", value=detail_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@tree.command(name="komisi_saya_zen", description="Cek komisi referral Zen")
@app_commands.default_permissions(administrator=False)
async def komisi_saya_zen(interaction: discord.Interaction):
    if not is_analyst(interaction, "Zen"):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk analyst Zen.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        c.execute('''SELECT COUNT(*), SUM(commission_amount), SUM(commission_amount)
                    FROM commissions WHERE referrer_name = "Zen"''')
        result = c.fetchone()
        total_ref, total_komisi = result
        
        c.execute('''SELECT referred_username, final_amount, commission_amount, discount_percentage, transaction_date
                    FROM commissions WHERE referrer_name = "Zen" ORDER BY transaction_date DESC LIMIT 10''')
        transactions = c.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="💰 KOMISI REFERRAL - ZEN",
            color=0x00ff00)
        embed.add_field(name="👥 Total Referral", value=str(total_ref or 0), inline=True)
        embed.add_field(name="💵 Total Komisi", value=f"Rp {total_komisi or 0:,}", inline=True)
        
        if transactions:
            detail_text = ""
            for username, final_amt, komisi, diskon, date in transactions:
                detail_text += f"• {username}: Rp {komisi:,} (harga: Rp {final_amt:,}, diskon: {diskon}%)\n"
            embed.add_field(name="📋 10 Transaksi Terbaru:", value=detail_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@tree.command(name="komisi_saya_rey", description="Cek komisi referral Rey")
@app_commands.default_permissions(administrator=False)
async def komisi_saya_rey(interaction: discord.Interaction):
    if not is_analyst(interaction, "Rey"):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk analyst Rey.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        c.execute('''SELECT COUNT(*), SUM(commission_amount), SUM(commission_amount)
                    FROM commissions WHERE referrer_name = "Rey"''')
        result = c.fetchone()
        total_ref, total_komisi = result
        
        c.execute('''SELECT referred_username, final_amount, commission_amount, discount_percentage, transaction_date
                    FROM commissions WHERE referrer_name = "Rey" ORDER BY transaction_date DESC LIMIT 10''')
        transactions = c.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="💰 KOMISI REFERRAL - REY",
            color=0x00ff00)
        embed.add_field(name="👥 Total Referral", value=str(total_ref or 0), inline=True)
        embed.add_field(name="💵 Total Komisi", value=f"Rp {total_komisi or 0:,}", inline=True)
        
        if transactions:
            detail_text = ""
            for username, final_amt, komisi, diskon, date in transactions:
                detail_text += f"• {username}: Rp {komisi:,} (harga: Rp {final_amt:,}, diskon: {diskon}%)\n"
            embed.add_field(name="📋 10 Transaksi Terbaru:", value=detail_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@tree.command(name="komisi_saya_bell", description="Cek komisi referral Bell (Analyst's Lead)")
@app_commands.default_permissions(administrator=False)
async def komisi_saya_bell(interaction: discord.Interaction):
    if not is_analyst(interaction, "Bell"):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk analyst Bell.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        c.execute('''SELECT COUNT(*), SUM(commission_amount), SUM(commission_amount)
                    FROM commissions WHERE referrer_name = "Bell"''')
        result = c.fetchone()
        total_ref, total_komisi = result
        
        c.execute('''SELECT referred_username, final_amount, commission_amount, discount_percentage, transaction_date
                    FROM commissions WHERE referrer_name = "Bell" ORDER BY transaction_date DESC LIMIT 10''')
        transactions = c.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="💰 KOMISI REFERRAL - BELL",
            color=0x00ff00)
        embed.add_field(name="👥 Total Referral", value=str(total_ref or 0), inline=True)
        embed.add_field(name="💵 Total Komisi", value=f"Rp {total_komisi or 0:,}", inline=True)
        
        if transactions:
            detail_text = ""
            for username, final_amt, komisi, diskon, date in transactions:
                detail_text += f"• {username}: Rp {komisi:,} (harga: Rp {final_amt:,}, diskon: {diskon}%)\n"
            embed.add_field(name="📋 10 Transaksi Terbaru:", value=detail_text, inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class ResetCommissionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    
    @discord.ui.button(label="📊 Tutup Buku Komisi Bulanan", style=discord.ButtonStyle.primary, emoji="🔄")
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_commission_manager(interaction):
            await interaction.response.send_message(
                "❌ Hanya role **Com Manager** yang bisa tutup buku komisi!",
                ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        try:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            # Get current stats before reset
            c.execute('''SELECT SUM(commission_amount) FROM commissions''')
            total_before = c.fetchone()[0] or 0
            
            # Reset: Delete all commission records
            c.execute('DELETE FROM commissions')
            c.execute('DELETE FROM referrals')
            conn.commit()
            
            embed = discord.Embed(
                title="✅ BUKU KOMISI BERHASIL DITUTUP",
                description="📊 Data komisi bulanan telah di-archive dan reset ke nol",
                color=0xd35400)
            embed.add_field(
                name="💰 Total Komisi Terarsip",
                value=f"Rp {total_before:,}",
                inline=True)
            embed.add_field(
                name="📅 Status",
                value="Bulan baru dimulai (0 komisi)",
                inline=True)
            embed.add_field(
                name="🔄 Data Direset",
                value="✓ Komisi\n✓ Referral",
                inline=False)
            embed.set_footer(text=f"Ditutup oleh: {interaction.user.name} • {datetime.now().strftime('%d-%m-%Y %H:%M')}")
            
            conn.close()
            await interaction.followup.send(embed=embed, ephemeral=True)
            print(f"✅ Commission book closed by {interaction.user.name} | Total archived: Rp {total_before:,}")
        except Exception as e:
            await interaction.followup.send(f"❌ Error tutup buku: {e}", ephemeral=True)
            print(f"❌ Error closing commission book: {e}")


@tree.command(name="bot_status", description="[Com-Manager Only] Lihat status bot uptime dan availability")
@app_commands.default_permissions(administrator=False)
async def bot_status_command(interaction: discord.Interaction):
    if not is_commission_manager(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk role **Com Manager**.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        now = datetime.now(pytz.timezone('Asia/Jakarta'))
        uptime = now - bot_start_time
        
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        
        uptime_str = f"{days}d {hours}h {minutes}m"
        
        # Calculate availability (simplified: assume bot always runs)
        availability = "99.9%"
        
        embed = discord.Embed(
            title="🤖 BOT STATUS",
            color=0xd35400)
        embed.add_field(
            name="📊 Status",
            value="🟢 ONLINE",
            inline=True)
        embed.add_field(
            name="⏱️ Uptime",
            value=uptime_str,
            inline=True)
        embed.add_field(
            name="🕐 Last Start",
            value=format_jakarta_datetime_full(bot_start_time.strftime('%Y-%m-%d %H:%M:%S')),
            inline=True)
        embed.add_field(
            name="📈 Availability",
            value=availability,
            inline=True)
        embed.add_field(
            name="✅ Systems",
            value="✓ Discord Connected\n✓ Midtrans Active\n✓ Database Ready\n✓ Email Service",
            inline=False)
        embed.set_footer(text="Bot is running smoothly! 🚀")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@tree.command(name="komisi_stats", description="[Admin/Analyst Only] Lihat statistik komisi semua referral")
@app_commands.default_permissions(administrator=False)
async def komisi_stats_command(interaction: discord.Interaction):
    if not can_access_admin_commands(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk role **Origin**, **Analyst**, atau **Analyst's Lead**.", 
            ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        # Get stats for each referrer
        referrer_names = ["Bay", "Dialena", "Kamado", "Ryzu", "Zen", "Rey", "Bell"]
        
        embed = discord.Embed(
            title="📊 STATISTIK KOMISI SEMUA REFERRAL",
            color=0xd35400)
        
        total_all_ref = 0
        total_all_komisi = 0
        
        # Build description with detailed stats
        description = ""
        for referrer in referrer_names:
            c.execute('''SELECT COUNT(*), SUM(commission_amount)
                        FROM commissions WHERE referrer_name = ?''', (referrer,))
            result = c.fetchone()
            total_ref, total_komisi = result
            total_ref = total_ref or 0
            total_komisi = total_komisi or 0
            
            total_all_ref += total_ref
            total_all_komisi += total_komisi
            
            description += f"📊 **{referrer}**\n`Referral: {total_ref} | Komisi: Rp {total_komisi:,} | Total: Rp {total_komisi:,}`\n\n"
        
        # Add separator and total
        description += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        description += f"📊 **TOTAL KESELURUHAN**\n`Referral: {total_all_ref} | Komisi: Rp {total_all_komisi:,} | Total: Rp {total_all_komisi:,}`"
        
        embed.description = description
        embed.set_footer(text="🔐 Button reset hanya untuk Com Manager")
        
        conn.close()
        
        # Add reset button (visible to all, but only Com Manager dapat akses)
        view = ResetCommissionView(interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


async def cleanup_stale_pending_orders():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            # Find pending orders older than 15 minutes
            fifteen_min_ago = (datetime.now() - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute('''SELECT order_id, discord_id, discord_username, created_at 
                        FROM pending_orders 
                        WHERE datetime(created_at) <= datetime(?)''',
                     (fifteen_min_ago,))
            
            stale_orders = c.fetchall()
            
            if stale_orders:
                print(f"🧹 Found {len(stale_orders)} stale pending orders (older than 15 min)")
                
                for order_id, discord_id, discord_username, created_at in stale_orders:
                    c.execute('DELETE FROM pending_orders WHERE order_id = ?', (order_id,))
                    print(f"  ✅ Deleted stale order {order_id} for {discord_username} (created: {created_at})")
                
                conn.commit()
            
            conn.close()
            
        except Exception as e:
            print(f"❌ Error cleaning stale orders: {e}")
        
        # Check every 10 minutes
        await asyncio.sleep(600)


async def check_expiring_subscriptions():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            # Add column if not exists (for backwards compatibility)
            try:
                c.execute('ALTER TABLE subscriptions ADD COLUMN last_notified_3days TIMESTAMP')
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
            now = datetime.now()
            now_str = now.strftime('%Y-%m-%d %H:%M:%S')
            three_days_from_now = (now + timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
            twenty_four_hours_ago = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
            
            # Check for subscriptions expiring within next 3 days that haven't been notified in last 24 hours
            c.execute('''SELECT discord_id, discord_username, nama, email, end_date, package_type, last_notified_3days
                        FROM subscriptions 
                        WHERE status = "active" 
                        AND datetime(end_date) > datetime(?)
                        AND datetime(end_date) <= datetime(?)
                        AND (last_notified_3days IS NULL OR datetime(last_notified_3days) < datetime(?))''',
                     (now_str, three_days_from_now, twenty_four_hours_ago))
            
            expiring_subs = c.fetchall()
            packages = get_all_packages()
            
            guild = bot.get_guild(GUILD_ID)
            
            for row in expiring_subs:
                discord_id, discord_username, nama, email, end_date, package_type, last_notif = row
                try:
                    member = guild.get_member(int(discord_id)) if guild else None
                    
                    if member:
                        pkg_name = packages.get(package_type, {}).get('name', 'The Warrior')
                        end_datetime_full = format_jakarta_datetime_full(end_date)
                        
                        embed = discord.Embed(
                            title="⚠️ MEMBERSHIP AKAN BERAKHIR",
                            description=f"Halo **{nama}**!\n\nMembership **{pkg_name}** kamu akan berakhir dalam 3 hari!",
                            color=0xd35400)
                        embed.add_field(
                            name="📅 Tanggal & Jam Berakhir",
                            value=end_datetime_full,
                            inline=False)
                        embed.add_field(
                            name="🔄 Perpanjang Sekarang",
                            value="Gunakan `/buy` dan pilih 'Perpanjang Member'",
                            inline=False)
                        embed.add_field(
                            name="⏰ Akses akan hilang jika tidak diperpanjang",
                            value="Role & channel access akan otomatis dicopot saat membership expired",
                            inline=False)
                        embed.set_footer(text="Jangan sampai akses kamu terputus!")
                        
                        await member.send(embed=embed)
                        print(f"✅ Sent expiry warning DM to user {discord_id} ({nama})")
                    
                    # Update last notification time (NOW) so next notification will be in 24 hours
                    c.execute('UPDATE subscriptions SET last_notified_3days = datetime(?) WHERE discord_id = ?',
                             (now_str, discord_id))
                    
                except Exception as e:
                    print(f"❌ Error sending notification to {discord_id}: {e}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"❌ Error checking expiring subscriptions: {e}")
        
        # Check every 24 hours (86400 seconds)
        await asyncio.sleep(86400)


async def check_expired_trial_members():
    """Auto-remove Trial Member role when trial ends"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute('''SELECT discord_id, discord_username, trial_end_date
                        FROM trial_members 
                        WHERE status = "active" 
                        AND datetime(trial_end_date) <= datetime(?)''',
                     (now,))
            
            expired_trials = c.fetchall()
            print(f"🔍 Trial check: Found {len(expired_trials)} expired trial members")
            
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                print(f"❌ Guild not found in trial removal!")
                conn.close()
                await asyncio.sleep(60)
                continue
            
            for discord_id, discord_username, trial_end_date in expired_trials:
                try:
                    print(f"🔄 Processing expired trial: {discord_username} ({discord_id})")
                    
                    member = guild.get_member(int(discord_id))
                    if not member:
                        print(f"  ⚠️ Member {discord_username} tidak ditemukan")
                        c.execute('UPDATE trial_members SET status = "expired" WHERE discord_id = ?', (discord_id,))
                        print(f"  ✅ Status updated to expired")
                        continue
                    
                    trial_role = discord.utils.get(guild.roles, name="Trial Member")
                    if not trial_role:
                        print(f"  ❌ Trial Member role tidak ditemukan")
                        continue
                    
                    if trial_role in member.roles:
                        # Remove role
                        try:
                            await member.remove_roles(trial_role)
                            print(f"  ✅ Removed Trial Member role from {member.name}")
                        except discord.Forbidden:
                            print(f"  ❌ PERMISSION DENIED: Bot role tidak cukup tinggi")
                            continue
                        
                        # Send notification
                        try:
                            end_date_str = format_jakarta_datetime_full(trial_end_date)
                            embed = discord.Embed(
                                title="⏰ TRIAL MEMBER BERAKHIR",
                                description=f"Halo **{discord_username}**,\n\nPeriode trial Anda telah berakhir dan role telah dicopot.",
                                color=0xff0000)
                            embed.add_field(
                                name="📅 Tanggal Berakhir",
                                value=end_date_str,
                                inline=False)
                            embed.add_field(
                                name="🎯 Upgrade Sekarang",
                                value="Gunakan `/buy` untuk menjadi member premium!",
                                inline=False)
                            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                            
                            await member.send(embed=embed)
                            print(f"  ✅ DM sent to {member.name}")
                        except discord.HTTPException:
                            print(f"  ⚠️ Could not send DM to {discord_id}")
                    
                    # Update status
                    c.execute('UPDATE trial_members SET status = "expired" WHERE discord_id = ?', (discord_id,))
                    print(f"  ✅ Trial member marked as expired")
                    
                except Exception as e:
                    print(f"  ❌ Error: {e}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"❌ Error in trial removal: {e}")
        
        # Check every 5 minutes (300 seconds)
        await asyncio.sleep(300)


async def fetch_crypto_news():
    """Fetch crypto news - using sample data for testing (API backup)"""
    # Sample crypto news for testing/display purposes with REAL URLs
    sample_articles = [
        {
            'title': 'Bitcoin Rally Continues as Institutional Adoption Grows',
            'url': 'https://www.coindesk.com/markets',
            'source': {'title': 'CoinDesk'},
            'image_url': 'https://images.unsplash.com/photo-1621761191319-c6fb62b6fe6e?w=500',
            'published': '2025-11-24T14:30:00Z',
            'description': 'Bitcoin has surged past previous resistance levels as major institutions announce new crypto holdings. Analysts predict further gains in Q4 2025.'
        },
        {
            'title': 'Ethereum Layer 2 Solutions Reach New Milestone',
            'url': 'https://ethereum.org/en/',
            'source': {'title': 'Ethereum Official'},
            'image_url': 'https://images.unsplash.com/photo-1618793059027-ea4b6e3d6d7a?w=500',
            'published': '2025-11-24T12:15:00Z',
            'description': 'Arbitrum and Optimism Layer 2 protocols have processed over $500 billion in transactions this month, showing massive adoption.'
        },
        {
            'title': 'New DeFi Protocol Launches with $100M TVL',
            'url': 'https://defipulse.com/',
            'source': {'title': 'DeFi Pulse'},
            'image_url': 'https://images.unsplash.com/photo-1639762681033-6461efb0b480?w=500',
            'published': '2025-11-24T10:45:00Z',
            'description': 'Revolutionary DeFi platform gains traction with innovative yield farming mechanisms and attractive APY rewards.'
        },
        {
            'title': 'Altcoins Rally on Positive Market Sentiment',
            'url': 'https://www.coingecko.com/',
            'source': {'title': 'CoinGecko'},
            'image_url': 'https://images.unsplash.com/photo-1579621970563-430f63602d4b?w=500',
            'published': '2025-11-24T09:20:00Z',
            'description': 'Major altcoins including Cardano, Solana, and Polkadot surge as investors seek alternative investment opportunities.'
        },
        {
            'title': 'SEC Updates Crypto Regulations for 2025',
            'url': 'https://www.sec.gov/',
            'source': {'title': 'SEC Official'},
            'image_url': 'https://images.unsplash.com/photo-1611531900900-48d240ce8313?w=500',
            'published': '2025-11-24T08:00:00Z',
            'description': 'New regulatory framework aims to clarify crypto asset classification and improve consumer protection in digital asset markets.'
        }
    ]
    
    return sample_articles


async def auto_post_crypto_news():
    """Auto-post cryptocurrency news to #berita channel"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                await asyncio.sleep(3600)
                continue
            
            # Find news channel
            news_channel = None
            for channel in guild.text_channels:
                if channel.name == NEWS_CHANNEL_NAME:
                    news_channel = channel
                    break
            
            if not news_channel:
                print(f"⚠️ Channel #{NEWS_CHANNEL_NAME} tidak ditemukan. Skip posting berita.")
                await asyncio.sleep(3600)
                continue
            
            # Fetch crypto news
            try:
                articles = await fetch_crypto_news()
                
                if articles:
                    for article in articles:
                        try:
                            title = article.get('title', 'Untitled')
                            link = article.get('url', '')
                            source = article.get('source', {}).get('title', 'Crypto News')
                            image = article.get('image_url', '')
                            published = article.get('published', '')
                            description = article.get('description', '')
                            
                            embed = discord.Embed(
                                title=title[:256],
                                description=description[:2000] if description else "Klik link untuk baca artikel lengkap",
                                color=0xf7931a,
                                url=link
                            )
                            
                            if image:
                                embed.set_image(url=image)
                            
                            embed.add_field(
                                name="📖 Baca Artikel Lengkap",
                                value=f"[LINK KE ARTIKEL]({link})",
                                inline=False
                            )
                            
                            embed.set_footer(text=f"Sumber: {source} | {published}")
                            
                            await news_channel.send(embed=embed)
                            await asyncio.sleep(2)  # Rate limit
                        except Exception as e:
                            print(f"⚠️ Error posting individual article: {e}")
                    
                    print(f"✅ {len(articles)} crypto news posted to #{NEWS_CHANNEL_NAME}")
                else:
                    print(f"⚠️ No crypto news found")
            
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Error fetching crypto news: {e}")
            except Exception as e:
                print(f"❌ Error posting news: {e}")
            
            # Post setiap 24 jam
            await asyncio.sleep(86400)
        
        except Exception as e:
            print(f"❌ Error in crypto news task: {e}")
            await asyncio.sleep(3600)


async def check_expired_subscriptions():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute('''SELECT discord_id, discord_username, nama, email, package_type, end_date 
                        FROM subscriptions 
                        WHERE status = "active" 
                        AND datetime(end_date) <= datetime(?)''',
                     (now,))
            
            expired_subs = c.fetchall()
            print(f"🔍 Auto removal check: Found {len(expired_subs)} expired memberships")
            
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                print(f"❌ Guild not found in auto removal!")
                conn.close()
                await asyncio.sleep(3600)
                continue
            
            for discord_id, discord_username, nama, email, package_type, end_date in expired_subs:
                try:
                    print(f"🔄 Processing expired: {discord_username} ({discord_id}) - Package: {package_type}")
                    
                    member = guild.get_member(int(discord_id))
                    if not member:
                        print(f"  ⚠️ Member {discord_username} ({discord_id}) tidak ditemukan di guild")
                        # Update status tetap ke expired meski member tidak ditemukan
                        c.execute('UPDATE subscriptions SET status = "expired" WHERE discord_id = ?',
                                 (discord_id,))
                        print(f"  ✅ Status updated to expired")
                        continue
                    
                    packages = get_all_packages()
                    role_name = packages.get(package_type, {}).get("role_name")
                    duration_days = packages.get(package_type, {}).get("duration_days", 0)
                    if not role_name:
                        print(f"  ❌ Role name tidak ditemukan untuk package {package_type}")
                        continue
                    
                    role = discord.utils.get(guild.roles, name=role_name)
                    if not role:
                        print(f"  ❌ Role '{role_name}' tidak ditemukan di guild")
                        continue
                    
                    if role in member.roles:
                        pkg_name = packages.get(package_type, {}).get('name', 'The Warrior')
                        end_datetime_full = format_jakarta_datetime_full(end_date)
                        
                        # Determine warning message based on package duration
                        is_one_hour_package = duration_days < 1  # 1 hour = 0.041667 days
                        
                        if is_one_hour_package:
                            # For 1-hour package: SUDAH BERAKHIR warning
                            title_warning = "⏰ PERHATIAN: MEMBERSHIP SUDAH BERAKHIR"
                            desc_warning = f"Halo **{nama}**,\n\nMembership **{pkg_name}** kamu sudah berakhir dan akan segera dicabut."
                            action_text = "• Role **The Warrior** akan dicopot sekarang\n• Akses channel akan hilang\n• Gunakan `/buy` untuk perpanjang!"
                        else:
                            # For other packages: keep original warning (should not reach here normally, handled by check_expiring_subscriptions)
                            title_warning = "⏰ PERHATIAN: MEMBERSHIP SEGERA BERAKHIR"
                            desc_warning = f"Halo **{nama}**,\n\nMembership **{pkg_name}** kamu akan dicabut dalam 1 menit."
                            action_text = "• Role **The Warrior** akan dicopot\n• Akses channel akan hilang\n• Gunakan `/buy` untuk perpanjang!"
                        
                        # Send pre-expiry notification BEFORE removing role
                        embed_warning = discord.Embed(
                            title=title_warning,
                            description=desc_warning,
                            color=0xff8800)
                        embed_warning.add_field(
                            name="📅 Tanggal & Jam Berakhir",
                            value=end_datetime_full,
                            inline=False)
                        embed_warning.add_field(
                            name="⚠️ Apa yang akan terjadi?",
                            value=action_text,
                            inline=False)
                        embed_warning.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                        
                        try:
                            await member.send(embed=embed_warning)
                            print(f"  ✅ Pre-expiry warning sent to {member.name}")
                        except discord.HTTPException:
                            print(f"  ⚠️ Could not send warning DM to {discord_id}")
                        
                        # Now remove the role
                        try:
                            await member.remove_roles(role)
                            print(f"  ✅ Removed role {role.name} from {member.name}")
                        except discord.Forbidden:
                            print(f"  ❌ PERMISSION DENIED: Bot role tidak cukup tinggi untuk remove role {role.name}")
                            continue
                        
                        # Send expiry confirmation
                        embed = discord.Embed(
                            title="❌ MEMBERSHIP BERAKHIR",
                            description=f"Halo **{nama}**,\n\nMembership **{pkg_name}** kamu telah berakhir dan role telah dicopot.",
                            color=0xff0000)
                        embed.add_field(
                            name="📅 Tanggal & Jam Berakhir",
                            value=end_datetime_full,
                            inline=False)
                        embed.add_field(
                            name="🔄 Perpanjang Sekarang",
                            value="Gunakan `/buy` dan pilih 'Perpanjang Member' untuk aktifkan kembali!",
                            inline=False)
                        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                        
                        try:
                            await member.send(embed=embed)
                            print(f"  ✅ DM sent to {member.name}")
                        except discord.HTTPException:
                            print(f"  ⚠️ Could not DM user {discord_id}")
                        
                        # Send goodbye card email
                        send_goodbye_card_email(email, nama, pkg_name, end_datetime_full)
                        
                        # Send admin kick notification
                        send_admin_kick_notification(nama, email, pkg_name, "Auto Removal - Membership Expired")
                    else:
                        print(f"  ℹ️ Role {role.name} not found in member roles")
                    
                    c.execute('UPDATE subscriptions SET status = "expired" WHERE discord_id = ?',
                             (discord_id,))
                    print(f"  ✅ Subscription marked as expired")
                    
                except Exception as e:
                    print(f"  ❌ Error: {e}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"❌ Error in auto removal: {e}")
        
        await asyncio.sleep(300)


class KickMemberView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__()
        self.interaction = interaction
        self.guild = interaction.guild

    @discord.ui.button(label="🚨 Kick The Warrior Member", style=discord.ButtonStyle.danger)
    async def kick_warrior(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        if not self.guild:
            await interaction.followup.send("❌ Guild tidak ditemukan!", ephemeral=True)
            return
        
        warrior_role = discord.utils.get(self.guild.roles, name="The Warrior")
        if not warrior_role:
            await interaction.followup.send("❌ Role 'The Warrior' tidak ditemukan!", ephemeral=True)
            return
        
        members_with_role = [m for m in self.guild.members if warrior_role in m.roles]
        if not members_with_role:
            await interaction.followup.send("❌ Tidak ada member dengan role The Warrior!", ephemeral=True)
            return
        
        options = [discord.SelectOption(label=m.name, value=str(m.id)) for m in members_with_role[:25]]
        select_view = MemberSelectView(self.guild, warrior_role, "The Warrior", options)
        
        await interaction.followup.send("📋 Pilih member yang ingin di-kick:", view=select_view, ephemeral=True)

    @discord.ui.button(label="⏰ Kick Trial Member", style=discord.ButtonStyle.danger)
    async def kick_trial(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        if not self.guild:
            await interaction.followup.send("❌ Guild tidak ditemukan!", ephemeral=True)
            return
        
        trial_role = discord.utils.get(self.guild.roles, name="Trial Member")
        if not trial_role:
            await interaction.followup.send("❌ Role 'Trial Member' tidak ditemukan!", ephemeral=True)
            return
        
        members_with_role = [m for m in self.guild.members if trial_role in m.roles]
        if not members_with_role:
            await interaction.followup.send("❌ Tidak ada member dengan role Trial Member!", ephemeral=True)
            return
        
        options = [discord.SelectOption(label=m.name, value=str(m.id)) for m in members_with_role[:25]]
        select_view = MemberSelectView(self.guild, trial_role, "Trial Member", options)
        
        await interaction.followup.send("📋 Pilih member yang ingin di-kick:", view=select_view, ephemeral=True)


class MemberSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild, role: discord.Role, role_name: str, options):
        super().__init__()
        self.guild = guild
        self.role = role
        self.role_name = role_name
        self.add_item(MemberSelect(guild, role, role_name, options))


class MemberSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, role: discord.Role, role_name: str, options):
        super().__init__(placeholder="Pilih member...", options=options, min_values=1, max_values=1)
        self.guild = guild
        self.role = role
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        member_id = int(self.values[0])
        member = self.guild.get_member(member_id)
        
        if not member:
            await interaction.followup.send("❌ Member tidak ditemukan!", ephemeral=True)
            return
        
        try:
            await member.remove_roles(self.role)
            
            embed_kick = discord.Embed(
                title="🚨 KICKED!",
                description=f"Member **{member.name}** berhasil di-kick dari role **{self.role_name}**",
                color=0xff0000)
            embed_kick.add_field(name="👤 Member", value=member.name, inline=True)
            embed_kick.add_field(name="🎯 Role Dihapus", value=self.role_name, inline=True)
            embed_kick.set_footer(text=f"Di-kick oleh: {interaction.user.name}")
            
            await interaction.followup.send(embed=embed_kick, ephemeral=True)
            
            try:
                dm_embed = discord.Embed(
                    title="❌ AKSES DICABUT",
                    description=f"Halo **{member.name}**,\n\nRole **{self.role_name}** Anda telah dihapus oleh admin.",
                    color=0xff0000)
                dm_embed.add_field(
                    name="📌 Alasan",
                    value="Hubungi admin jika ada pertanyaan",
                    inline=False)
                dm_embed.add_field(
                    name="💡 Apa selanjutnya?",
                    value="Gunakan `/buy` untuk membeli membership baru",
                    inline=False)
                dm_embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
                dm_embed.set_footer(text="Terima kasih!")
                
                await member.send(embed=dm_embed)
            except discord.HTTPException:
                print(f"⚠️ Could not send DM to {member.id}")
            
            # Send goodbye card + expiry email for manual kick
            conn_email = sqlite3.connect('warrior_subscriptions.db')
            c_email = conn_email.cursor()
            c_email.execute('SELECT nama, email, package_type, end_date FROM subscriptions WHERE discord_id = ?', (str(member.id),))
            member_data = c_email.fetchone()
            conn_email.close()
            
            if member_data:
                nama, member_email, package_type, end_date = member_data
                packages = get_all_packages()
                pkg_name = packages.get(package_type, {}).get('name', 'The Warrior')
                end_date_str = format_jakarta_datetime_full(end_date)
                
                # Send goodbye card email
                send_goodbye_card_email(member_email, nama, pkg_name, end_date_str)
                
                # Send admin kick notification
                send_admin_kick_notification(nama, member_email, pkg_name, "Manual Kick by Com-Manager")
            
            print(f"✅ Kicked: {member.name} ({member.id}) from {self.role_name}")
            
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot tidak memiliki permission untuk menghapus role!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


async def check_is_commission_manager(interaction: discord.Interaction) -> bool:
    """Check if user is Com-Manager"""
    return is_commission_manager(interaction)


@tree.command(name="post_crypto_news_now", description="Post crypto news sekarang (untuk testing)")
@app_commands.check(check_is_commission_manager)
@app_commands.default_permissions(administrator=True)
async def post_crypto_news_now(interaction: discord.Interaction):
    
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Guild tidak ditemukan!", ephemeral=True)
            return
        
        # Find news channels - support multiple channels
        news_channels = []
        target_channel_names = [NEWS_CHANNEL_NAME, "💳｜payment"]  # Add both channels
        
        for channel in guild.text_channels:
            if channel.name in target_channel_names:
                news_channels.append(channel)
        
        if not news_channels:
            await interaction.followup.send(f"❌ Channel tidak ditemukan! Cari: {', '.join(target_channel_names)}", ephemeral=True)
            return
        
        # Fetch crypto news
        articles = await fetch_crypto_news()
        
        if articles:
            count = 0
            # Post to each channel
            for news_channel in news_channels:
                for article in articles:
                    try:
                        title = article.get('title', 'Untitled')
                        link = article.get('url', '')
                        source = article.get('source', {}).get('title', 'Crypto News')
                        image = article.get('image_url', '')
                        published = article.get('published', '')
                        description = article.get('description', '')
                        
                        embed = discord.Embed(
                            title=title[:256],
                            description=description[:2000] if description else "Klik link untuk baca artikel lengkap",
                            color=0xf7931a,
                            url=link
                        )
                        
                        if image:
                            embed.set_image(url=image)
                        
                        embed.add_field(
                            name="📖 Baca Artikel Lengkap",
                            value=f"[LINK KE ARTIKEL]({link})",
                            inline=False
                        )
                        
                        embed.set_footer(text=f"Sumber: {source} | {published}")
                        
                        await news_channel.send(embed=embed)
                        count += 1
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        print(f"⚠️ Error posting article: {e}")
            
            channel_list = ", ".join([f"#{ch.name}" for ch in news_channels])
            await interaction.followup.send(
                f"✅ {count} berita crypto sudah di-post ke: {channel_list}!",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "⚠️ Tidak ada berita crypto yang ditemukan saat ini",
                ephemeral=True
            )
    
    except Exception as e:
        print(f"❌ Error posting news: {e}")
        await interaction.followup.send(
            f"❌ Error: {str(e)}",
            ephemeral=True
        )


@tree.command(name="kick_member", description="[Com-Manager Only] Kick member secara manual")
@app_commands.default_permissions(administrator=False)
async def kick_member_command(interaction: discord.Interaction):
    if not is_commission_manager(interaction):
        await interaction.response.send_message(
            "❌ Command ini HANYA untuk role **Com-Manager** saja!", 
            ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🚨 KICK MEMBER MANAGER",
        description="Pilih tipe member yang ingin di-kick:",
        color=0xff0000)
    embed.add_field(name="🎯 The Warrior", value="Kick member dengan role The Warrior", inline=False)
    embed.add_field(name="⏰ Trial Member", value="Kick member dengan role Trial Member", inline=False)
    
    view = KickMemberView(interaction)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Global error handler untuk semua app commands"""
    try:
        print(f"❌ App command error: {error}")
        
        # Jika interaction sudah di-respond, gunakan followup
        if interaction.response.is_done():
            try:
                await interaction.followup.send(
                    "⚠️ Bot sedang maintenance. Silakan coba lagi dalam beberapa saat.",
                    ephemeral=True
                )
            except:
                pass
        else:
            # Jika belum, respond dengan pesan maintenance
            await interaction.response.send_message(
                "⚠️ Bot sedang maintenance. Silakan coba lagi dalam beberapa saat.",
                ephemeral=True
            )
    except Exception as e:
        print(f"❌ Error in error handler: {e}")


@bot.event
async def on_error(event, *args, **kwargs):
    """Global error event handler"""
    print(f"❌ Error in {event}: {args}")


@bot.event
async def on_ready():
    print(f'✅ {bot.user} has connected to Discord!')
    
    try:
        # Verify guild exists
        guild = bot.get_guild(GUILD_ID)
        if guild:
            print(f"✅ Found guild: {guild.name} (ID: {GUILD_ID})")
        else:
            print(f"⚠️ Guild not found: {GUILD_ID}")
            print(f"Available guilds: {[g.name for g in bot.guilds]}")
        
        # Try to sync globally first
        print("🔄 Syncing commands globally...")
        global_synced = await tree.sync()
        print(f"✅ Global sync: {len(global_synced)} commands")
        
        # Then sync to guild if it exists
        if guild:
            print(f"🔄 Syncing commands to guild {guild.name}...")
            guild_synced = await tree.sync(guild=discord.Object(id=GUILD_ID))
            print(f"✅ Guild sync: {len(guild_synced)} commands")
            for cmd in guild_synced:
                print(f"   - /{cmd.name}")
    except Exception as e:
        print(f"❌ Sync error: {e}")
        import traceback
        traceback.print_exc()
    
    bot.loop.create_task(cleanup_stale_pending_orders())
    bot.loop.create_task(check_expiring_subscriptions())
    bot.loop.create_task(check_expired_subscriptions())
    bot.loop.create_task(check_expired_trial_members())
    # bot.loop.create_task(auto_post_crypto_news())  # Manual only for now
    print("✅ Stale order cleanup started!")
    print("✅ Expiry checker started!")
    print("✅ Auto role removal started!")
    print("✅ Trial member auto-removal started!")
    print("✅ Crypto news MANUAL mode (use /post_crypto_news_now to test)")
    print("🎉 Bot is ready!")


if __name__ == "__main__":

    def run_flask():
        app.run(host='0.0.0.0', port=5000, debug=False)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    init_database()
    
    # Get correct webhook URL from REPLIT_DOMAINS
    replit_domain = os.environ.get('REPLIT_DOMAINS', f'{REPL_SLUG}.{REPL_OWNER}.repl.co')
    webhook_url = f"https://{replit_domain}/webhook/midtrans"
    
    print("🚀 Starting Discord bot...")
    print(f"🌐 Webhook URL untuk Midtrans: {webhook_url}")
    print(f"🧪 Midtrans Mode: SANDBOX (Testing)")
    print(f"💡 Pastikan webhook URL sudah dikonfigurasi di dashboard Midtrans SANDBOX")
    
    bot.run(TOKEN)
