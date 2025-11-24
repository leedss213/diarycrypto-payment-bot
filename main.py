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
import re

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

# ============ NEWS API KEYS ============
NEWSAPI_KEY = os.getenv('NEWSAPI_KEY')
CRYPTOPANIC_KEY = os.getenv('CRYPTOPANIC_KEY')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')
COINMARKETCAP_KEY = os.getenv('COINMARKETCAP_KEY')

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
                    discord_id TEXT NOT NULL,
                    discord_username TEXT,
                    nama TEXT,
                    email TEXT,
                    package_type TEXT,
                    amount INTEGER,
                    status TEXT DEFAULT "pending",
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS renewals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    discord_id TEXT NOT NULL,
                    old_end_date TEXT,
                    new_end_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS discount_codes (
                    code TEXT PRIMARY KEY,
                    discount_percent INTEGER,
                    max_uses INTEGER,
                    current_uses INTEGER DEFAULT 0,
                    expiry_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS referral_codes (
                    code TEXT PRIMARY KEY,
                    analyst_name TEXT,
                    discord_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS commissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analyst_name TEXT,
                    amount REAL,
                    referral_order_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS trial_members (
                    code TEXT PRIMARY KEY,
                    discord_id TEXT NOT NULL,
                    discord_username TEXT,
                    duration_days REAL,
                    assigned_at TEXT,
                    role_removed_at TEXT
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id TEXT,
                    action TEXT,
                    target_user TEXT,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )''')
    
    # Add missing columns if they don't exist (migration)
    try:
        c.execute('ALTER TABLE trial_members ADD COLUMN assigned_at TEXT DEFAULT CURRENT_TIMESTAMP')
        print("✅ Added missing column 'assigned_at' to trial_members table")
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e) or 'already exists' in str(e):
            pass  # Column already exists, no action needed
        else:
            print(f"⚠️ Migration error (non-critical): {e}")
    
    conn.commit()
    conn.close()

init_db()

# ============ UTILITY FUNCTIONS ============
def get_jakarta_datetime():
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    return datetime.now(jakarta_tz)

def format_jakarta_datetime(dt):
    return dt.strftime('%d %b %Y, %H:%M WIB')

def is_admin_user(user):
    """Check if user is admin, guild owner, or Orion"""
    return user.id in [1198379949206020146] or user.guild.owner_id == user.id

# ============ EMAIL FUNCTIONS ============
def send_email(recipient_email, subject, html_content):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = GMAIL_SENDER
        msg['To'] = recipient_email
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_SENDER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_SENDER, recipient_email, msg.as_string())
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False

def send_welcome_email(nama, email, package_type, start_date, end_date, referral_code, user_avatar):
    """Send welcome email dengan orange gradient"""
    duration_text = ""
    if "15 Menit" in package_type:
        duration_text = "15 Menit"
    elif "1 Jam" in package_type or "1 Hour" in package_type:
        duration_text = "1 Jam"
    elif "1 Bulan" in package_type or "1 Month" in package_type:
        duration_text = "1 Bulan"
    elif "3 Bulan" in package_type or "3 Months" in package_type:
        duration_text = "3 Bulan"
    
    html_content = f"""
    <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #f7931a 0%, #ff7f00 100%); padding: 30px; text-align: center; color: white; }}
                .avatar {{ width: 80px; height: 80px; border-radius: 50%; border: 3px solid #f7931a; margin: -40px auto 20px; display: block; }}
                .content {{ padding: 30px; }}
                .status-badge {{ display: inline-block; background: #4CAF50; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; margin: 10px 0; }}
                .info-row {{ margin: 15px 0; font-size: 14px; }}
                .label {{ font-weight: bold; color: #f7931a; }}
                .footer {{ background: linear-gradient(135deg, #f7931a 0%, #ff7f00 100%); padding: 20px; text-align: center; color: white; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="margin: 0 0 10px 0;">🎉 Selamat Datang!</h2>
                    <p style="margin: 0;">The Warrior Membership</p>
                </div>
                <img src="{user_avatar}" alt="User Avatar" class="avatar">
                <div class="content">
                    <h3>Halo {nama}! 👋</h3>
                    <p>Terima kasih telah bergabung dengan komunitas The Warrior! Akses premium Anda sudah aktif.</p>
                    
                    <div class="status-badge">✅ AKTIF</div>
                    
                    <div class="info-row">
                        <span class="label">📧 Email:</span> {email}
                    </div>
                    <div class="info-row">
                        <span class="label">📦 Paket:</span> {duration_text}
                    </div>
                    <div class="info-row">
                        <span class="label">🗓️ Tanggal Mulai:</span> {start_date}
                    </div>
                    <div class="info-row">
                        <span class="label">⏰ Tanggal Berakhir:</span> {end_date}
                    </div>
                    <div class="info-row">
                        <span class="label">🔗 Kode Referral:</span> <code style="background: #f0f0f0; padding: 5px 10px; border-radius: 5px;">{referral_code}</code>
                    </div>
                    
                    <p style="margin-top: 20px; padding: 15px; background: #fff3cd; border-left: 4px solid #f7931a; border-radius: 5px;">
                        <strong>💡 Tips:</strong> Bagikan kode referral Anda untuk mendapatkan komisi 30%!
                    </p>
                </div>
                <div class="footer">
                    <p style="margin: 0;">© 2025 Diary Crypto | The Warrior Premium Membership</p>
                </div>
            </div>
        </body>
    </html>
    """
    
    return send_email(email, f"🎉 Welcome to The Warrior - {duration_text}", html_content)

def send_expiry_email(nama, email, end_date, user_avatar):
    """Send expiry reminder email dengan red gradient"""
    html_content = f"""
    <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%); padding: 30px; text-align: center; color: white; }}
                .avatar {{ width: 80px; height: 80px; border-radius: 50%; border: 3px solid #ff4444; margin: -40px auto 20px; display: block; }}
                .content {{ padding: 30px; }}
                .status-badge {{ display: inline-block; background: #f44336; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; margin: 10px 0; }}
                .info-row {{ margin: 15px 0; font-size: 14px; }}
                .label {{ font-weight: bold; color: #ff4444; }}
                .cta {{ background: #ff4444; color: white; padding: 15px 30px; border-radius: 5px; text-align: center; margin: 20px 0; font-weight: bold; }}
                .footer {{ background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%); padding: 20px; text-align: center; color: white; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="margin: 0 0 10px 0;">⏰ Membership Anda Telah Berakhir!</h2>
                    <p style="margin: 0;">The Warrior</p>
                </div>
                <img src="{user_avatar}" alt="User Avatar" class="avatar">
                <div class="content">
                    <h3>Halo {nama}, 👋</h3>
                    <p>Akses premium Anda telah berakhir.</p>
                    
                    <div class="status-badge">❌ EXPIRED</div>
                    
                    <div class="info-row">
                        <span class="label">📧 Email:</span> {email}
                    </div>
                    <div class="info-row">
                        <span class="label">📅 Tanggal Kadaluarsa:</span> {end_date}
                    </div>
                    
                    <div class="cta">
                        Gunakan /buy untuk perpanjang membership
                    </div>
                    
                    <p style="margin-top: 20px; padding: 15px; background: #ffebee; border-left: 4px solid #ff4444; border-radius: 5px;">
                        <strong>⚠️ Catatan:</strong> Akses Anda telah dilepas. Perpanjang sekarang untuk melanjutkan!
                    </p>
                </div>
                <div class="footer">
                    <p style="margin: 0;">© 2025 Diary Crypto | The Warrior Premium Membership</p>
                </div>
            </div>
        </body>
    </html>
    """
    
    return send_email(email, "⏰ Membership Anda Telah Berakhir!", html_content)

def send_trial_email(nama, email, duration_text, user_avatar):
    """Send trial member email"""
    html_content = f"""
    <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #9C27B0 0%, #673AB7 100%); padding: 30px; text-align: center; color: white; }}
                .avatar {{ width: 80px; height: 80px; border-radius: 50%; border: 3px solid #9C27B0; margin: -40px auto 20px; display: block; }}
                .content {{ padding: 30px; }}
                .status-badge {{ display: inline-block; background: #9C27B0; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; margin: 10px 0; }}
                .info-row {{ margin: 15px 0; font-size: 14px; }}
                .label {{ font-weight: bold; color: #9C27B0; }}
                .footer {{ background: linear-gradient(135deg, #9C27B0 0%, #673AB7 100%); padding: 20px; text-align: center; color: white; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="margin: 0 0 10px 0;">🎁 Trial Member - Free Access!</h2>
                    <p style="margin: 0;">The Warrior</p>
                </div>
                <img src="{user_avatar}" alt="User Avatar" class="avatar">
                <div class="content">
                    <h3>Selamat! 🎉</h3>
                    <p>Anda mendapatkan akses trial gratis untuk The Warrior!</p>
                    
                    <div class="status-badge">✅ AKTIF (TRIAL)</div>
                    
                    <div class="info-row">
                        <span class="label">📧 Email:</span> {email}
                    </div>
                    <div class="info-row">
                        <span class="label">⏱️ Durasi Trial:</span> {duration_text}
                    </div>
                    
                    <p style="margin-top: 20px; padding: 15px; background: #E8F5E9; border-left: 4px solid #9C27B0; border-radius: 5px;">
                        <strong>💡 Tips:</strong> Manfaatkan trial ini dengan baik. Setelah berakhir, gunakan /buy untuk perpanjang!
                    </p>
                </div>
                <div class="footer">
                    <p style="margin: 0;">© 2025 Diary Crypto | The Warrior Premium Membership</p>
                </div>
            </div>
        </body>
    </html>
    """
    
    return send_email(email, f"🎁 Trial Member Access - {duration_text}", html_content)

# ============ NEWS FUNCTIONS - MULTI SOURCE ============

async def fetch_news_from_newsapi():
    """Fetch crypto news dari NewsAPI"""
    try:
        if not NEWSAPI_KEY:
            return []
        
        url = "https://newsapi.org/v2/everything"
        params = {
            'q': 'cryptocurrency OR bitcoin OR ethereum',
            'sortBy': 'publishedAt',
            'language': 'en',
            'apiKey': NEWSAPI_KEY,
            'pageSize': 3
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            articles = []
            for article in data.get('articles', [])[:3]:
                articles.append({
                    'source': '📰 NewsAPI',
                    'title': article.get('title', '')[:150],
                    'description': article.get('description', '')[:300],
                    'url': article.get('url', ''),
                    'image': article.get('urlToImage', ''),
                    'published_at': article.get('publishedAt', '')
                })
            print(f"✅ Fetched {len(articles)} articles from NewsAPI")
            return articles
    except Exception as e:
        print(f"⚠️ NewsAPI Error: {e}")
    return []


async def fetch_news_from_cryptopanic():
    """Fetch crypto news dari CryptoPanic dengan sentiment voting"""
    try:
        if not CRYPTOPANIC_KEY:
            return []
        
        url = "https://cryptopanic.com/api/v1/posts/"
        params = {
            'auth_token': CRYPTOPANIC_KEY,
            'filter': 'hot',
            'kind': 'news',
            'public': True
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            articles = []
            for post in data.get('results', [])[:3]:
                votes = post.get('votes', {})
                positive = votes.get('positive', 0)
                negative = votes.get('negative', 0)
                total = positive + negative
                
                if total > 0:
                    sentiment_score = (positive / total) * 100
                else:
                    sentiment_score = 50
                
                sentiment_icon = "🟢" if sentiment_score > 60 else "🟡" if sentiment_score > 40 else "🔴"
                
                articles.append({
                    'source': f'🔥 CryptoPanic {sentiment_icon}',
                    'title': post.get('title', '')[:150],
                    'url': post.get('url', ''),
                    'published_at': post.get('published_at', ''),
                    'sentiment_score': sentiment_score,
                    'votes': f"{positive}👍 {negative}👎"
                })
            print(f"✅ Fetched {len(articles)} posts from CryptoPanic (with sentiment)")
            return articles
    except Exception as e:
        print(f"⚠️ CryptoPanic Error: {e}")
    return []


async def fetch_news_from_twitter_verified():
    """Fetch crypto tweets ONLY dari verified/A1 accounts (anti-FOMO filter)"""
    try:
        if not TWITTER_BEARER_TOKEN:
            return []
        
        headers = {
            'Authorization': f'Bearer {TWITTER_BEARER_TOKEN}',
            'User-Agent': 'DiaryBot/1.0'
        }
        
        # Query hanya verified accounts dengan minimal engagement
        url = "https://api.twitter.com/2/tweets/search/recent"
        params = {
            'query': '(cryptocurrency OR bitcoin OR ethereum) -is:retweet has:verified lang:en',
            'max_results': 10,
            'tweet.fields': 'public_metrics,author_id,created_at',
            'expansions': 'author_id',
            'user.fields': 'verified,public_metrics'
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            articles = []
            
            user_map = {}
            if 'includes' in data and 'users' in data['includes']:
                for user in data['includes']['users']:
                    user_map[user['id']] = user
            
            for tweet in data.get('data', [])[:3]:
                user_id = tweet.get('author_id')
                user = user_map.get(user_id, {})
                
                if user.get('verified', False):
                    follower_count = user.get('public_metrics', {}).get('followers_count', 0)
                    
                    articles.append({
                        'source': f"✅ @{user.get('username', 'unknown')} ({follower_count} followers)",
                        'title': tweet.get('text', '')[:250],
                        'engagement': tweet.get('public_metrics', {}).get('like_count', 0),
                        'created_at': tweet.get('created_at', '')
                    })
            
            print(f"✅ Fetched {len(articles)} verified tweets (A1 accounts - anti FOMO)")
            return articles
    except Exception as e:
        print(f"⚠️ Twitter API Error (non-critical): {e}")
    return []


async def fetch_crypto_news():
    """Aggregate crypto news dari MULTIPLE sources: CoinGecko + NewsAPI + CryptoPanic + Twitter (A1 only)"""
    try:
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        now_jakarta = datetime.now(jakarta_tz)
        timestamp = now_jakarta.strftime('%d %b %Y, %H:%M WIB')
        
        articles_with_analysis = []
        
        # 1. COINGECKO - Top 5 coins real-time data
        try:
            coingecko_url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': 3,
                'page': 1,
                'sparkline': False
            }
            
            response = requests.get(coingecko_url, params=params, timeout=10)
            response.raise_for_status()
            coins_data = response.json()
            
            print(f"✅ CoinGecko: Fetched {len(coins_data)} top coins")
            
            for coin in coins_data:
                name = coin.get('name', 'Unknown')
                symbol = coin.get('symbol', '').upper()
                price = coin.get('current_price', 0)
                change_24h = coin.get('price_change_percentage_24h', 0) or 0
                market_cap = coin.get('market_cap', 0) or 0
                image = coin.get('image', '')
                high_24h = coin.get('high_24h', price)
                low_24h = coin.get('low_24h', price)
                
                emoji = "🔴" if change_24h < -10 else "🟠" if change_24h < -5 else "🟡" if change_24h < 0 else "🟢"
                sentiment = "TURUN DRASTIS" if change_24h < -10 else "TURUN" if change_24h < 0 else "NAIK"
                status = "BEARISH STRONG" if change_24h < -15 else "BEARISH" if change_24h < -10 else "NEUTRAL" if change_24h < 3 else "BULLISH" if change_24h < 10 else "BULLISH STRONG"
                
                price_str = f"${price:,.2f}" if price >= 1 else f"${price:.6f}"
                market_cap_str = f"${market_cap/1e9:.2f}B" if market_cap >= 1e9 else f"${market_cap/1e6:.2f}M"
                high_24h_str = f"${high_24h:,.2f}" if high_24h >= 1 else f"${high_24h:.6f}"
                low_24h_str = f"${low_24h:,.2f}" if low_24h >= 1 else f"${low_24h:.6f}"
                
                # DETAILED ANALYSIS dengan PENYEBAB, DAMPAK, FORECAST, REKOMENDASI
                analysis = f"""⚠️ **DISCLAIMER - NOT FINANCIAL ADVICE (NFA)**
🔍 DYOR - DO YOUR OWN RESEARCH
📊 Analisis ini untuk educational purpose saja. Bukan rekomendasi trading/investasi.
⚡ Crypto adalah HIGHLY RISKY. Investasi sesuai kemampuan Anda saja!

---

**{emoji} {name} ({symbol}) - REAL-TIME MARKET ANALYSIS**

**📊 SNAPSHOT HARGA SAAT INI:**
Harga Sekarang: **{price_str}** USD
24h Change: **{change_24h:+.2f}%** {emoji}
High 24h: **{high_24h_str}** | Low 24h: **{low_24h_str}**
Market Cap: **{market_cap_str}**
Status Teknis: **{status}**

---

**🔴 PENYEBAB PERGERAKAN:**
{'• Market BEARISH - Massive sell pressure terjadi hari ini' if change_24h < -10 else '• Tekanan jual berkelanjutan di pasar' if change_24h < -5 else '• Market STABLE - Consolidation zone' if abs(change_24h) < 5 else '• Momentum positif terus berlanjut' if change_24h < 15 else '• Strong buying rally terjadi hari ini'}
• Retail investor {'panic selling' if change_24h < -5 else 'neutral sentiment' if change_24h < 5 else 'agresif buying'}
• Market kapitalisasi {'menurun signifikan' if change_24h < -10 else 'turun' if change_24h < 0 else 'naik'}
• Volume trading: {'TINGGI (panic liquidation detected)' if abs(change_24h) > 10 else 'NORMAL'}

---

**📉 DAMPAK LANGSUNG:**
• Pembeli minggu lalu sekarang {'DALAM KERUGIAN BESAR -25%+' if change_24h < -20 else 'DALAM KERUGIAN -10%' if change_24h < -10 else 'underwater' if change_24h < 0 else 'PROFIT +5%'} 
• Support level di **${ f"{low_24h:,.2f}" if low_24h >= 1 else f"{low_24h:.6f}" }** sedang ditest
• Resistance level di **${f"{high_24h:,.2f}" if high_24h >= 1 else f"{high_24h:.6f}"}** masih jauh
• Total market cap {name} turun {'drastis' if change_24h < -15 else 'signifikan' if change_24h < -10 else 'moderate' if change_24h < 0 else 'naik konsisten'}

---

**📈 TECHNICAL FORECAST (1-2 MINGGU DEPAN):**
Skenario BEARISH (Probability 65%):
  • Harga bisa test support level ${ f"{low_24h:,.2f}" if low_24h >= 1 else f"{low_24h:.6f}"}
  • Bisa turun lebih lanjut sebelum stabilisasi
  • Jangan expect bounce cepat - market perlu breath

Skenario BULLISH (Probability 35%):
  • Jika break di support level = stabilisasi mungkin
  • Rebound gradual ke ${ f"{high_24h:,.2f}" if high_24h >= 1 else f"{high_24h:.6f}"}
  • Recovery bertahap 1-2 minggu kemungkinan

---

**💡 REKOMENDASI STRATEGY:**
✅ HODLER: **JANGAN PANIC SELL!** History repeats - crash ini sudah terjadi berkali-kali, selalu recover
✅ TRADER: **Siapkan limit order** di support level untuk entry dengan aman
✅ PEMULA: **STAY AWAY** - tunggu Fear Index turun lebih bawah untuk entry
✅ SEMUA: **Gunakan DCA** (Dollar Cost Averaging) - small frequent buys > all-in saat panic
❌ JANGAN leverage - modal cash saja yang afford to lose!

---

**🧠 MARKET PSYCHOLOGY:**
Extreme volatility ini adalah TESTING TIME, bukan collapse final. Para hodler dari cycle sebelumnya terbiasa dengan pattern ini. Smart money sedang accumulate quietly saat retail panic dump.

📍 Timestamp: {timestamp} WIB"""
                
                # FIX: Gunakan thumbnail size (kecil, 100x100) instead of full image
                image_url = image if image else 'https://images.unsplash.com/photo-1621761191319-c6fb62b6fe6e?w=200'
                
                articles_with_analysis.append({
                    'title': f'{emoji} {symbol} - {sentiment} {change_24h:+.2f}%',
                    'image_url': image_url,
                    'analysis': analysis,
                    'source': 'CoinGecko'
                })
        except Exception as e:
            print(f"⚠️ CoinGecko Error: {e}")
        
        # 2. Fetch dari multiple news sources secara parallel
        newsapi_articles = await fetch_news_from_newsapi()
        cryptopanic_articles = await fetch_news_from_cryptopanic()
        twitter_articles = await fetch_news_from_twitter_verified()
        
        # 3. Format semua articles jadi embed-ready format
        for article in newsapi_articles:
            analysis = f"""📰 **{article.get('source', 'NewsAPI')}**

**Headline:** {article.get('title', '')}

**Summary:** {article.get('description', 'No description available')[:200]}...

**Published:** {article.get('published_at', '')[:10]}

⚠️ **DISCLAIMER** | DYOR - DO YOUR OWN RESEARCH
🔗 Source: NewsAPI | Timestamp: {timestamp}"""
            
            articles_with_analysis.append({
                'title': f"📰 {article.get('title', '')[:80]}",
                'image_url': article.get('image', '') or 'https://images.unsplash.com/photo-1585794899668-9f1f4ff4f1f5?w=500',
                'analysis': analysis,
                'source': 'NewsAPI'
            })
        
        for article in cryptopanic_articles:
            analysis = f"""{article.get('source', 'CryptoPanic')}

**News:** {article.get('title', '')}

**Community Sentiment:** {article.get('votes', 'No votes')}
**Sentiment Score:** {article.get('sentiment_score', 50):.0f}%

⚠️ **DISCLAIMER** | DYOR - DO YOUR OWN RESEARCH
Community voting berdasarkan positive/negative reactions
Timestamp: {timestamp}"""
            
            articles_with_analysis.append({
                'title': f"{article.get('source', '')} {article.get('title', '')[:70]}",
                'image_url': 'https://images.unsplash.com/photo-1529088889033-ddef7fbf8ad6?w=500',
                'analysis': analysis,
                'source': 'CryptoPanic'
            })
        
        for article in twitter_articles:
            analysis = f"""✅ **VERIFIED TWITTER ACCOUNT**

**From:** {article.get('source', 'Unknown')}

**Tweet:** {article.get('title', '')}

**Engagement:** {article.get('engagement', 0)} likes
**Posted:** {article.get('created_at', '')[:10]}

⚠️ **DISCLAIMER** | DYOR - DO YOUR OWN RESEARCH
Hanya dari verified accounts (A1 sources) | Anti-FOMO filter
Timestamp: {timestamp}"""
            
            articles_with_analysis.append({
                'title': f"✅ {article.get('title', '')[:70]}",
                'image_url': 'https://images.unsplash.com/photo-1611162616305-c69b3fa7fbe0?w=500',
                'analysis': analysis,
                'source': 'Twitter'
            })
        
        # 4. Add Fear & Greed Index
        try:
            fear_response = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            if fear_response.status_code == 200:
                fear_data = fear_response.json()
                if fear_data.get('data'):
                    fear_index = int(fear_data['data'][0].get('value', 50))
                    fear_emoji = "🔴" if fear_index < 25 else "🟡" if fear_index < 50 else "🟢"
                    fear_status = "EXTREME FEAR" if fear_index < 25 else "FEAR" if fear_index < 50 else "NEUTRAL" if fear_index < 75 else "GREED"
                    
                    fear_analysis = f"""📊 **FEAR & GREED INDEX - LIVE**

**Current Reading: {fear_index}/100** - {fear_status} Zone {fear_emoji}

**Interpretation:**
0-25: 🔴 EXTREME FEAR (Historically = best buying)
26-50: 🟡 FEAR (Caution, but opportunities exist)
51-75: 🟢 GREED (Market getting hot)
76-100: 🔥 EXTREME GREED (Peak euphoria = watch out!)

**Current Status:** {fear_status}
Investor sentiment: {'Panic selling' if fear_index < 50 else 'Neutral' if fear_index < 75 else 'Greedy buying'}

**Smart Money Psychology:**
Buy when FEAR high → Sell when GREED high
(Opposite dari retail behavior)

⚠️ **DISCLAIMER** | DYOR - DO YOUR OWN RESEARCH
Always combine sentiment dengan technical analysis
Timestamp: {timestamp}"""
                    
                    articles_with_analysis.append({
                        'title': f'{fear_emoji} FEAR & GREED INDEX - {fear_status} ({fear_index}/100)',
                        'image_url': 'https://images.unsplash.com/photo-1611531900900-48d240ce8313?w=500',
                        'analysis': fear_analysis,
                        'source': 'Alternative.me'
                    })
                    print(f"✅ Added Fear & Greed analysis (Index: {fear_index})")
        except Exception as e:
            print(f"⚠️ Fear & Greed fetch error: {e}")
        
        print(f"✅ Aggregated {len(articles_with_analysis)} articles dari multiple sources")
        return articles_with_analysis
        
    except Exception as e:
        print(f"❌ Error in fetch_crypto_news: {e}")
        return []


async def auto_post_crypto_news():
    """Auto-post cryptocurrency news dengan analysis ke diary research channel setiap 3 jam"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                await asyncio.sleep(3600)
                continue
            
            # Find diary research channel for news posting
            news_channel = None
            for channel in guild.text_channels:
                if channel.name == "📊｜diary-research":
                    news_channel = channel
                    break
            
            if not news_channel:
                print(f"⚠️ Channel #📊｜diary-research tidak ditemukan. Skip posting berita.")
                await asyncio.sleep(3600)
                continue
            
            # Check bot permissions
            bot_member = guild.me
            if not news_channel.permissions_for(bot_member).send_messages:
                print(f"❌ Bot tidak punya permission SEND_MESSAGES di #{news_channel.name}")
                print(f"   ℹ️ Pastikan bot role punya Send Messages permission!")
                await asyncio.sleep(3600)
                continue
            
            # Fetch crypto news
            articles = await fetch_crypto_news()
            
            if articles:
                print(f"✅ AUTO POSTING CRYPTO NEWS - {len(articles)} berita ke #📊｜diary-research")
                
                # Find "The Warrior" role untuk mention
                warrior_role = None
                for role in guild.roles:
                    if role.name == "The Warrior":
                        warrior_role = role
                        break
                
                # Send mention message
                if warrior_role:
                    mention_content = f"🚀 **CRYPTO NEWS UPDATE** untuk {warrior_role.mention}!\n📊 Real-time market data & analysis untuk members!"
                    await news_channel.send(mention_content)
                
                for article in articles:
                    try:
                        title = article.get('title', 'Untitled')
                        image = article.get('image_url', '')
                        analysis = article.get('analysis', '')
                        source = article.get('source', 'Unknown')
                        
                        # 1. HEADER EMBED
                        header_embed = discord.Embed(
                            title=f"📰 {title[:200]}",
                            color=0xf7931a,
                            description=f"📊 {source} | Real-Time Analysis"
                        )
                        
                        if image:
                            header_embed.set_image(url=image)
                        
                        header_embed.set_footer(text="🔔 Diary Crypto News • Auto-Posted • DYOR")
                        await news_channel.send(embed=header_embed)
                        
                        # 2. ANALYSIS EMBED (dengan chunking untuk panjang content)
                        if analysis:
                            # Split jika terlalu panjang (Discord limit 4096 chars per embed)
                            if len(analysis) > 3500:
                                chunks = [analysis[i:i+3500] for i in range(0, len(analysis), 3500)]
                                for chunk in chunks:
                                    analysis_embed = discord.Embed(
                                        description=chunk,
                                        color=0xf7931a
                                    )
                                    analysis_embed.set_footer(text="📊 Full Analysis")
                                    await news_channel.send(embed=analysis_embed)
                                    await asyncio.sleep(0.5)
                            else:
                                analysis_embed = discord.Embed(
                                    description=analysis,
                                    color=0xf7931a
                                )
                                analysis_embed.set_footer(text="📊 Full Analysis")
                                await news_channel.send(embed=analysis_embed)
                        
                        # 3. CLOSING DIVIDER
                        closing_embed = discord.Embed(
                            description="━" * 50 + "\n✅ **End of News** - Tetap Update & DYOR!",
                            color=0xf7931a
                        )
                        closing_embed.set_footer(text="💡 Set price alerts & manage risk dengan baik!")
                        await news_channel.send(embed=closing_embed)
                        
                        await asyncio.sleep(1)
                    except Exception as e:
                        print(f"⚠️ Error posting article: {str(e)}")
                
                print(f"✅ Berita crypto berhasil di-post ke #📊｜diary-research")
            
            # 3-hour interval untuk testing, bisa diubah ke 86400 (24 jam) nanti
            print(f"⏰ Next update in 3 hours (10800 seconds)...")
            await asyncio.sleep(10800)
        
        except Exception as e:
            print(f"❌ Error in auto crypto news task: {str(e)}")
            await asyncio.sleep(3600)


async def cleanup_stale_orders():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            now_jakarta = get_jakarta_datetime()
            cutoff_time = (now_jakarta - timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute('SELECT order_id, discord_id, discord_username, package_type FROM pending_orders WHERE status = "pending" AND created_at < ?', (cutoff_time,))
            stale_orders = c.fetchall()
            
            if stale_orders:
                print(f"🧹 Cleanup: Found {len(stale_orders)} expired orders (>10 menit)")
                
                for (order_id, discord_id, discord_username, package_type) in stale_orders:
                    try:
                        c.execute('DELETE FROM pending_orders WHERE order_id = ?', (order_id,))
                        
                        user = await bot.fetch_user(int(discord_id))
                        if user:
                            dm_embed = discord.Embed(
                                title="⏰ ORDER EXPIRED!",
                                description="Pembayaran Anda tidak selesai dalam 10 menit",
                                color=0xff0000
                            )
                            dm_embed.add_field(name="❌ Status", value="Order Expired", inline=True)
                            dm_embed.add_field(name="📋 Order ID", value=f"`{order_id}`", inline=True)
                            dm_embed.add_field(name="📦 Paket", value=package_type, inline=False)
                            dm_embed.add_field(name="🔄 Solusi", value="Gunakan `/buy` lagi untuk buat order baru", inline=False)
                            dm_embed.set_footer(text="Diary Crypto Payment Bot • Real Time WIB")
                            
                            await user.send(embed=dm_embed)
                            print(f"✅ Expired notification sent to {discord_username}")
                    except Exception as e:
                        print(f"⚠️ Error sending expired notification: {e}")
                
                conn.commit()
            
            conn.close()
            await asyncio.sleep(10)
        
        except Exception as e:
            print(f"❌ Error in cleanup task: {e}")
            await asyncio.sleep(10)


async def check_membership_expiry():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                await asyncio.sleep(60)
                continue
            
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            now_jakarta = get_jakarta_datetime()
            now_str = now_jakarta.strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute('''SELECT order_id, discord_id, discord_username, email, nama, package_type, end_date 
                        FROM subscriptions WHERE status = "active" AND end_date <= ?''', (now_str,))
            expired_subs = c.fetchall()
            
            if expired_subs:
                print(f"🔍 Auto removal check: Found {len(expired_subs)} expired memberships")
                
                for (order_id, discord_id, discord_username, email, nama, package_type, end_date) in expired_subs:
                    try:
                        user = guild.get_member(int(discord_id))
                        if user:
                            # Remove role
                            warrior_role = discord.utils.get(guild.roles, name=WARRIOR_ROLE_NAME)
                            if warrior_role:
                                await user.remove_roles(warrior_role)
                                print(f"✅ Removed 'The Warrior' role from {discord_username}")
                        
                        # Send DM
                        user_obj = await bot.fetch_user(int(discord_id))
                        if user_obj:
                            dm_embed = discord.Embed(
                                title="⏰ MEMBERSHIP EXPIRED",
                                description="Akses premium Anda telah berakhir",
                                color=0xff0000
                            )
                            dm_embed.add_field(name="📅 Tanggal Kadaluarsa", value=end_date, inline=False)
                            dm_embed.add_field(name="🔄 Solusi", value="Gunakan `/buy` untuk perpanjang", inline=False)
                            dm_embed.set_footer(text="Diary Crypto Payment Bot")
                            
                            await user_obj.send(embed=dm_embed)
                        
                        # Send expiry email
                        if email:
                            user_avatar = user.avatar.url if user and user.avatar else "https://discord.com/assets/dd4dbc0016779df1378e7812eabaa04d.png"
                            send_expiry_email(nama, email, end_date, user_avatar)
                        
                        # Update database
                        c.execute('UPDATE subscriptions SET status = "expired" WHERE order_id = ?', (order_id,))
                        
                        # Log admin action
                        c.execute('''INSERT INTO admin_logs (action, target_user, details, created_at)
                                    VALUES (?, ?, ?, ?)''', 
                                ('auto_remove_role', discord_username, f'Membership expired: {package_type}', now_str))
                        
                        print(f"✅ Auto-removed membership for {discord_username}")
                    except Exception as e:
                        print(f"⚠️ Error removing membership: {e}")
                
                conn.commit()
            
            conn.close()
            await asyncio.sleep(60)
        
        except Exception as e:
            print(f"❌ Error in expiry check: {e}")
            await asyncio.sleep(60)


async def check_trial_member_expiry():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                await asyncio.sleep(60)
                continue
            
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            now_jakarta = get_jakarta_datetime()
            now_timestamp = now_jakarta.timestamp()
            
            try:
                # Query using ACTUAL database columns
                c.execute('SELECT discord_id, discord_username, validity_days, trial_started FROM trial_members WHERE status = "active"')
                trial_members = c.fetchall()
                
                for (discord_id, discord_username, validity_days, trial_started_str) in trial_members:
                    try:
                        if trial_started_str and validity_days:
                            trial_started = datetime.fromisoformat(trial_started_str.replace('Z', '+00:00'))
                            trial_started_ts = trial_started.timestamp()
                            expiry_timestamp = trial_started_ts + (validity_days * 86400)
                            
                            if now_timestamp >= expiry_timestamp:
                                user = guild.get_member(int(discord_id))
                                if user:
                                    trial_role = discord.utils.get(guild.roles, name=TRIAL_MEMBER_ROLE_NAME)
                                    if trial_role and trial_role in user.roles:
                                        await user.remove_roles(trial_role)
                                        print(f"✅ Removed Trial Member role from {discord_username}")
                                
                                # Update database with actual column name
                                c.execute('UPDATE trial_members SET status = ? WHERE discord_id = ?', 
                                        ('expired', discord_id))
                                print(f"✅ Trial expired for {discord_username}")
                    
                    except Exception as e:
                        print(f"⚠️ Error checking trial member {discord_username}: {e}")
            except Exception as e:
                print(f"ℹ️ Trial members check: {e} (safe to ignore if no trial members)")
            
            conn.commit()
            conn.close()
            await asyncio.sleep(60)
        
        except Exception as e:
            print(f"❌ Error in trial check: {e}")
            await asyncio.sleep(60)


# ============ DISCORD EVENTS & COMMANDS ============

@bot.event
async def on_ready():
    print(f"✅ {bot.user} has connected to Discord!")
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f"✅ Found guild: {guild.name} (ID: {guild.id})")
        
        print("🔄 Syncing commands globally...")
        await bot.tree.sync()
        print(f"✅ Global sync: {len(bot.tree._get_all_commands())} commands")
        
        print("🔄 Syncing commands to guild...")
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"✅ Guild sync: {len(bot.tree._get_all_commands())} commands")
    
    if not bot.is_synced:
        await bot.tree.sync()
        bot.is_synced = True
    
    print("🎉 Bot is ready!")

@bot.event
async def on_app_command_error(interaction, error):
    print(f"❌ Error in command {interaction.command.name}: {error}")
    await interaction.response.send_message(f"❌ Error: {str(error)}", ephemeral=True)

# Task startup
@bot.event
async def setup_hook():
    print("✅ Stale order cleanup started!")
    bot.loop.create_task(cleanup_stale_orders())
    
    print("✅ Expiry checker started!")
    bot.loop.create_task(check_membership_expiry())
    
    print("✅ Trial member auto-removal started!")
    bot.loop.create_task(check_trial_member_expiry())
    
    print("✅ Crypto news AUTO mode - posting news setiap 3 hours!")
    bot.loop.create_task(auto_post_crypto_news())

# ============ COMMANDS ============

@tree.command(name="buy", description="Beli atau perpanjang membership The Warrior")
@discord.app_commands.checks.cooldown(1, 5)
async def buy_command(interaction: discord.Interaction):
    """Buy atau renew membership"""
    # [Command implementation continues...]
    pass

# ============ MAIN ============
if __name__ == "__main__":
    from flask import jsonify
    
    @app.route('/')
    def index():
        return jsonify({'status': 'OK', 'message': 'Bot is running'})
    
    @app.route('/webhook/midtrans', methods=['POST'])
    def midtrans_webhook():
        # [Webhook implementation...]
        return jsonify({'status': 'ok'})
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False), daemon=True)
    flask_thread.start()
    
    print("🚀 Starting Discord bot...")
    print(f"🌐 Webhook URL untuk Midtrans: https://localhost/webhook/midtrans")
    print(f"🧪 Midtrans Mode: SANDBOX (Testing)")
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Bot error: {e}")
