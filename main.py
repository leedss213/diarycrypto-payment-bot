import os
import discord
from discord import app_commands
import midtransclient
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import threading
import asyncio
import csv
from io import StringIO, BytesIO
from typing import Optional

TOKEN = os.environ.get('DISCORD_TOKEN', '')
GUILD_ID = 1370638839407972423
ORIGIN_ROLE_NAME = "Origin"

PACKAGES = {
    "warrior_1month": {
        "name": "The Warrior 1 Month",
        "price": 299000,
        "duration_days": 30,
        "role_id": 1371002371899133992
    },
    "warrior_3month": {
        "name": "The Warrior 3 Months",
        "price": 649000,
        "duration_days": 90,
        "role_id": 1371002371899133992
    }
}

MIDTRANS_SERVER_KEY = os.environ.get('MIDTRANS_SERVER_KEY', '')
MIDTRANS_CLIENT_KEY = os.environ.get('MIDTRANS_CLIENT_KEY', '')

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


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'bot': 'running'}), 200


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)
snap = midtransclient.Snap(is_production=True,
                           server_key=MIDTRANS_SERVER_KEY,
                           client_key=MIDTRANS_CLIENT_KEY)


def init_database():
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                 (discord_id TEXT PRIMARY KEY,
                  package_type TEXT,
                  start_date TIMESTAMP,
                  end_date TIMESTAMP,
                  status TEXT DEFAULT 'active',
                  order_id TEXT,
                  email TEXT,
                  notified_3days INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pending_orders
                 (order_id TEXT PRIMARY KEY,
                  discord_id TEXT,
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
    conn.commit()
    conn.close()


def save_pending_order(order_id, discord_id, package_type, duration_days, is_renewal=False):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute(
        '''INSERT OR REPLACE INTO pending_orders 
                 (order_id, discord_id, package_type, duration_days, is_renewal)
                 VALUES (?, ?, ?, ?, ?)''',
        (order_id, discord_id, package_type, duration_days, 1 if is_renewal else 0))
    conn.commit()
    conn.close()


def get_pending_order(order_id):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    c.execute(
        'SELECT discord_id, package_type, duration_days, is_renewal FROM pending_orders WHERE order_id = ?',
        (order_id, ))
    result = c.fetchone()
    conn.close()
    return result


def save_subscription(discord_id, package_type, duration_days, order_id, email=None, is_renewal=False):
    conn = sqlite3.connect('warrior_subscriptions.db')
    c = conn.cursor()
    
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
                 (discord_id, package_type, start_date, end_date, status, order_id, email, notified_3days)
                 VALUES (?, ?, ?, ?, 'active', ?, ?, 0)''',
        (discord_id, package_type, start_date, end_date, order_id, email))

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


async def activate_subscription(order_id):
    try:
        pending = get_pending_order(order_id)
        if not pending:
            print(f"⚠️ No pending order found for {order_id}")
            return

        discord_id, package_type, duration_days, is_renewal = pending
        save_subscription(discord_id, package_type, duration_days, order_id, is_renewal=bool(is_renewal))
        
        save_transaction(discord_id, order_id, package_type, PACKAGES[package_type]['price'], 'settlement')

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print(f"❌ Guild {GUILD_ID} not found")
            return

        member = guild.get_member(int(discord_id))
        if not member:
            print(f"❌ Member {discord_id} not found in guild")
            return

        role_id = PACKAGES[package_type]["role_id"]
        role = guild.get_role(role_id)

        if role:
            await member.add_roles(role)
            print(f"✅ Assigned role {role.name} to {member.name}")

        renewal_text = "diperpanjang" if is_renewal else "aktif"
        embed = discord.Embed(
            title="✅ PEMBAYARAN BERHASIL!",
            description=
            f"Selamat! Akses **{PACKAGES[package_type]['name']}** kamu sudah {renewal_text}.",
            color=0x00ff00)
        embed.add_field(name="📅 Durasi",
                        value=f"{duration_days} hari",
                        inline=True)
        embed.add_field(name="🎯 Status", value="Active", inline=True)
        embed.set_footer(text="Terima kasih telah berlangganan!")

        try:
            await member.send(embed=embed)
        except:
            print(f"⚠️ Could not DM user {discord_id}")

        print(f"✅ Subscription activated for user {discord_id}")

    except Exception as e:
        print(f"❌ Error activating subscription: {e}")


def is_admin(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    origin_role = discord.utils.get(interaction.guild.roles, name=ORIGIN_ROLE_NAME)
    if origin_role and hasattr(interaction.user, 'roles'):
        return origin_role in interaction.user.roles
    return False


@tree.command(name="buy", description="Beli atau perpanjang akses The Warrior")
@app_commands.describe(package="Pilih paket langganan", action="Beli baru atau perpanjang membership")
@app_commands.choices(
    package=[
        app_commands.Choice(name="1 Month - Rp 299,000", value="warrior_1month"),
        app_commands.Choice(name="3 Months - Rp 649,000", value="warrior_3month")
    ],
    action=[
        app_commands.Choice(name="Beli Baru", value="new"),
        app_commands.Choice(name="Perpanjang Member", value="renewal")
    ]
)
async def buy_command(interaction: discord.Interaction,
                      package: app_commands.Choice[str],
                      action: Optional[app_commands.Choice[str]] = None):
    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        is_renewal = action and action.value == "renewal"
        
        if is_renewal:
            existing_sub = get_user_subscription(str(interaction.user.id))
            if not existing_sub:
                await interaction.followup.send(
                    "❌ Kamu belum memiliki membership aktif. Silakan pilih 'Beli Baru'.",
                    ephemeral=True)
                return
        
        selected_package = PACKAGES[package.value]
        timestamp = int(datetime.now().timestamp())
        order_id = f"W{interaction.user.id}{timestamp}"[-36:]

        transaction = snap.create_transaction({
            "transaction_details": {
                "order_id": order_id,
                "gross_amount": selected_package["price"]
            },
            "item_details": [{
                "id": package.value,
                "price": selected_package["price"],
                "quantity": 1,
                "name": selected_package["name"] + (" - Perpanjangan" if is_renewal else "")
            }],
            "customer_details": {
                "first_name": interaction.user.display_name[:30],
                "email": f"{interaction.user.id}@warrior.diarycrypto"
            }
        })

        payment_url = transaction['redirect_url']
        save_pending_order(order_id, str(interaction.user.id), package.value,
                           selected_package["duration_days"], is_renewal)

        action_text = "perpanjang" if is_renewal else "upgrade"
        embed = discord.Embed(
            title=f"🎯 {'PERPANJANG' if is_renewal else 'UPGRADE TO'} THE WARRIOR",
            description=
            f"**Paket:** {selected_package['name']}\n**Harga:** Rp {selected_package['price']:,}\n**Durasi:** {selected_package['duration_days']} hari",
            color=0x00ff00)
        embed.add_field(name="🔗 Payment Link",
                        value=f"[Klik di sini untuk bayar]({payment_url})",
                        inline=False)
        embed.add_field(
            name="💳 Metode Pembayaran",
            value="• Transfer Bank\n• E-Wallet\n• Kartu Kredit/Debit",
            inline=False)
        
        if is_renewal:
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
        print(f"Payment error: {e}")
        await interaction.followup.send(
            "❌ Gagal membuat link pembayaran. Silakan coba lagi.",
            ephemeral=True)


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
            color=0x0099ff)
        
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
            color=0x00ff00)
        
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
                color=0x00ff00)
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


async def check_expiring_subscriptions():
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            conn = sqlite3.connect('warrior_subscriptions.db')
            c = conn.cursor()
            
            three_days_from_now = datetime.now() + timedelta(days=3)
            three_days_threshold = three_days_from_now.strftime('%Y-%m-%d')
            
            c.execute('''SELECT discord_id, email, end_date, package_type 
                        FROM subscriptions 
                        WHERE status = "active" 
                        AND date(end_date) = date(?)
                        AND notified_3days = 0''',
                     (three_days_threshold,))
            
            expiring_subs = c.fetchall()
            
            guild = bot.get_guild(GUILD_ID)
            
            for discord_id, email, end_date, package_type in expiring_subs:
                try:
                    member = guild.get_member(int(discord_id)) if guild else None
                    
                    if member:
                        embed = discord.Embed(
                            title="⚠️ MEMBERSHIP AKAN BERAKHIR",
                            description=f"Membership **{PACKAGES.get(package_type, {}).get('name', 'The Warrior')}** kamu akan berakhir dalam 3 hari!",
                            color=0xffa500)
                        embed.add_field(
                            name="📅 Tanggal Berakhir",
                            value=datetime.fromisoformat(end_date).strftime('%Y-%m-%d %H:%M'),
                            inline=True)
                        embed.add_field(
                            name="🔄 Perpanjang Sekarang",
                            value="Gunakan `/buy` dan pilih 'Perpanjang Member'",
                            inline=False)
                        embed.set_footer(text="Jangan sampai akses kamu terputus!")
                        
                        await member.send(embed=embed)
                        print(f"✅ Sent expiry warning to user {discord_id}")
                    
                    if email:
                        print(f"📧 Email notification needed for {email} (ID: {discord_id})")
                    
                    c.execute('UPDATE subscriptions SET notified_3days = 1 WHERE discord_id = ?',
                             (discord_id,))
                    
                except Exception as e:
                    print(f"❌ Error sending notification to {discord_id}: {e}")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"❌ Error checking expiring subscriptions: {e}")
        
        await asyncio.sleep(86400)


@bot.event
async def on_ready():
    print(f'✅ {bot.user} has connected to Discord!')
    try:
        await tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Commands synced to guild {GUILD_ID}")
    except Exception as e:
        print(f"❌ Sync error: {e}")
    
    bot.loop.create_task(check_expiring_subscriptions())
    print("✅ Expiry checker started!")
    print("🎉 Bot is ready!")


if __name__ == "__main__":

    def run_flask():
        app.run(host='0.0.0.0', port=5000, debug=False)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    init_database()
    print("🚀 Starting Discord bot...")
    print(
        "🌐 Webhook URL: https://ec5bec16-e71d-49ee-9d62-36af3690cb49-00-2pvvtr1za5a96.pike.replit.dev/webhook/midtrans"
    )
    bot.run(TOKEN)
