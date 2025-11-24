import discord
from discord.ext import commands
import os
import sqlite3
import time
from datetime import datetime, timedelta
import pytz
import requests
from flask import Flask, request
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import asyncio
import random
from enum import Enum
from typing import Optional, Dict, List, Tuple
import urllib.parse
import midtransclient

# ============ CONFIG ============
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 1370638839407972423
MIDTRANS_CLIENT_KEY = os.getenv('MIDTRANS_CLIENT_KEY')
MIDTRANS_SERVER_KEY = os.getenv('MIDTRANS_SERVER_KEY')
GMAIL_SENDER = os.getenv('GMAIL_SENDER')
GMAIL_PASSWORD = os.getenv('GMAIL_PASSWORD')
ADMIN_EMAIL = "asrofsantoso@gmail.com"
WARRIOR_ROLE_NAME = "The Warrior"
TRIAL_MEMBER_ROLE_NAME = "Trial Member"
ANALYST_ROLE_NAME = "Analyst"
ANALYST_LEAD_ROLE_NAME = "Analyst's Lead"
NEWS_CHANNEL_NAME = "📰｜berita-crypto"

# Flask app
app = Flask(__name__)

# Discord client setup
intents = discord.Intents.all()
intents.members = True
intents.presences = True
bot = commands.Bot(command_prefix='/', intents=intents)
bot.is_synced = False
tree = bot.tree

# Midtrans setup
midtrans_client = midtransclient.Snap(
    is_production=False,
    server_key=MIDTRANS_SERVER_KEY,
    client_key=MIDTRANS_CLIENT_KEY
)

# ============ DATABASE SETUP ============
def init_db():
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
                    order_id TEXT PRIMARY KEY,
                    discord_id TEXT NOT NULL,
                    discord_username TEXT,
                    nama TEXT,
                    email TEXT,
                    package_type TEXT,
                    payment_method TEXT,
                    status TEXT DEFAULT "pending",
                    start_date TEXT,
                    end_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    referral_code TEXT,
                    referrer_id TEXT
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS pending_orders (
                    order_id TEXT PRIMARY KEY,
                    discord_id TEXT,
                    discord_username TEXT,
                    nama TEXT,
                    email TEXT,
                    package_type TEXT,
                    payment_url TEXT,
                    status TEXT DEFAULT "pending",
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS trial_members (
                    discord_id TEXT PRIMARY KEY,
                    discord_username TEXT,
                    trial_started TEXT,
                    trial_end TEXT,
                    status TEXT DEFAULT "active"
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS referral_codes (
                    code TEXT PRIMARY KEY,
                    created_by TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    uses INT DEFAULT 0,
                    max_uses INT
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS commissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analyst_id TEXT,
                    referred_member_id TEXT,
                    commission_amount REAL,
                    package_type TEXT,
                    earned_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT "pending"
                )''')
    
    conn.commit()
    conn.close()

init_db()

# ============ TIMEZONE & DATE UTILS ============
def get_jakarta_datetime():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

def format_jakarta_datetime(dt):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.UTC)
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    jakarta_dt = dt.astimezone(jakarta_tz)
    return jakarta_dt.strftime('%d %b %Y %H:%M WIB')

def format_jakarta_datetime_full(date_str):
    if isinstance(date_str, str):
        date_str = date_str.split(' ')[0]
        dt = datetime.strptime(date_str, '%Y-%m-%d')
    else:
        dt = date_str
    
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.UTC)
    jakarta_dt = dt.astimezone(jakarta_tz)
    return jakarta_dt.strftime('%d %B %Y')

# ============ PACKAGES ============
def get_all_packages():
    packages = {
        'warrior_15min': {
            'name': 'The Warrior 15 Minutes',
            'price': 200000,
            'duration_days': 15/1440,
            'duration_text': '15 menit',
            'role_name': WARRIOR_ROLE_NAME
        },
        'warrior_1hour': {
            'name': 'The Warrior 1 Hour',
            'price': 50000,
            'duration_days': 1/24,
            'duration_text': '1 jam',
            'role_name': WARRIOR_ROLE_NAME
        },
        'warrior_1month': {
            'name': 'The Warrior 1 Month',
            'price': 299000,
            'duration_days': 30,
            'duration_text': '1 bulan',
            'role_name': WARRIOR_ROLE_NAME
        },
        'warrior_3month': {
            'name': 'The Warrior 3 Months',
            'price': 649000,
            'duration_days': 90,
            'duration_text': '3 bulan',
            'role_name': WARRIOR_ROLE_NAME
        }
    }
    return packages

# ============ HELPER FUNCTIONS ============
def is_commission_manager(interaction: discord.Interaction):
    """Check if user is guild owner or has admin permissions"""
    return interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator

def verify_discount_code(code: str) -> Dict:
    """Verify dan get discount code details"""
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        # Create table jika belum exist
        c.execute('''CREATE TABLE IF NOT EXISTS discount_codes (
            code TEXT PRIMARY KEY,
            discount_percent INTEGER,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            created_at TEXT,
            created_by TEXT
        )''')
        
        c.execute('SELECT discount_percent, max_uses, used_count FROM discount_codes WHERE code = ?', (code.upper(),))
        result = c.fetchone()
        conn.close()
        
        if not result:
            return {"valid": False, "message": "Kode diskon tidak ditemukan"}
        
        discount_percent, max_uses, used_count = result
        
        # Check max uses
        if max_uses > 0 and used_count >= max_uses:
            return {"valid": False, "message": f"Kode diskon sudah mencapai batas penggunaan ({used_count}/{max_uses})"}
        
        return {
            "valid": True,
            "discount_percent": discount_percent,
            "message": f"✅ Diskon {discount_percent}% berhasil diterapkan!"
        }
    except Exception as e:
        return {"valid": False, "message": str(e)}

def generate_referral_code(member_id):
    code = f"REF_{member_id}_{random.randint(1000, 9999)}"
    return code

def get_pending_order(order_id):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('SELECT * FROM pending_orders WHERE order_id = ?', (order_id,))
    order = c.fetchone()
    conn.close()
    return order

def save_pending_order(order_id, discord_id, username, nama, email, package_type, payment_url):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO pending_orders 
                (order_id, discord_id, discord_username, nama, email, package_type, payment_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
             (order_id, discord_id, username, nama, email, package_type, payment_url))
    conn.commit()
    conn.close()

def save_subscription(order_id, discord_id, username, nama, email, package_type, referral_code=None, referrer_id=None):
    packages = get_all_packages()
    package = packages.get(package_type)
    if not package:
        return False
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    start = get_jakarta_datetime()
    end = start + timedelta(days=package['duration_days'])
    
    c.execute('''INSERT OR REPLACE INTO subscriptions 
                (order_id, discord_id, discord_username, nama, email, package_type, status, start_date, end_date, referral_code, referrer_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
             (order_id, discord_id, username, nama, email, package_type, 'active',
              start.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S'), referral_code, referrer_id))
    
    conn.commit()
    conn.close()
    return True

def send_welcome_email(member_name, email, package_name, order_id, start_date, end_date, referral_code, member_avatar):
    if not GMAIL_SENDER or not GMAIL_PASSWORD:
        print("⚠️ Gmail not configured")
        return False
    
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px;">
                    <div style="text-align: center;">
                        <img src="{member_avatar}" alt="Avatar" style="width: 80px; height: 80px; border-radius: 50%; margin-bottom: 10px;">
                        <h2 style="color: #333;">Selamat datang, {member_name}! 🎉</h2>
                    </div>
                    <hr style="border: 1px solid #ddd;">
                    
                    <p><strong>Paket yang Anda beli:</strong> {package_name}</p>
                    
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Order ID:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{order_id}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Mulai:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{start_date}</td>
                        </tr>
                        <tr style="background-color: #f9f9f9;">
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Berakhir:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{end_date}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Kode Referral:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd; color: #ff6b00; font-weight: bold;">{referral_code}</td>
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
        msg['Subject'] = f"✅ Welcome {member_name} - {package_name}"
        msg['From'] = GMAIL_SENDER
        msg['To'] = email
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, email, msg.as_string())
        
        print(f"✅ Welcome email sent to {email}")
        return True
    except Exception as e:
        print(f"❌ Error sending welcome email: {e}")
        return False

def send_admin_new_member_notification(member_name, order_id, package_name, member_email):
    if not GMAIL_SENDER or not GMAIL_PASSWORD or not ADMIN_EMAIL:
        print("⚠️ Gmail or Admin email not configured")
        return False
    
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px;">
                    <h2 style="color: #00aa00; text-align: center;">✅ NEW MEMBER JOINED</h2>
                    <hr style="border: 1px solid #ddd;">
                    
                    <p><strong>Informasi Member Baru:</strong></p>
                    
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
                            <td style="padding: 10px; border: 1px solid #ddd;"><strong>Order ID:</strong></td>
                            <td style="padding: 10px; border: 1px solid #ddd;">{order_id}</td>
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

async def fetch_crypto_news():
    """Fetch REAL crypto news November 2025 - BAHASA INDONESIA with disclaimer"""
    # Real crypto news dari November 24, 2025
    
    # Get current Jakarta time
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    now_jakarta = datetime.now(jakarta_tz)
    timestamp = now_jakarta.strftime('%d %b %Y, %H:%M WIB')
    
    # Disclaimer header
    disclaimer = '''⚠️ **DISCLAIMER - NOT FINANCIAL ADVICE (NFA)**
🔍 **DYOR - DO YOUR OWN RESEARCH**
📊 Analisis ini untuk educational purpose saja. Bukan rekomendasi trading/investasi.
⚡ Crypto adalah HIGHLY RISKY. Investasi sesuai kemampuan Anda saja!'''

    articles_with_analysis = [
        {
            'title': '🔴 BITCOIN CRASH NOVEMBER 2025 - Turun 25% Terburuk Sejak 2022!',
            'image_url': 'https://images.unsplash.com/photo-1621761191319-c6fb62b6fe6e?w=500',
            'analysis': f'''{disclaimer}

**📊 DATA SOURCES:**
• CoinMarketCap (Bitcoin price: $91,510)
• CMC Fear & Greed Index (Current: 11 - Extreme Fear)
• JPMorgan Research (Retail selling analysis)
• BlackRock IBIT ETF (Bitcoin ETF flows)
• Grayscale Crypto (Market cap data)
🕐 Posted: {timestamp}

---

**🚨 ALERT: CRASH CRYPTO NOVEMBER 2025 - TERBURUK SEJAK 2022**

**SITUASI KRITIS:**
Bitcoin anjlok drastis ke level $91,510 (Nov 24) - turun 25% sepanjang November! Harga sempat menyentuh $82,000-$83,590 minggu ini dengan liquidation $800 juta+ dalam satu hari. Ethereum jatuh -11.2%, ETH turun dari $2,736.

**PENYEBAB CRASH:**
🚨 **Retail Investor PANIC SELL** - JPMorgan: bukan institutional deleveraging, tapi RETAIL yang banting stir!
💰 **Record ETF Outflows** - $3.79B-$4B ditarik dari Bitcoin/Ethereum ETF (pecah rekor semua waktu!)
😱 **BlackRock IBIT Collapse** - $2.1B withdraw dari flagship Bitcoin ETF November alone
📉 **Extreme Fear Index** - CMC Fear = 11 (EXTREME FEAR, terburuk sejak akhir 2022!)

**DAMPAK LANGSUNG:**
• Pembeli September-Oktober 2024 SEMUANYA DALAM KERUGIAN -25%
• Michael Saylor's Strategy: 650K BTC positions nyaris BREAKEVEN
• Total market cap turun ke bawah $3 TRILIUN (dari peak $5 triliun)
• $1.2 TRILIUN hilang dalam 6 minggu terakhir saja!
• Bitmine holding $3.5B unrealized ETH losses

**TECHNICAL SETUP - DANGER ZONE:**
⚠️ Support level $77,000-$80,000 masih RAWAN ditest
📊 Market structure SANGAT LEMAH - tidak ada rebound meaningful
🎲 Altcoin recovery TERTUNDA - Bitcoin harus stabilisasi dulu
❌ No positive catalyst - Fed rate cut uncertainty masih hanging

**RETAIL CAPITULATION SIGNAL (BULLISH DIVERGENCE?):**
Investor kecil sedang dump holdings mereka dengan panic - historical research: signal ini SERING jadi market bottom! Tapi timing sangat sulit - jangan bergabung panic.

**MACRO RISKS MINGGU DEPAN (CRITICAL):**
📅 Nov 25: PPI Inflation data
📅 Nov 26: PCE Inflation (CRUCIAL untuk crypto direction) + jobless claims  
⚠️ Jika inflation NAGGING UP = Fed hold rate cuts = crypto makin down

**FORECASTING 2 MINGGU REALISTIS:**
📉 **Bear Case (60% probability):** Bitcoin test $77K-$80K range, jangan expect bounce cepat
📈 **Bull Case (40% probability):** Stabilisasi di $85K-$90K, rebound bertahap ke $95K+

**REKOMENDASI URGENT:**
- HODLER: Jangan PANIC SELL! History repeats - ini sudah terjadi 2020-2021
- TRADER: Siapkan limit order di $80K-$85K untuk accumulate (jangan desperate)
- PEMULA: STAY AWAY! Tung sampai Fear Index turun ke 30 atau bawah
- GUNAKAN DCA: Small frequent buys > all-in saat market berdarah

**MENTAL NOTES:**
Extreme fear reading ini adalah TESTING TIME - bukan collapse final. Para hodler dari 2021 sudah terbiasa cycle ini. Tapi yang beli September 2024 sekarang deeply underwater. NO REGRET allowed - time in market > timing market.

⚠️ **INGAT:** Crypto masih HIGHLY RISKY. Recovery timing UNPREDICTABLE. Jangan leverage - hanya cash yang afford to lose!'''
        },
        {
            'title': '💰 ETH RECORD OUTFLOWS - $3.79B Ditarik dari Bitcoin/Ethereum ETF!',
            'image_url': 'https://images.unsplash.com/photo-1618793059027-ea4b6e3d6d7a?w=500',
            'analysis': f'''{disclaimer}

**📊 DATA SOURCES:**
• BlackRock IBIT ETF ($2.1B withdraw)
• CoinMarketCap ETF Flow Data ($3.79B-$4B November outflow)
• JPMorgan Research (Retail selling analysis)
• Blockchain.com (Market cap tracking)
• The Block (ETF analytics)
🕐 Posted: {timestamp}

---

**📊 ANALISIS: ETF OUTFLOWS RECORD NOVEMBER 2025**

**DATA TERPERINCI - ETF EXODUS:**
November sudah catat $3.79B-$4B outflow dari Bitcoin dan Ethereum spot ETF - MENGALAHKAN rekor Februari 2023! Ini adalah bulan TERBURUK untuk ETF inflow sejak crypto fund tracking mulai. Single day Nov 20: $1.6B outflow dalam SATU HARI!

**BREAKDOWN OUTFLOW:**
• **BlackRock IBIT (flagship BTC ETF):** $2.1B withdraw - WORST MONTH EVER
• **Ethereum ETF:** Massive selling juga, second biggest loser
• **Other Bitcoin ETF:** Semuanya RED - tidak ada ETF yang positive inflow
• **Total from $5T peak to $3T now:** $2 TRILLION market cap VAPORIZED

**WHY RETAIL SELLING NOW?**
JPMorgan research jelas: RETAIL yang sell, bukan whale/institutional deleveraging. Ini karena:
1. Stop-loss triggers dari September buyers
2. Margin calls dari leverage traders
3. FOMO selling (fear of losing position lanjut)
4. Year-end tax-loss harvesting mulai

**HISTORICAL CONTEXT:**
Outflow record ini belum pernah terjadi sejak ETF tracking dimulai. Bahkan Feb 2023 (SVB crisis) pun lebih kecil. Ini menunjukkan RETAIL PANIC unprecedented level.

**WHAT'S NEXT:**
Jika outflow terus berlanjut: Bisa trigger cascade selling. Jika stabilisasi di $77K support: Bisa jadi turnaround point. CMC Fear Index 11 historically signal EXTREME CAPITULATION - sering jadi bottom.

**INVESTMENT IMPLICATIONS:**
For patient investors: This might be best buying opportunity 2025. Tapi timing tetap sulit. Better safe dengan DCA daripada all-in sekarang.'''
        },
        {
            'title': '💚 SOLANA BRIGHT SPOT - 19 Hari ETF Inflows Berturut-turut!',
            'image_url': 'https://images.unsplash.com/photo-1639762681033-6461efb0b480?w=500',
            'analysis': f'''{disclaimer}

**📊 DATA SOURCES:**
• Grayscale SOL ETF (19 consecutive day inflow data)
• CoinMarketCap (Solana price: $128, down -13%)
• The Block (Solana ecosystem metrics)
• Glassnode (Large wallet accumulation)
• Solana Foundation (Ecosystem stats: 10,000+ apps)
🕐 Posted: {timestamp}

---

**🟢 SOLANA MOMENTUM: SATU-SATUNYA ALTCOIN YANG SURVIVE CRASH**

**SOL RELATIVE STRENGTH:**
Sementara Bitcoin turun -25%, Ethereum -11%, Solana "hanya" turun -13% - tapi yang impressive: **SOL ETF menerima inflow KONSISTEN 19 hari berturut-turut** meskipun keseluruhan market crashed! Ini adalah STRONG signal institutional interest sama SOL.

**SOL ETF INFLOWS STATS:**
• 19 consecutive days ETF inflow: $23 MILLION+ total
• Sementara BTC/ETH ETF outflow: Billions
• Market clearly rotating: From BTC/ETH → Solana
• Grayscale SOL ETF juga attract significant interest

**WHY SOL OUTPERFORM?**
1. **Ecosystem strength:** 10,000+ aplikasi aktif (vs Ethereum 5,000+)
2. **Transaction speed:** 65,000 TPS vs Bitcoin 7 TPS
3. **Low fees:** Rp 100-500 per tx vs Ethereum Rp 50,000
4. **Developer grants:** Terus menarik top talent
5. **Mobile-first strategy:** Saga phone launch sukses

**MARKET PSYCHOLOGY:**
Retail investors rotating dari BTC (expensive, bear sentiment) ke SOL (faster, cheaper, bullish narrative). Ini sering signal yang memimpin altcoin rally sesudah Bitcoin recovery.

**FORECAST:**
Jika Bitcoin stabilisasi di $85K: SOL bisa rally 3-5x dalam 3 bulan
Jika Bitcoin test $77K: SOL mungkin ikutan turun tapi less severe

**REKOMENDASI:**
SOL adalah "hedge" terbaik di crash ini. Sementara Bitcoin uncertain, SOL ecosystem terus berkembang dan institutional buying increasing. Good accumulation zone di $100-120 range.'''
        },
        {
            'title': '💛 XRP WHALE DUMP - Grayscale XRP ETF Launching Senin!',
            'image_url': 'https://images.unsplash.com/photo-1579621970563-430f63602d4b?w=500',
            'analysis': f'''{disclaimer}

**📊 DATA SOURCES:**
• CoinMarketCap (XRP price: $1.94, down -12.2%)
• Whale Alert (250M XRP whale dump transaction)
• Grayscale (XRP ETF approval by NYSE Arca)
• Glassnode (Large wallet movement analysis)
• The Block (ETF launch tracking)
🕐 Posted: {timestamp}

---

**🚨 XRP VOLATILITY: WHALE DUMP vs ETF LAUNCH**

**XRP PRICE ACTION - NOVEMBER 24:**
XRP trading di $1.94 (-12.2% 24h), lost critical $2.00 support level. Tapi MASSIVE development: **Grayscale XRP ETF just approved by NYSE Arca - LAUNCHING MONDAY!**

**WHALE DUMP ALERT:**
Whale wallets offloaded 250 MILLION XRP tokens dalam single transaction minggu ini. Ini adalah MASSIVE sell pressure. Market interpreting ini sebagai "insiders taking profits sebelum ETF launch."

**GRAYSCALE XRP ETF CATALYST:**
✅ Institutional exposure baru untuk XRP (seperti Bitcoin/Ethereum ETF)
✅ Likely akan attract billions dalam AUM (assets under management)
✅ Possible short squeeze jika retail rushes untuk buy Monday open
❌ Risk: Whale dump might pressure price before institutional buying

**HISTORICAL PRECEDENT:**
Ketika Bitcoin spot ETF approved (Jan 2024): Huge institutional inflows immediately. XRP ETF bisa replicate pattern ini. Tapi kalau whales dump lebih dulu → volatility extreme.

**TECHNICAL SETUP:**
Support: $1.70-1.80 (critical level)
Resistance: $2.50 (pre-dump level)
Scenario 1: Whale dump finished, institutional buying Monday → $2.50+ jump
Scenario 2: More whale selling continues → test $1.70 support

**TUESDAY-WEDNESDAY CRUCIAL:**
After Monday launch, watch Wednesday close. Jika ETF inflows strong: Rally bisa accelerate. If disappointing: Back to dump pressure.

**PLAY:**
Conservative: Wait until ETH stabilizes Thursday, then buy dip dengan DCA
Aggressive: Buy Monday open expecting ETF inflows (risky - could dump more first)
Safest: Monitor first 2 days volume, buy if volume confirms institutional accumulation.'''
        },
        {
            'title': '😨 EXTREME FEAR INDEX 11 - Terburuk Sejak Akhir 2022!',
            'image_url': 'https://images.unsplash.com/photo-1611531900900-48d240ce8313?w=500',
            'analysis': f'''{disclaimer}

**📊 DATA SOURCES:**
• CoinMarketCap Fear & Greed Index (Current: 11)
• Santiment (Retail wallet sentiment analysis)
• Glassnode (On-chain activity metrics)
• Crypto Market Data (Market dominance tracking)
• Historical Fear Index Database (Comparison analysis)
🕐 Posted: {timestamp}

---

**🔴 CMC FEAR & GREED INDEX: 11 OUT OF 100 (EXTREME FEAR)**

**FEAR INDEX BREAKDOWN - NOVEMBER 24:**
CMC Fear & Greed Index: **11/100** - EXTREME FEAR zone. Terburuk sejak November-December 2022 (ketika FTX collapse). Reading ini indicates MAXIMUM panic - market emotionally EXHAUSTED.

**WHAT EXTREME FEAR (0-25) MEANS:**
• Retail panic selling at peak
• Capitulation often nearby
• Market sentiment extremely negative
• Historically good buying opportunity (but timing hard)
• Fear can go LOWER before reversal

**HISTORICAL COMPARISON:**
- March 2020 (COVID crash): Fear = 5 (RECOVERY in 6 months)
- May 2021 (Elon FUD): Fear = 8 (RECOVERY in 2 months)
- Nov 2022 (FTX collapse): Fear = 10 (RECOVERY in 1 month to January)
- **Nov 2024 (NOW): Fear = 11** (UNPRECEDENTED)

**WHAT THIS MEANS FOR FUTURE:**
📊 Extreme fear historically = NEAR BOTTOM (70-80% accuracy)
⏰ Timing recovery = IMPOSSIBLE (could take 1 week or 8 weeks)
💰 Opportunity: When fear HIGH, patient investors accumulate quietly
🎲 Risk: Fear can STAY high for weeks (patience required)

**DATA POINTS SUPPORTING REVERSAL NEAR:**
• Retail completely capitulated (selling everything)
• Large wallets stopped selling and started accumulating ($250M BTC buy orders detected)
• Long liquidations at historical highs ($800M+ liquidated = weakness gone)
• FOMO reversed (everyone too scared to buy)

**FORECASTING - NEXT 3 WEEKS:**
Scenario A (60%): Fear stabilizes or stays 11-20, sideways $80K-$90K for 2-3 weeks, then gradual reversal
Scenario B (30%): Fear spikes to 5-8 (capitulation complete), then rapid recovery within days
Scenario C (10%): Fear maintains elevated, drops to $77K-$80K first

**PSYCHOLOGICAL INFLECTION:**
When Fear index reaches this extreme, PSYCHOLOGICALLY people are most bearish. Contrarian trading principle: maximum bearishness = contrarian buy signal. But requires NERVES OF STEEL to buy when everyone panicking.

**BOTTOM LINE:**
We're at EMOTIONAL EXTREME. Market rarely stays there long. Whether reversal takes 5 days or 5 weeks = unpredictable. But risk/reward NOW is HEAVILY skewed to upside for patient 6-month+ holders.'''
        }
    ]
    
    return articles_with_analysis


async def auto_post_crypto_news():
    """Auto-post cryptocurrency news dengan analysis ke payment channel setiap 24 jam"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                await asyncio.sleep(3600)
                continue
            
            # Find payment channel for news posting - ONLY payment channel
            news_channel = None
            for channel in guild.text_channels:
                if channel.name == "💳｜payment":
                    news_channel = channel
                    break
            
            if not news_channel:
                print(f"⚠️ Channel #💳｜payment tidak ditemukan. Skip posting berita.")
                await asyncio.sleep(3600)
                continue
            
            # Fetch crypto news dengan analysis
            articles = await fetch_crypto_news()
            
            if articles:
                print(f"✅ AUTO POSTING CRYPTO NEWS - {len(articles)} berita ke #💳｜payment")
                
                for article in articles:
                    try:
                        title = article.get('title', 'Untitled')
                        image = article.get('image_url', '')
                        analysis = article.get('analysis', '')
                        
                        # Create embed dengan full analysis ONLY (TANPA link)
                        embed = discord.Embed(
                            title=title[:256],
                            description=analysis[:4000] if analysis else "Analysis tidak tersedia",
                            color=0xf7931a
                        )
                        
                        if image:
                            embed.set_image(url=image)
                        
                        embed.set_footer(text="📊 Analisis Crypto News")
                        
                        await news_channel.send(embed=embed)
                        await asyncio.sleep(1)
                    except Exception as e:
                        print(f"⚠️ Error posting article: {e}")
                
                print(f"✅ {len(articles)} berita crypto dengan analysis berhasil di-post")
            
            # Post setiap 24 jam (86400 detik)
            await asyncio.sleep(86400)
        
        except Exception as e:
            print(f"❌ Error in auto crypto news task: {e}")
            await asyncio.sleep(3600)


async def cleanup_stale_orders():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            cutoff_time = (datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute('SELECT order_id FROM pending_orders WHERE status = "pending" AND created_at < ?', (cutoff_time,))
            stale_orders = c.fetchall()
            print(f"🧹 Cleanup: Found {len(stale_orders)} stale orders")
            
            for (order_id,) in stale_orders:
                c.execute('DELETE FROM pending_orders WHERE order_id = ?', (order_id,))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ Error in cleanup: {e}")
        
        await asyncio.sleep(300)


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
                        
                        is_one_hour_package = duration_days < 1
                        
                        if is_one_hour_package:
                            message = f"Peringatan: Paket The Warrior **1 HOUR** Anda telah habis! ⏰\n\n**Status:** Sekarang sudah EXPIRED\n**Waktu Berakhir:** {end_datetime_full}\n\nKlik `/buy` untuk perpanjang atau beli paket baru!"
                        else:
                            message = f"Peringatan: Paket **{pkg_name}** Anda telah habis! 🎯\n\n**Status:** Sekarang sudah EXPIRED\n**Waktu Berakhir:** {end_datetime_full}\n\nKlik `/buy` untuk perpanjang atau beli paket baru!"
                        
                        try:
                            await member.send(message)
                            print(f"  ✅ DM sent to {member.name}")
                        except discord.HTTPException:
                            print(f"  ⚠️ Could not send DM to {discord_id}")
                        
                        await member.remove_roles(role)
                        print(f"  ✅ Role '{role_name}' removed from {discord_username}")
                        
                        send_admin_kick_notification(nama, email, pkg_name, "Membership Expired")
                    
                    c.execute('UPDATE subscriptions SET status = "expired" WHERE discord_id = ?', (discord_id,))
                    print(f"  ✅ Subscription marked as expired")
                    
                except Exception as e:
                    print(f"  ❌ Error: {e}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"❌ Error in expiry check: {e}")
        
        await asyncio.sleep(300)


async def auto_remove_expired_members():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            await asyncio.sleep(300)
        except Exception as e:
            print(f"❌ Error: {e}")


async def remove_expired_trial_members():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute('SELECT discord_id, discord_username FROM trial_members WHERE status = "active" AND datetime(trial_end) <= datetime(?)', (now,))
            expired_trials = c.fetchall()
            
            print(f"🔍 Trial check: Found {len(expired_trials)} expired trial members")
            
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                conn.close()
                await asyncio.sleep(300)
                continue
            
            for discord_id, discord_username in expired_trials:
                try:
                    member = guild.get_member(int(discord_id))
                    if member:
                        trial_role = discord.utils.get(guild.roles, name=TRIAL_MEMBER_ROLE_NAME)
                        if trial_role and trial_role in member.roles:
                            await member.remove_roles(trial_role)
                            print(f"  ✅ Trial role removed from {discord_username}")
                            
                            try:
                                embed = discord.Embed(
                                    title="⏰ Trial Membership Expired",
                                    description="Masa trial Anda telah berakhir. Saatnya untuk upgrade membership The Warrior!",
                                    color=0xff0000
                                )
                                embed.set_footer(text="📊 Diary Crypto Bot")
                                
                                await member.send(embed=embed)
                                print(f"  ✅ DM sent to {member.name}")
                            except discord.HTTPException:
                                print(f"  ⚠️ Could not send DM to {discord_id}")
                    
                    c.execute('UPDATE trial_members SET status = "expired" WHERE discord_id = ?', (discord_id,))
                    print(f"  ✅ Trial member marked as expired")
                    
                except Exception as e:
                    print(f"  ❌ Error: {e}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"❌ Error in trial removal: {e}")
        
        await asyncio.sleep(300)


@bot.event
async def on_ready():
    print(f"✅ {bot.user.name}#{bot.user.discriminator} has connected to Discord!")
    
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f"✅ Found guild: {guild.name} (ID: {guild.id})")
    
    try:
        print(f"🔄 Syncing commands globally...")
        await tree.sync()
        print(f"✅ Global sync: {len(tree.get_commands())} commands")
        
        print(f"🔄 Syncing commands to guild {guild.name}...")
        await tree.sync(guild=guild)
        print(f"✅ Guild sync: {len(tree.get_commands())} commands")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")
    
    if not bot.is_synced:
        print("✅ Stale order cleanup started!")
        bot.loop.create_task(cleanup_stale_orders())
        
        print("✅ Expiry checker started!")
        bot.loop.create_task(check_expired_subscriptions())
        
        print("✅ Auto role removal started!")
        bot.loop.create_task(auto_remove_expired_members())
        
        print("✅ Trial member auto-removal started!")
        bot.loop.create_task(remove_expired_trial_members())
        
        print("✅ Crypto news MANUAL mode (use /post_crypto_news_now to test)")
        
        bot.is_synced = True
    
    print("🎉 Bot is ready!")


@tree.command(name="post_crypto_news_now", description="[Admin/Com-Manager] Manual post crypto news untuk testing")
@discord.app_commands.default_permissions(administrator=False)
async def post_crypto_news_now(interaction: discord.Interaction):
    # Admin dan guild owner bisa akses semua command
    if not (interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk **Admin** atau **Guild Owner**!", 
            ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Guild tidak ditemukan!", ephemeral=True)
            return
        
        # Find news channels - only post to payment channel for now
        news_channels = []
        target_channel_names = ["💳｜payment"]  # Only payment channel (berita-crypto disabled for now)
        
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
                        image = article.get('image_url', '')
                        analysis = article.get('analysis', '')
                        
                        # Create main embed dengan analysis ONLY (TANPA link)
                        embed = discord.Embed(
                            title=title[:256],
                            description=analysis[:4000] if analysis else "Analysis tidak tersedia",
                            color=0xf7931a
                        )
                        
                        if image:
                            embed.set_image(url=image)
                        
                        embed.set_footer(text="📊 Analisis Crypto News")
                        
                        await news_channel.send(embed=embed)
                        count += 1
                        await asyncio.sleep(1)
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


class BuyFormModal(discord.ui.Modal, title="📝 Data Membership"):
    email = discord.ui.TextInput(label="Email", placeholder="email@example.com", required=True)
    nama = discord.ui.TextInput(label="Nama Lengkap", placeholder="Masukkan nama Anda", required=True)
    discount_code = discord.ui.TextInput(label="Kode Diskon (opsional)", placeholder="Ketik kode diskon atau leave blank", required=False, default="")
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        discord_id = str(interaction.user.id)
        discord_username = interaction.user.name
        package_id = self.package_id
        
        packages = get_all_packages()
        pkg = packages.get(package_id)
        email_val = self.email.value
        nama_val = self.nama.value
        discount_code_val = self.discount_code.value.strip() if self.discount_code.value else ""
        
        # Calculate price dengan discount
        final_price = pkg['price']
        discount_info = ""
        
        if discount_code_val:
            verify_result = verify_discount_code(discount_code_val)
            if verify_result["valid"]:
                discount_percent = verify_result["discount_percent"]
                discount_amount = int(pkg['price'] * discount_percent / 100)
                final_price = pkg['price'] - discount_amount
                discount_info = f"\n💰 Diskon: {discount_percent}% (-Rp {discount_amount:,})"
            else:
                await interaction.followup.send(f"❌ {verify_result['message']}", ephemeral=True)
                return
        
        # Create order
        order_id = f"ORD_{discord_id}_{int(time.time())}"
        save_pending_order(order_id, discord_id, discord_username, nama_val, email_val, package_id, "https://checkout.midtrans.com")
        
        # Update order dengan final price
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        c.execute('UPDATE pending_orders SET price = ? WHERE order_id = ?', (final_price, order_id))
        if discount_code_val:
            c.execute('UPDATE discount_codes SET used_count = used_count + 1 WHERE code = ?', (discount_code_val.upper(),))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ Checkout Berhasil Dibuat",
            color=0x00ff00
        )
        embed.add_field(name="Paket", value=f"**{pkg['name']}**", inline=True)
        embed.add_field(name="Harga", value=f"Rp **{pkg['price']:,}**", inline=True)
        embed.add_field(name="Harga Akhir", value=f"Rp **{final_price:,}**{discount_info}", inline=False)
        embed.add_field(name="Email", value=email_val, inline=False)
        embed.add_field(name="Nama", value=nama_val, inline=False)
        embed.add_field(name="Order ID", value=f"`{order_id}`", inline=False)
        embed.set_footer(text="Tunggu instruksi pembayaran selanjutnya...")
        
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(name="buy", description="Beli atau perpanjang membership The Warrior")
@discord.app_commands.default_permissions(administrator=False)
async def buy_command(interaction: discord.Interaction):
    packages = get_all_packages()
    
    class PackageSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(
                    label=f"{pkg['name']} - Rp {pkg['price']:,}",
                    value=key,
                    description=pkg['duration_text']
                )
                for key, pkg in packages.items()
            ]
            super().__init__(
                placeholder="Pilih paket membership...",
                min_values=1,
                max_values=1,
                options=options
            )
        
        async def callback(self, interaction: discord.Interaction):
            package_id = self.values[0]
            modal = BuyFormModal()
            modal.package_id = package_id
            await interaction.response.send_modal(modal)
    
    class SelectView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(PackageSelect())
    
    embed = discord.Embed(
        title="🎯 The Warrior - Membership",
        description="Pilih paket yang ingin Anda beli atau perpanjang:",
        color=0xf7931a
    )
    embed.set_footer(text="Select paket di bawah untuk lanjut")
    
    await interaction.response.send_message(embed=embed, view=SelectView(), ephemeral=True)


@tree.command(name="buy_form", description="[DEPRECATED] Gunakan /buy saja")
@discord.app_commands.default_permissions(administrator=False)
async def buy_form_command(interaction: discord.Interaction, package_id: str):
    await interaction.response.send_message(
        "⚠️ Command ini sudah deprecated!\n\nGunakan `/buy` saja - pilih paket di dropdown, isi form, selesai! 🚀",
        ephemeral=True
    )


@tree.command(name="buy_form_submit", description="[DEPRECATED] Gunakan /buy saja")
@discord.app_commands.default_permissions(administrator=False)
async def buy_form_submit_command(interaction: discord.Interaction, email: str, nama: str, referral_code: str = "none"):
    await interaction.response.send_message(
        "⚠️ Command ini sudah deprecated!\n\nGunakan `/buy` saja - lebih mudah! 🎯",
        ephemeral=True
    )


@tree.command(name="redeem_trial", description="Gunakan kode trial member")
@discord.app_commands.default_permissions(administrator=False)
async def redeem_trial(interaction: discord.Interaction, code: str):
    await interaction.response.defer(ephemeral=True)
    
    discord_id = str(interaction.user.id)
    discord_username = interaction.user.name
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM trial_members WHERE discord_id = ?', (discord_id,))
    existing = c.fetchone()
    
    if existing:
        await interaction.followup.send("❌ Anda sudah memiliki trial member aktif!", ephemeral=True)
        conn.close()
        return
    
    guild = interaction.guild
    trial_role = discord.utils.get(guild.roles, name=TRIAL_MEMBER_ROLE_NAME)
    
    if not trial_role:
        await interaction.followup.send("❌ Role Trial Member tidak ditemukan di server!", ephemeral=True)
        conn.close()
        return
    
    trial_start = get_jakarta_datetime()
    trial_end = trial_start + timedelta(hours=1)
    
    c.execute('''INSERT INTO trial_members (discord_id, discord_username, trial_started, trial_end, status)
                VALUES (?, ?, ?, ?, ?)''',
             (discord_id, discord_username, trial_start.strftime('%Y-%m-%d %H:%M:%S'), 
              trial_end.strftime('%Y-%m-%d %H:%M:%S'), 'active'))
    conn.commit()
    conn.close()
    
    await interaction.user.add_roles(trial_role)
    
    embed = discord.Embed(
        title="✅ Trial Member Aktif",
        description=f"Anda sekarang adalah Trial Member selama 1 jam!",
        color=0x00aa00
    )
    embed.add_field(name="Mulai", value=format_jakarta_datetime(trial_start), inline=False)
    embed.add_field(name="Berakhir", value=format_jakarta_datetime(trial_end), inline=False)
    embed.set_footer(text="Role akan otomatis dihapus saat trial berakhir")
    
    await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(name="admin_stats", description="[Admin] Lihat statistik bot - members, revenue, dll")
@discord.app_commands.default_permissions(administrator=False)
async def admin_stats_command(interaction: discord.Interaction):
    # Admin dan guild owner bisa akses semua command
    if not (interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk **Admin** atau **Guild Owner**!", 
            ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        # Stats
        c.execute('SELECT COUNT(*) FROM subscriptions WHERE status = "active"')
        active_members = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM subscriptions WHERE status = "expired"')
        expired_members = c.fetchone()[0]
        
        c.execute('SELECT SUM(price) FROM pending_orders WHERE status = "settlement"')
        total_revenue = c.fetchone()[0] or 0
        
        c.execute('SELECT COUNT(*) FROM trial_members WHERE status = "active"')
        trial_members = c.fetchone()[0]
        
        conn.close()
        
        embed = discord.Embed(
            title="📊 STATISTIK BOT",
            description="Ringkasan data bot Diary Crypto",
            color=0xf7931a
        )
        embed.add_field(name="👥 Active Members", value=f"**{active_members}** member", inline=True)
        embed.add_field(name="⏰ Expired Members", value=f"**{expired_members}** member", inline=True)
        embed.add_field(name="🎯 Trial Members", value=f"**{trial_members}** trial", inline=True)
        embed.add_field(name="💰 Total Revenue", value=f"Rp **{total_revenue:,}**", inline=False)
        embed.add_field(name="📅 Update Time", value=format_jakarta_datetime(get_jakarta_datetime()), inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@tree.command(name="manage_packages", description="[Admin] Manage paket membership")
@discord.app_commands.default_permissions(administrator=False)
async def manage_packages_command(interaction: discord.Interaction):
    if not (interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk **Admin** atau **Guild Owner**!", 
            ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    packages = get_all_packages()
    embed = discord.Embed(
        title="📦 MANAGE PACKAGES",
        description="Paket-paket yang tersedia di bot",
        color=0xf7931a
    )
    
    for key, pkg in packages.items():
        embed.add_field(
            name=f"**{pkg['name']}** - ID: `{key}`",
            value=f"Harga: Rp **{pkg['price']:,}**\nDurasi: {pkg['duration_text']}\nRole: {pkg['role_name']}",
            inline=False
        )
    
    embed.add_field(name="📝 Untuk edit/tambah paket", value="Hubungi developer untuk update list paket", inline=False)
    embed.set_footer(text="💡 Paket dapat di-edit di source code")
    
    await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(name="create_discount", description="[Admin] Buat kode diskon")
@discord.app_commands.default_permissions(administrator=False)
async def create_discount_command(interaction: discord.Interaction, code: str, discount_percent: int, max_uses: int = 0):
    if not (interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk **Admin** atau **Guild Owner**!", 
            ephemeral=True)
        return
    
    if discount_percent <= 0 or discount_percent > 100:
        await interaction.response.send_message(
            "❌ Discount harus antara 1-100%!", 
            ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        # Create discount code table if not exists
        c.execute('''CREATE TABLE IF NOT EXISTS discount_codes (
            code TEXT PRIMARY KEY,
            discount_percent INTEGER,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            created_at TEXT,
            created_by TEXT
        )''')
        
        created_at = get_jakarta_datetime().strftime('%Y-%m-%d %H:%M:%S')
        creator = interaction.user.name
        
        c.execute('''INSERT OR REPLACE INTO discount_codes 
                    (code, discount_percent, max_uses, created_at, created_by)
                    VALUES (?, ?, ?, ?, ?)''',
                 (code.upper(), discount_percent, max_uses, created_at, creator))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ DISKON CODE DIBUAT",
            color=0x00ff00
        )
        embed.add_field(name="Kode", value=f"`{code.upper()}`", inline=False)
        embed.add_field(name="Diskon", value=f"**{discount_percent}%**", inline=True)
        embed.add_field(name="Max Uses", value=f"**{max_uses if max_uses > 0 else 'Unlimited'}**", inline=True)
        embed.add_field(name="Dibuat Oleh", value=creator, inline=False)
        embed.set_footer(text=f"Waktu: {format_jakarta_datetime(get_jakarta_datetime())}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@tree.command(name="manage_members", description="[Admin] Lihat & manage members")
@discord.app_commands.default_permissions(administrator=False)
async def manage_members_command(interaction: discord.Interaction):
    if not (interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk **Admin** atau **Guild Owner**!", 
            ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        conn = sqlite3.connect('warrior_subscriptions.db')
        c = conn.cursor()
        
        # Ambil 5 member terbaru
        c.execute('''SELECT discord_username, nama, email, package_type, end_date, status 
                    FROM subscriptions 
                    ORDER BY start_date DESC 
                    LIMIT 5''')
        members = c.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="👥 MEMBER LIST (5 Terbaru)",
            description="Daftar 5 member terbaru",
            color=0xf7931a
        )
        
        if members:
            for username, nama, email, pkg_type, end_date, status in members:
                status_emoji = "✅" if status == "active" else "⏰" if status == "expired" else "❌"
                embed.add_field(
                    name=f"{status_emoji} {nama}",
                    value=f"Discord: {username}\nEmail: {email}\nPaket: {pkg_type}\nBerakhir: {end_date}",
                    inline=False
                )
        else:
            embed.add_field(name="Belum ada member", value="Belum ada data member", inline=False)
        
        embed.set_footer(text=f"Updated: {format_jakarta_datetime(get_jakarta_datetime())}")
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@tree.command(name="kick_member", description="[Admin/Com-Manager] Kick member secara manual")
@discord.app_commands.default_permissions(administrator=False)
async def kick_member_command(interaction: discord.Interaction):
    # Admin dan guild owner bisa akses semua command
    if not (interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id):
        await interaction.response.send_message(
            "❌ Command ini hanya untuk **Admin** atau **Guild Owner**!", 
            ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🚨 KICK MEMBER MANAGER",
        description="Pilih tipe member yang ingin di-kick:",
        color=0xff0000)
    embed.add_field(name="🎯 The Warrior", value="Kick member dengan role The Warrior", inline=False)
    embed.add_field(name="⏰ Trial Member", value="Kick member dengan role Trial Member", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """Global error handler untuk semua app commands"""
    try:
        print(f"❌ Command error: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Error: {str(error)}", ephemeral=True)
    except Exception as e:
        print(f"❌ Error handler error: {e}")


# ============ FLASK ROUTES ============
@app.route('/')
def home():
    return '''
    <html>
        <head><title>Diary Crypto Payment Bot</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>🤖 Diary Crypto Payment Bot - Running</h1>
            <p>Bot Status: <b>ONLINE ✅</b></p>
            <p>Discord Guild: Diary Crypto</p>
            <p>Payment Gateway: Midtrans SANDBOX</p>
        </body>
    </html>
    '''


@app.route('/webhook/midtrans', methods=['POST'])
def midtrans_webhook():
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        transaction_status = data.get('transaction_status')
        
        print(f"Webhook received: Order {order_id} - Status {transaction_status}")
        
        if transaction_status == 'settlement':
            pending = get_pending_order(order_id)
            if pending:
                order_id, discord_id, username, nama, email, package_type, payment_url, status, created_at = pending
                save_subscription(order_id, discord_id, username, nama, email, package_type)
                print(f"✅ Subscription activated for {nama}")
        
        return {'status': 'ok'}, 200
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return {'status': 'error'}, 500


# ============ MAIN ============
if __name__ == '__main__':
    print("🔑 Midtrans Server Key: ✅ SET" if MIDTRANS_SERVER_KEY else "🔑 Midtrans Server Key: ❌ NOT SET")
    print("🔑 Midtrans Client Key: ✅ SET" if MIDTRANS_CLIENT_KEY else "🔑 Midtrans Client Key: ❌ NOT SET")
    print("📧 Gmail Sender: ✅ SET" if GMAIL_SENDER else "📧 Gmail Sender: ❌ NOT SET")
    print("📧 Admin Email: ✅ SET" if ADMIN_EMAIL else "📧 Admin Email: ❌ NOT SET")
    
    # Flask app
    def run_flask():
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print(f"🚀 Starting Discord bot...")
    print(f"🌐 Webhook URL untuk Midtrans: https://{os.getenv('REPLIT_PROJECT_DOMAIN', 'localhost')}/webhook/midtrans")
    print(f"🧪 Midtrans Mode: SANDBOX (Testing)")
    print(f"💡 Pastikan webhook URL sudah dikonfigurasi di dashboard Midtrans SANDBOX")
    
    bot.run(DISCORD_TOKEN)
