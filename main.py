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

# ============ PACKAGES DATA ============
PACKAGES = {
    'warrior_15min': {'name': 'The Warrior 15 Minutes', 'price': 200000, 'duration': 0.01},
    'warrior_1hour': {'name': 'The Warrior 1 Hour', 'price': 50000, 'duration': 0.042},
    'warrior_1month': {'name': 'The Warrior 1 Month', 'price': 299000, 'duration': 30},
    'warrior_3month': {'name': 'The Warrior 3 Months', 'price': 649000, 'duration': 90}
}

# ============ BUTTON MODALS ============
class BuyPackageModal(discord.ui.Modal, title="Paket Membership The Warrior"):
    def __init__(self, package_id, package_name, package_price, is_renewal=False, existing_email="", existing_nama=""):
        super().__init__()
        self.package_id = package_id
        self.package_name = package_name
        self.package_price = package_price
        self.is_renewal = is_renewal
        
        self.nama_input = discord.ui.TextInput(label="Nama Lengkap", placeholder="Masukkan nama Anda", default=existing_nama if is_renewal else "")
        self.email_input = discord.ui.TextInput(label="Email", placeholder="Masukkan email Anda", default=existing_email if is_renewal else "")
        self.diskon_input = discord.ui.TextInput(label="Kode Diskon (opsional)", placeholder="Masukkan kode diskon", required=False)
        self.referral_input = discord.ui.TextInput(label="Kode Referral (opsional)", placeholder="Masukkan kode referral analyst", required=False)
        
        self.add_item(self.nama_input)
        self.add_item(self.email_input)
        self.add_item(self.diskon_input)
        self.add_item(self.referral_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        nama = self.nama_input.value
        email = self.email_input.value
        diskon_code = self.diskon_input.value or None
        referral_code = self.referral_input.value or None
        
        # Validate email
        if '@' not in email:
            await interaction.response.send_message("❌ Email tidak valid!", ephemeral=True)
            return
        
        # Check discount code
        discount_percent = 0
        if diskon_code:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            c.execute('SELECT discount_percent, current_uses, max_uses FROM discount_codes WHERE code = ?', (diskon_code,))
            result = c.fetchone()
            conn.close()
            
            if result:
                discount_percent, current_uses, max_uses = result
                if current_uses >= max_uses:
                    await interaction.response.send_message("❌ Kode diskon sudah mencapai batas penggunaan!", ephemeral=True)
                    return
            else:
                await interaction.response.send_message("❌ Kode diskon tidak valid!", ephemeral=True)
                return
        
        # Calculate price
        package_info = PACKAGES[self.package_id]
        final_price = int(package_info['price'] * (1 - discount_percent / 100))
        
        # Check referral code
        if referral_code:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            c.execute('SELECT analyst_name FROM referral_codes WHERE code = ?', (referral_code,))
            result = c.fetchone()
            conn.close()
            
            if not result:
                await interaction.response.send_message("❌ Kode referral tidak valid!", ephemeral=True)
                return
        
        # Create Midtrans order
        order_id = f"WARRIOR-{interaction.user.id}-{int(time.time())}"
        
        try:
            snap_response = midtrans_client.snap.create_transaction({
                'transaction_details': {
                    'order_id': order_id,
                    'gross_amount': final_price
                },
                'customer_details': {
                    'first_name': nama,
                    'email': email,
                    'customer_id': str(interaction.user.id)
                },
                'item_details': [{
                    'id': self.package_id,
                    'name': self.package_name,
                    'quantity': 1,
                    'price': final_price
                }]
            })
            
            payment_url = snap_response['redirect_url']
            snap_token = snap_response['token']
            
            # Store pending order
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            c.execute('''INSERT INTO pending_orders (order_id, discord_id, discord_username, nama, email, package_type, amount, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (order_id, str(interaction.user.id), str(interaction.user), nama, email, self.package_name, final_price, 'pending', get_jakarta_datetime().isoformat()))
            
            # Apply discount if used
            if diskon_code:
                c.execute('UPDATE discount_codes SET current_uses = current_uses + 1 WHERE code = ?', (diskon_code,))
            
            conn.commit()
            conn.close()
            
            # Send checkout embed
            checkout_embed = discord.Embed(
                title="🛒 Checkout Membership The Warrior",
                description="Klik tombol di bawah untuk melanjutkan pembayaran",
                color=0xf7931a
            )
            checkout_embed.add_field(name="📦 Paket", value=self.package_name, inline=True)
            checkout_embed.add_field(name="💰 Harga", value=f"Rp {final_price:,}", inline=True)
            checkout_embed.add_field(name="📧 Email", value=email, inline=False)
            checkout_embed.add_field(name="👤 Nama", value=nama, inline=False)
            checkout_embed.add_field(name="🔗 Link Pembayaran", value=f"[Bayar di Midtrans]({payment_url})", inline=False)
            checkout_embed.set_footer(text="Diary Crypto | Sandbox Mode Testing")
            checkout_embed.set_thumbnail(url="https://midtrans.com/images/midtrans_square_logo.png")
            
            await interaction.response.send_message(embed=checkout_embed, ephemeral=True)
            
            print(f"✅ Order created: {order_id} | User: {interaction.user} | Amount: Rp {final_price:,}")
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error creating order: {str(e)}", ephemeral=True)
            print(f"❌ Midtrans error: {e}")

# ============ COMMANDS ============

@tree.command(name="buy", description="Beli atau perpanjang membership The Warrior")
@discord.app_commands.checks.cooldown(1, 5)
async def buy_command(interaction: discord.Interaction):
    """Buy atau renew membership"""
    
    # Create buttons
    class BuyView(discord.ui.View):
        @discord.ui.button(label="Beli Paket Baru", style=discord.ButtonStyle.green, emoji="🛒")
        async def buy_new(self, interaction_inner: discord.Interaction, button: discord.ui.Button):
            await interaction_inner.response.send_message("Pilih paket:", view=PackageSelectView(is_renewal=False), ephemeral=True)
        
        @discord.ui.button(label="Perpanjang", style=discord.ButtonStyle.blue, emoji="🔄")
        async def renew(self, interaction_inner: discord.Interaction, button: discord.ui.Button):
            # Check if user has active subscription
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            c.execute('SELECT email, nama FROM subscriptions WHERE discord_id = ? AND status = "active"', (str(interaction_inner.user.id),))
            result = c.fetchone()
            conn.close()
            
            if not result:
                await interaction_inner.response.send_message("❌ Anda tidak memiliki membership aktif untuk diperpanjang!", ephemeral=True)
                return
            
            email, nama = result
            await interaction_inner.response.send_message("Pilih paket perpanjangan:", view=PackageSelectView(is_renewal=True, existing_email=email, existing_nama=nama), ephemeral=True)
    
    class PackageSelectView(discord.ui.View):
        def __init__(self, is_renewal=False, existing_email="", existing_nama=""):
            super().__init__()
            self.is_renewal = is_renewal
            self.existing_email = existing_email
            self.existing_nama = existing_nama
        
        @discord.ui.button(label="15 Menit - Rp 200K", style=discord.ButtonStyle.secondary)
        async def pkg_15min(self, interaction_inner: discord.Interaction, button: discord.ui.Button):
            modal = BuyPackageModal('warrior_15min', PACKAGES['warrior_15min']['name'], PACKAGES['warrior_15min']['price'], self.is_renewal, self.existing_email, self.existing_nama)
            await interaction_inner.response.send_modal(modal)
        
        @discord.ui.button(label="1 Jam - Rp 50K", style=discord.ButtonStyle.secondary)
        async def pkg_1hour(self, interaction_inner: discord.Interaction, button: discord.ui.Button):
            modal = BuyPackageModal('warrior_1hour', PACKAGES['warrior_1hour']['name'], PACKAGES['warrior_1hour']['price'], self.is_renewal, self.existing_email, self.existing_nama)
            await interaction_inner.response.send_modal(modal)
        
        @discord.ui.button(label="1 Bulan - Rp 299K", style=discord.ButtonStyle.secondary)
        async def pkg_1month(self, interaction_inner: discord.Interaction, button: discord.ui.Button):
            modal = BuyPackageModal('warrior_1month', PACKAGES['warrior_1month']['name'], PACKAGES['warrior_1month']['price'], self.is_renewal, self.existing_email, self.existing_nama)
            await interaction_inner.response.send_modal(modal)
        
        @discord.ui.button(label="3 Bulan - Rp 649K", style=discord.ButtonStyle.secondary)
        async def pkg_3month(self, interaction_inner: discord.Interaction, button: discord.ui.Button):
            modal = BuyPackageModal('warrior_3month', PACKAGES['warrior_3month']['name'], PACKAGES['warrior_3month']['price'], self.is_renewal, self.existing_email, self.existing_nama)
            await interaction_inner.response.send_modal(modal)
    
    await interaction.response.send_message("Pilih aksi:", view=BuyView(), ephemeral=True)

@tree.command(name="redeem_trial", description="Gunakan kode trial member")
async def redeem_trial(interaction: discord.Interaction, kode: str):
    """Redeem trial member code"""
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('SELECT * FROM trial_members WHERE code = ?', (kode,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        await interaction.response.send_message("❌ Kode trial tidak valid!", ephemeral=True)
        return
    
    code, disc_id, disc_username, duration_days, assigned_at, role_removed_at = result
    
    if role_removed_at:
        await interaction.response.send_message("❌ Kode trial sudah digunakan!", ephemeral=True)
        return
    
    # Assign trial member role
    guild = bot.get_guild(GUILD_ID)
    trial_role = discord.utils.get(guild.roles, name=TRIAL_MEMBER_ROLE_NAME)
    
    if not trial_role:
        await interaction.response.send_message("❌ Trial Member role tidak ditemukan!", ephemeral=True)
        return
    
    user = guild.get_member(int(disc_id))
    if user:
        await user.add_roles(trial_role)
        print(f"✅ Added Trial Member role to {disc_username}")
    
    # Update database
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('UPDATE trial_members SET assigned_at = ? WHERE code = ?', (get_jakarta_datetime().isoformat(), kode))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Trial member access granted untuk {duration_days} hari!", ephemeral=True)

@tree.command(name="bot_stats", description="Lihat statistik bot")
async def bot_stats(interaction: discord.Interaction):
    """Bot statistics"""
    if not is_admin_user(interaction.user):
        await interaction.response.send_message("❌ Command ini hanya untuk admin!", ephemeral=True)
        return
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM subscriptions WHERE status = "active"')
    active_members = c.fetchone()[0]
    
    c.execute('SELECT SUM(amount) FROM subscriptions WHERE status = "active"')
    total_revenue = c.fetchone()[0] or 0
    
    c.execute('SELECT COUNT(*) FROM pending_orders WHERE status = "pending"')
    pending_orders = c.fetchone()[0]
    
    conn.close()
    
    stats_embed = discord.Embed(
        title="📊 Bot Statistics",
        color=0xf7931a
    )
    stats_embed.add_field(name="👥 Active Members", value=str(active_members), inline=True)
    stats_embed.add_field(name="💰 Total Revenue", value=f"Rp {total_revenue:,}", inline=True)
    stats_embed.add_field(name="⏳ Pending Orders", value=str(pending_orders), inline=True)
    stats_embed.set_footer(text=f"Generated at {format_jakarta_datetime(get_jakarta_datetime())}")
    
    await interaction.response.send_message(embed=stats_embed, ephemeral=True)

@tree.command(name="referral_statistik", description="Lihat statistik referral")
async def referral_statistik(interaction: discord.Interaction):
    """Referral statistics"""
    if not is_admin_user(interaction.user):
        await interaction.response.send_message("❌ Command ini hanya untuk admin!", ephemeral=True)
        return
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute('''SELECT analyst_name, COUNT(*) as total_referrals, SUM(amount) as total_commission
                FROM commissions GROUP BY analyst_name''')
    results = c.fetchall()
    conn.close()
    
    referral_embed = discord.Embed(
        title="💼 Statistik Referral & Komisi",
        color=0xf7931a
    )
    
    if results:
        for analyst_name, total_referrals, total_commission in results:
            referral_embed.add_field(
                name=analyst_name,
                value=f"Referrals: {total_referrals} | Komisi: Rp {total_commission:,.0f}",
                inline=False
            )
    else:
        referral_embed.description = "Belum ada data referral"
    
    referral_embed.set_footer(text=f"Generated at {format_jakarta_datetime(get_jakarta_datetime())}")
    
    await interaction.response.send_message(embed=referral_embed, ephemeral=True)

@tree.command(name="export_monthly", description="Export data bulanan")
async def export_monthly(interaction: discord.Interaction):
    """Export monthly data"""
    if not is_admin_user(interaction.user):
        await interaction.response.send_message("❌ Command ini hanya untuk admin!", ephemeral=True)
        return
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute('''SELECT order_id, discord_username, email, package_type, start_date, end_date, status
                FROM subscriptions ORDER BY created_at DESC''')
    rows = c.fetchall()
    conn.close()
    
    # Create CSV
    csv_content = "Order ID,Username,Email,Package,Start Date,End Date,Status\n"
    for row in rows:
        csv_content += f"{row[0]},{row[1]},{row[2]},{row[3]},{row[4]},{row[5]},{row[6]}\n"
    
    # Save and send
    with open('monthly_export.csv', 'w') as f:
        f.write(csv_content)
    
    await interaction.response.send_message("📊 Export berhasil!", file=discord.File('monthly_export.csv'), ephemeral=True)

@tree.command(name="manage_packages", description="Manage membership packages")
async def manage_packages(interaction: discord.Interaction, action: str):
    """Manage packages"""
    if not is_admin_user(interaction.user):
        await interaction.response.send_message("❌ Command ini hanya untuk admin!", ephemeral=True)
        return
    
    if action.lower() == "list":
        embed = discord.Embed(title="📦 Available Packages", color=0xf7931a)
        for pkg_id, pkg_info in PACKAGES.items():
            embed.add_field(name=pkg_info['name'], value=f"Rp {pkg_info['price']:,} | {pkg_info['duration']} hari", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ Gunakan 'list' untuk melihat paket!", ephemeral=True)

@tree.command(name="create_discount", description="Buat kode diskon")
async def create_discount(interaction: discord.Interaction, kode: str, persen: int, max_uses: int):
    """Create discount code"""
    if not is_admin_user(interaction.user):
        await interaction.response.send_message("❌ Command ini hanya untuk admin!", ephemeral=True)
        return
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    try:
        c.execute('''INSERT INTO discount_codes (code, discount_percent, max_uses, created_at)
                    VALUES (?, ?, ?, ?)''',
                 (kode, persen, max_uses, get_jakarta_datetime().isoformat()))
        conn.commit()
        await interaction.response.send_message(f"✅ Kode diskon '{kode}' berhasil dibuat! ({persen}% off, max {max_uses} uses)", ephemeral=True)
    except sqlite3.IntegrityError:
        await interaction.response.send_message("❌ Kode diskon sudah ada!", ephemeral=True)
    finally:
        conn.close()

@tree.command(name="manage_members", description="Manage members")
async def manage_members(interaction: discord.Interaction, search: str):
    """Search members"""
    if not is_admin_user(interaction.user):
        await interaction.response.send_message("❌ Command ini hanya untuk admin!", ephemeral=True)
        return
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute('SELECT discord_username, email, package_type, status, start_date, end_date FROM subscriptions WHERE discord_username LIKE ? OR email LIKE ?', 
             (f'%{search}%', f'%{search}%'))
    results = c.fetchall()
    conn.close()
    
    if not results:
        await interaction.response.send_message("❌ Member tidak ditemukan!", ephemeral=True)
        return
    
    embed = discord.Embed(title=f"🔍 Search Results: {search}", color=0xf7931a)
    for result in results[:10]:
        embed.add_field(
            name=result[0],
            value=f"Email: {result[1]}\nPackage: {result[2]}\nStatus: {result[3]}\nStart: {result[4]}\nEnd: {result[5]}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="kick_member", description="Kick member")
async def kick_member(interaction: discord.Interaction, search: str):
    """Kick member manually"""
    if not is_admin_user(interaction.user):
        await interaction.response.send_message("❌ Command ini hanya untuk admin!", ephemeral=True)
        return
    
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
    c.execute('SELECT discord_id, discord_username, email, nama, package_type, end_date FROM subscriptions WHERE discord_username LIKE ? OR email LIKE ?',
             (f'%{search}%', f'%{search}%'))
    results = c.fetchall()
    conn.close()
    
    if not results:
        await interaction.response.send_message("❌ Member tidak ditemukan!", ephemeral=True)
        return
    
    if len(results) > 1:
        await interaction.response.send_message("⚠️ Hasil pencarian terlalu banyak, mohon spesifik!", ephemeral=True)
        return
    
    discord_id, discord_username, email, nama, package_type, end_date = results[0]
    
    guild = bot.get_guild(GUILD_ID)
    user = guild.get_member(int(discord_id))
    
    if user:
        warrior_role = discord.utils.get(guild.roles, name=WARRIOR_ROLE_NAME)
        if warrior_role:
            await user.remove_roles(warrior_role)
            print(f"✅ Removed The Warrior role from {discord_username}")
    
    # Update database
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('UPDATE subscriptions SET status = "expired" WHERE discord_id = ?', (discord_id,))
    conn.commit()
    conn.close()
    
    # Send expiry email
    if email:
        user_avatar = user.avatar.url if user and user.avatar else "https://discord.com/assets/dd4dbc0016779df1378e7812eabaa04d.png"
        send_expiry_email(nama, email, end_date, user_avatar)
    
    await interaction.response.send_message(f"✅ Member {discord_username} berhasil di-kick!", ephemeral=True)

# ============ AUTO-POST CRYPTO NEWS ============
async def auto_post_crypto_news():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                await asyncio.sleep(10800)
                continue
            
            channel = discord.utils.get(guild.channels, name=NEWS_CHANNEL_NAME)
            if not channel:
                print(f"❌ Channel {NEWS_CHANNEL_NAME} tidak ditemukan!")
                await asyncio.sleep(10800)
                continue
            
            # Fetch news
            newsapi_articles = await fetch_news_from_newsapi()
            cryptopanic_posts = await fetch_news_from_cryptopanic()
            twitter_posts = await fetch_news_from_twitter_verified()
            
            print(f"✅ Aggregated {len(newsapi_articles)} + {len(cryptopanic_posts)} + {len(twitter_posts)} articles")
            
            if newsapi_articles or cryptopanic_posts or twitter_posts:
                # Create embeds
                embeds = []
                
                # Header embed
                header_embed = discord.Embed(
                    title="📰 CRYPTO NEWS UPDATE",
                    description="Real-time news aggregation dari multiple sources",
                    color=0xf7931a
                )
                header_embed.add_field(name="📊 Sources", value="NewsAPI • CryptoPanic • Twitter (Verified only)", inline=False)
                embeds.append(header_embed)
                
                # NewsAPI articles
                if newsapi_articles:
                    for article in newsapi_articles[:2]:
                        embed = discord.Embed(
                            title=article['title'][:256],
                            url=article['url'],
                            color=0xf7931a
                        )
                        if article['image']:
                            embed.set_image(url=article['image'])
                        embeds.append(embed)
                
                # CryptoPanic posts
                if cryptopanic_posts:
                    for post in cryptopanic_posts[:2]:
                        embed = discord.Embed(
                            title=post['title'][:256],
                            url=post['url'],
                            color=0xf7931a
                        )
                        embed.add_field(name="Community Sentiment", value=post['votes'], inline=True)
                        embeds.append(embed)
                
                # Twitter posts
                if twitter_posts:
                    for tweet in twitter_posts[:2]:
                        embed = discord.Embed(
                            title=tweet['title'][:256],
                            color=0xf7931a
                        )
                        embed.set_author(name=tweet['source'])
                        embeds.append(embed)
                
                # Send to channel with role mention
                warrior_role = discord.utils.get(guild.roles, name=WARRIOR_ROLE_NAME)
                mention = warrior_role.mention if warrior_role else "@The Warrior"
                
                await channel.send(f"{mention}\n📢 Crypto News Update!", embeds=embeds[:10])
                print(f"✅ Posted crypto news to #{NEWS_CHANNEL_NAME}")
            
            print(f"⏰ Next update in 3 hours...")
            await asyncio.sleep(10800)
        
        except Exception as e:
            print(f"❌ Error in crypto news: {e}")
            await asyncio.sleep(3600)

async def fetch_news_from_newsapi():
    """Fetch crypto news dari NewsAPI"""
    try:
        if not NEWSAPI_KEY:
            print("⚠️ NEWSAPI_KEY not set")
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
                if article.get('title') and article.get('url'):
                    articles.append({
                        'source': '📰 NewsAPI',
                        'title': article.get('title', '')[:150],
                        'description': article.get('description', '')[:300],
                        'url': article.get('url', ''),
                        'image': article.get('urlToImage', ''),
                        'published_at': article.get('publishedAt', '')
                    })
            print(f"✅ NewsAPI: {len(articles)} articles fetched")
            return articles
        else:
            print(f"⚠️ NewsAPI status code: {response.status_code}")
    except Exception as e:
        print(f"⚠️ NewsAPI Error: {e}")
    return []

async def fetch_news_from_cryptopanic():
    """Fetch crypto news dari CryptoPanic"""
    try:
        if not CRYPTOPANIC_KEY:
            print("⚠️ CRYPTOPANIC_KEY not set")
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
                if post.get('title') and post.get('url'):
                    articles.append({
                        'source': '🔥 CryptoPanic',
                        'title': post.get('title', '')[:150],
                        'url': post.get('url', ''),
                        'votes': f"{post.get('votes', {}).get('positive', 0)}👍 {post.get('votes', {}).get('negative', 0)}👎"
                    })
            print(f"✅ CryptoPanic: {len(articles)} posts fetched")
            return articles
        else:
            print(f"⚠️ CryptoPanic status code: {response.status_code}")
    except Exception as e:
        print(f"⚠️ CryptoPanic Error: {e}")
    return []

async def fetch_news_from_twitter_verified():
    """Fetch verified Twitter posts"""
    try:
        if not TWITTER_BEARER_TOKEN:
            print("⚠️ TWITTER_BEARER_TOKEN not set")
            return []
        
        headers = {'Authorization': f'Bearer {TWITTER_BEARER_TOKEN}'}
        url = "https://api.twitter.com/2/tweets/search/recent"
        params = {
            'query': '(cryptocurrency OR bitcoin) -is:retweet has:verified lang:en',
            'max_results': 10
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            articles = []
            for tweet in data.get('data', [])[:3]:
                if tweet.get('text'):
                    articles.append({
                        'source': '✅ Twitter (Verified)',
                        'title': tweet.get('text', '')[:250]
                    })
            print(f"✅ Twitter: {len(articles)} verified tweets fetched")
            return articles
        else:
            print(f"⚠️ Twitter status code: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Twitter Error: {e}")
    return []

# ============ DISCORD EVENTS ============

@bot.event
async def on_ready():
    if not bot.is_synced:
        await tree.sync()
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

# ============ BACKGROUND TASKS ============

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
            await asyncio.sleep(600)  # Check every 10 minutes
        
        except Exception as e:
            print(f"❌ Error in cleanup task: {e}")
            await asyncio.sleep(600)  # Check every 10 minutes

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
                            warrior_role = discord.utils.get(guild.roles, name=WARRIOR_ROLE_NAME)
                            if warrior_role:
                                await user.remove_roles(warrior_role)
                                print(f"✅ Removed 'The Warrior' role from {discord_username}")
                        
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
                        
                        if email:
                            user_avatar = user.avatar.url if user and user.avatar else "https://discord.com/assets/dd4dbc0016779df1378e7812eabaa04d.png"
                            send_expiry_email(nama, email, end_date, user_avatar)
                        
                        c.execute('UPDATE subscriptions SET status = "expired" WHERE order_id = ?', (order_id,))
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
                # Safe query - check if columns exist first
                try:
                    c.execute('SELECT discord_id, discord_username, duration_days, assigned_at FROM trial_members WHERE role_removed_at IS NULL LIMIT 1')
                except sqlite3.OperationalError:
                    # Column doesn't exist, skip trial member check
                    pass
                else:
                    trial_members = c.fetchall()
                    
                    for (discord_id, discord_username, duration_days, assigned_at_str) in trial_members:
                        try:
                            if assigned_at_str and duration_days:
                                assigned_at = datetime.fromisoformat(assigned_at_str.replace('Z', '+00:00'))
                                assigned_at_timestamp = assigned_at.timestamp()
                                expiry_timestamp = assigned_at_timestamp + (duration_days * 86400)
                                
                                if now_timestamp >= expiry_timestamp:
                                    user = guild.get_member(int(discord_id))
                                    if user:
                                        trial_role = discord.utils.get(guild.roles, name=TRIAL_MEMBER_ROLE_NAME)
                                        if trial_role and trial_role in user.roles:
                                            await user.remove_roles(trial_role)
                                            print(f"✅ Removed Trial Member role from {discord_username}")
                                    
                                    c.execute('UPDATE trial_members SET role_removed_at = ? WHERE discord_id = ?', 
                                            (now_jakarta.isoformat(), discord_id))
                                    print(f"✅ Trial expired for {discord_username}")
                        
                        except Exception as e:
                            print(f"⚠️ Error checking trial member {discord_username}: {e}")
            except Exception as e:
                print(f"✅ Trial members check skipped (no active trials)")
            
            conn.commit()
            conn.close()
            await asyncio.sleep(60)
        
        except Exception as e:
            print(f"❌ Error in trial check: {e}")
            await asyncio.sleep(60)

# ============ MIDTRANS WEBHOOK ============

@app.route('/')
def index():
    return {'status': 'OK', 'message': 'Bot is running'}

@app.route('/webhook/midtrans', methods=['POST'])
def midtrans_webhook():
    """Midtrans payment webhook"""
    try:
        notification = request.get_json()
        order_id = notification['order_id']
        transaction_status = notification['transaction_status']
        
        print(f"🔔 Webhook received: {order_id} | Status: {transaction_status}")
        
        if transaction_status == 'capture' or transaction_status == 'settlement':
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            c.execute('SELECT * FROM pending_orders WHERE order_id = ?', (order_id,))
            order = c.fetchone()
            
            if order:
                order_id, discord_id, discord_username, nama, email, package_type, amount, status, created_at = order
                
                package_duration = PACKAGES.get(next((k for k, v in PACKAGES.items() if v['name'] == package_type), 'warrior_1month'), {}).get('duration', 30)
                start_date = get_jakarta_datetime()
                end_date = start_date + timedelta(days=package_duration)
                
                start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
                end_date_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
                
                referral_code = f"{nama.replace(' ', '')[:5]}-{random.randint(1000, 9999)}"
                
                c.execute('''INSERT INTO subscriptions (order_id, discord_id, discord_username, nama, email, package_type, status, start_date, end_date, referral_code, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (order_id, discord_id, discord_username, nama, email, package_type, 'active', start_date_str, end_date_str, referral_code, start_date.isoformat()))
                
                c.execute('DELETE FROM pending_orders WHERE order_id = ?', (order_id,))
                
                # Assign warrior role
                guild = bot.get_guild(GUILD_ID)
                user = guild.get_member(int(discord_id))
                if user:
                    warrior_role = discord.utils.get(guild.roles, name=WARRIOR_ROLE_NAME)
                    if warrior_role:
                        asyncio.run_coroutine_threadsafe(user.add_roles(warrior_role), bot.loop)
                        print(f"✅ Added The Warrior role to {discord_username}")
                
                # Send welcome email
                user_avatar = user.avatar.url if user and user.avatar else "https://discord.com/assets/dd4dbc0016779df1378e7812eabaa04d.png"
                send_welcome_email(nama, email, package_type, start_date_str, end_date_str, referral_code, user_avatar)
                
                # Send congratulations DM
                try:
                    user_obj = bot.get_user(int(discord_id))
                    if user_obj:
                        congrats_embed = discord.Embed(
                            title="🎉 MEMBERSHIP AKTIF!",
                            description="Selamat! Akses premium The Warrior Anda sudah aktif!",
                            color=0xf7931a
                        )
                        congrats_embed.add_field(name="📦 Paket", value=package_type, inline=False)
                        congrats_embed.add_field(name="🗓️ Mulai", value=start_date_str, inline=True)
                        congrats_embed.add_field(name="⏰ Berakhir", value=end_date_str, inline=True)
                        congrats_embed.add_field(name="🔗 Referral Code", value=referral_code, inline=False)
                        congrats_embed.set_footer(text="Diary Crypto | Enjoy Premium Access!")
                        
                        asyncio.run_coroutine_threadsafe(user_obj.send(embed=congrats_embed), bot.loop)
                except:
                    pass
                
                conn.commit()
                print(f"✅ Payment processed for {order_id}")
        
        conn.close()
        return {'status': 'ok'}, 200
    
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return {'error': str(e)}, 500

# ============ MAIN ============

if __name__ == "__main__":
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
