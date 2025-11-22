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

TOKEN = os.environ.get('DISCORD_TOKEN', '')
GUILD_ID = 1370638839407972423
ORIGIN_ROLE_NAME = "Origin"

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

print(f"🔑 Midtrans Server Key: {'✅ SET' if MIDTRANS_SERVER_KEY else '❌ NOT SET'}")
print(f"🔑 Midtrans Client Key: {'✅ SET' if MIDTRANS_CLIENT_KEY else '❌ NOT SET'}")

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
    
    c.execute('''SELECT discord_id, order_id, package_type, amount, status, transaction_date 
                 FROM transactions 
                 WHERE strftime('%Y', transaction_date) = ? AND strftime('%m', transaction_date) = ?''',
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
        
        start_time = format_jakarta_datetime(sub_data[0]) if sub_data else format_jakarta_datetime(datetime.now())
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
        embed.set_footer(text="Terima kasih telah berlangganan!")
        
        view = ContactComManagerView(discord_id, nama, email)

        try:
            await member.send(embed=embed, view=view)
        except:
            print(f"⚠️ Could not DM user {discord_id}")

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


class ContactComManagerView(discord.ui.View):
    def __init__(self, member_id, member_name, member_email):
        super().__init__()
        self.member_id = member_id
        self.member_name = member_name
        self.member_email = member_email
    
    @discord.ui.button(label="📞 Chat dengan Com Manager", style=discord.ButtonStyle.primary, emoji="💬")
    async def contact_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            await interaction.response.send_message("❌ Guild tidak ditemukan!", ephemeral=True)
            return
        
        # Try to find Com Manager by username (case-insensitive)
        com_manager = None
        
        # First try: exact match "diarycryptoid"
        com_manager = discord.utils.get(guild.members, name="diarycryptoid")
        
        # Second try: case-insensitive search
        if not com_manager:
            for member in guild.members:
                if member.name and member.name.lower() == "diarycryptoid":
                    com_manager = member
                    break
        
        # Third try: search by display_name
        if not com_manager:
            for member in guild.members:
                if member.display_name and member.display_name.lower() == "diarycryptoid":
                    com_manager = member
                    break
        
        # Last resort: Find anyone with "Com Manager" or "Com-Manager" role
        if not com_manager:
            com_manager_role = discord.utils.get(guild.roles, name="Com-Manager")
            if not com_manager_role:
                com_manager_role = discord.utils.get(guild.roles, name="Com Manager")
            if com_manager_role:
                for member in guild.members:
                    if com_manager_role in member.roles:
                        com_manager = member
                        break
        
        if not com_manager:
            await interaction.response.send_message(
                "❌ Com Manager tidak ditemukan! Silakan hubungi admin secara langsung.",
                ephemeral=True)
            print(f"❌ Com Manager 'diarycryptoid' tidak ditemukan di guild")
            return
        
        # Send notification to Com Manager
        embed_to_cm = discord.Embed(
            title="📞 MEMBER BUTUH BANTUAN",
            description=f"Member **{self.member_name}** ingin berbicara denganmu!",
            color=0x0099ff)
        embed_to_cm.add_field(name="👤 Member", value=f"<@{self.member_id}>", inline=False)
        embed_to_cm.add_field(name="📧 Email", value=self.member_email, inline=False)
        embed_to_cm.add_field(name="💬 Action", value="Hubungi member melalui DM untuk membantu!", inline=False)
        
        try:
            await com_manager.send(embed=embed_to_cm)
            await interaction.response.send_message(
                f"✅ **Com Manager ({com_manager.name})** telah diberitahu! Mereka akan segera menghubungimu di DM.",
                ephemeral=True)
            print(f"✅ Notified Com Manager {com_manager.name} about member {self.member_name}")
        except discord.HTTPException as e:
            await interaction.response.send_message(
                "❌ Gagal menghubungi Com Manager. Coba lagi nanti!",
                ephemeral=True)
            print(f"❌ Error sending DM to Com Manager: {e}")


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
@app_commands.describe(
    package="Pilih paket langganan",
    action="Pilih: Beli Baru atau Perpanjang Member")
@app_commands.choices(action=[
    app_commands.Choice(name="🆕 Beli Baru", value="beli"),
    app_commands.Choice(name="🔄 Perpanjang Member", value="renewal")
])
async def buy_command(interaction: discord.Interaction,
                      package: Optional[str] = None,
                      action: Optional[str] = None):
    try:
        packages = get_all_packages()
        
        if not packages:
            await interaction.response.send_message(
                "❌ Tidak ada paket tersedia. Admin harus membuat paket terlebih dahulu.",
                ephemeral=True)
            return
        
        # Build package choices dynamically
        if package is None:
            package_choices = []
            for pkg_id, pkg_data in packages.items():
                choice_name = f"{pkg_data['name']} - Rp {pkg_data['price']:,}"
                package_choices.append(app_commands.Choice(name=choice_name, value=pkg_id))
            
            # Send interactive select
            from discord.ui import Select, View
            
            class PackageSelect(Select):
                def __init__(self, packages):
                    self.packages = packages
                    options = []
                    for pkg_id, pkg_data in packages.items():
                        option_label = f"{pkg_data['name']} - Rp {pkg_data['price']:,}"
                        options.append(discord.SelectOption(label=option_label, value=pkg_id))
                    super().__init__(placeholder="Pilih paket...", options=options)
                
                async def callback(self, interaction: discord.Interaction):
                    package_value = self.values[0]
                    await handle_buy(interaction, package_value, action, self.packages)
            
            class PackageView(View):
                def __init__(self, packages):
                    super().__init__()
                    self.add_item(PackageSelect(packages))
            
            view = PackageView(packages)
            await interaction.response.send_message("Pilih paket yang ingin dibeli:", view=view, ephemeral=True)
            return
        
        await handle_buy(interaction, package, action, packages)
        
    except Exception as e:
        print(f"Buy command error: {e}")
        await interaction.response.send_message(
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


@tree.command(name="statistik", description="[Admin Only] Lihat statistik langganan")
async def statistik_command(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk admin (role Origin).", 
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


@tree.command(name="export_monthly", description="[Admin Only] Export data transaksi bulanan")
@app_commands.describe(year="Tahun (misal: 2024)", month="Bulan (1-12)")
async def export_monthly_command(interaction: discord.Interaction, year: int, month: int):
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk admin (role Origin).", 
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
        
        csv_output = StringIO()
        csv_writer = csv.writer(csv_output)
        csv_writer.writerow(['Discord ID', 'Order ID', 'Package', 'Amount', 'Status', 'Date'])
        
        for trans in transactions:
            csv_writer.writerow(trans)
        
        csv_content = csv_output.getvalue()
        csv_output.close()
        
        filename = f"transactions_{year}_{month:02d}.csv"
        file = discord.File(
            fp=BytesIO(csv_content.encode('utf-8')),
            filename=filename)
        
        embed = discord.Embed(
            title=f"📊 Export Data Bulan {month}/{year}",
            description=f"Total transaksi: {len(transactions)}",
            color=0xd35400)
        
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        
    except Exception as e:
        print(f"Export error: {e}")
        await interaction.followup.send(
            "❌ Gagal export data.",
            ephemeral=True)


@tree.command(name="creat_discount", description="[Admin Only] Buat kode diskon baru")
@app_commands.describe(
    code="Kode diskon (contoh: PROMO50)",
    discount="Persentase diskon (1-100)",
    valid_days="Berlaku berapa hari",
    usage_limit="Maksimal penggunaan"
)
async def creat_discount_command(interaction: discord.Interaction, 
                                 code: str, 
                                 discount: int, 
                                 valid_days: int, 
                                 usage_limit: int):
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk admin (role Origin).", 
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


@tree.command(name="manage_package", description="[Admin Only] Kelola paket membership")
@app_commands.describe(
    action="Aksi: create/delete/list",
    package_id="ID paket (contoh: warrior_1year)",
    name="Nama paket (contoh: 1 Tahun - Rp 2.000.000)",
    price="Harga dalam Rupiah",
    duration_days="Durasi dalam hari",
    role_name="Nama role Discord (contoh: The Warrior)"
)
async def manage_package_command(interaction: discord.Interaction,
                                 action: str,
                                 package_id: Optional[str] = None,
                                 name: Optional[str] = None,
                                 price: Optional[int] = None,
                                 duration_days: Optional[float] = None,
                                 role_name: Optional[str] = None):
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk admin (role Origin).", 
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


@tree.command(name="refer_link", description="Tampilkan kode referral Anda")
async def refer_link_command(interaction: discord.Interaction):
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


@tree.command(name="komisi_stats", description="[Admin Only] Lihat statistik komisi semua referral")
async def komisi_stats_command(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk admin (role Origin).", 
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
                        
                        view = ContactComManagerView(discord_id, nama, email)
                        await member.send(embed=embed, view=view)
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
                        
                        # Send pre-expiry notification BEFORE removing role
                        embed_warning = discord.Embed(
                            title="⏰ PERHATIAN: MEMBERSHIP SEGERA BERAKHIR",
                            description=f"Halo **{nama}**,\n\nMembership **{pkg_name}** kamu akan dicabut dalam 1 menit.",
                            color=0xff8800)
                        embed_warning.add_field(
                            name="📅 Tanggal & Jam Berakhir",
                            value=end_datetime_full,
                            inline=False)
                        embed_warning.add_field(
                            name="⚠️ Apa yang akan terjadi?",
                            value="• Role **The Warrior** akan dicopot\n• Akses channel akan hilang\n• Gunakan `/buy` untuk perpanjang!",
                            inline=False)
                        
                        view_warning = ContactComManagerView(discord_id, nama, email)
                        try:
                            await member.send(embed=embed_warning, view=view_warning)
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
                        
                        view_expired = ContactComManagerView(discord_id, nama, email)
                        try:
                            await member.send(embed=embed, view=view_expired)
                            print(f"  ✅ DM sent to {member.name}")
                        except discord.HTTPException:
                            print(f"  ⚠️ Could not DM user {discord_id}")
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
    print("✅ Stale order cleanup started!")
    print("✅ Expiry checker started!")
    print("✅ Auto role removal started!")
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
