# DiaryCrypto Payment Bot

Discord bot dengan integrasi pembayaran Midtrans untuk membership The Warrior.

## Overview
Bot ini mengelola sistem membership berbasis Discord dengan pembayaran melalui Midtrans Sandbox Mode (untuk testing). Bot memiliki fitur pembelian dengan form data, perpanjangan membership, notifikasi expiry, auto role removal, statistik untuk admin, dan export data.

## Recent Changes (2024-11-22)
- ✅ **Form Data Collection**: Nama, Email, Nomor HP (ALAMAT DIHAPUS)
- ✅ **Sandbox Mode**: Midtrans menggunakan mode testing untuk uji coba
- ✅ **Public /buy Command**: Semua member bisa menggunakan /buy
- ✅ **Admin Commands**: /statistik, /export_monthly, /creat_discount untuk role Origin
- ✅ **Auto Role Assignment**: Otomatis dapat role setelah payment berhasil
- ✅ **Auto Role Removal**: Otomatis copot role saat membership expired
- ✅ **Dynamic Webhook URL**: Auto-detect dari environment

## Project Architecture

### Tech Stack
- **Language**: Python 3.11
- **Framework**: Discord.py (with Modal UI), Flask
- **Payment**: Midtrans (SANDBOX mode untuk testing) 🧪
- **Database**: SQLite

### File Structure
```
.
├── main.py                      # Main bot file
├── requirements.txt             # Python dependencies
├── warrior_subscriptions.db     # SQLite database (auto-created)
└── replit.md                   # Project documentation
```

### Database Schema

#### subscriptions
- discord_id (PRIMARY KEY)
- discord_username - Username Discord untuk pencarian
- nama - Nama lengkap member
- email - Email member
- nomor_hp - Nomor HP/WhatsApp
- package_type
- start_date, end_date
- status (active/expired)
- order_id
- notified_3days - Flag notifikasi 3 hari
- email_sent - Flag email terkirim

#### pending_orders
- order_id (PRIMARY KEY)
- discord_id, discord_username
- nama, email, nomor_hp
- package_type, duration_days
- is_renewal
- created_at

#### discount_codes
- code, discount_percentage
- valid_until, usage_limit, used_count

#### transactions
- id, discord_id, order_id
- package_type, amount, status
- transaction_date

### Commands

#### Public Commands (Semua Member)
- `/buy` - Beli atau perpanjang membership The Warrior
  - **Flow**:
    1. Pilih package (1 month / 3 months)
    2. Pilih action (Beli Baru / Perpanjang Member)
    3. **Form popup**: Nama, Email, Nomor HP (tanpa alamat)
    4. Submit → Payment link dikirim ke DM

#### Admin Commands (Role: Origin Only)
- `/statistik` - Statistik langganan dan revenue
- `/export_monthly` - Export CSV transaksi bulanan
- `/creat_discount` - Buat kode diskon baru

### Environment Variables Required
- `DISCORD_TOKEN` - Discord bot token
- `MIDTRANS_SERVER_KEY` - Midtrans server key (SANDBOX) 🧪
- `MIDTRANS_CLIENT_KEY` - Midtrans client key (SANDBOX) 🧪
- `REPL_SLUG` - Auto-detected
- `REPL_OWNER` - Auto-detected

### Webhook Configuration
**SANDBOX MODE WEBHOOK URL:**
```
https://workspace.kibou98.repl.co/webhook/midtrans
```

⚠️ **PENTING**: 
- Update URL ini di dashboard Midtrans **SANDBOX** (bukan production)
- Endpoint: `/webhook/midtrans` (POST)
- Health check: `/health` (GET)

### Features

#### 1. Data Collection System ✅
- Modal form: Nama Lengkap, Email, Nomor HP
- **TIDAK ADA ALAMAT** (sudah dihapus)
- Discord username otomatis tercatat

#### 2. Payment Integration ✅
- Midtrans payment gateway (SANDBOX mode) 🧪
- Auto role assignment setelah payment berhasil
- Transaction history tracking

#### 3. Renewal System ✅
- Member bisa perpanjang membership
- Durasi ditambahkan dari end date lama
- Jika expired, mulai dari tanggal perpanjangan

#### 4. Expiry Notification System ✅
- Discord DM 3 hari sebelum expired
- Notifikasi mencantumkan nama member dan tanggal expiry
- **Email integration: DITUNDA** (user belum setup)

#### 5. Auto Role Removal ✅
- Background task check setiap jam
- Otomatis copot role saat membership expired
- Kirim notifikasi saat role dicopot
- Update status subscription menjadi "expired"

#### 6. Admin Dashboard ✅
- **Statistik**: Active/total subs, revenue, breakdown
- **Export Monthly**: Download CSV transaksi per bulan
- **Discount Codes**: Buat kode diskon
- **Security**: Hanya role "Origin" yang bisa akses

### Automated Tasks
1. **Expiry Check** (Daily): Cek membership 3 hari lagi expired, kirim notifikasi
2. **Auto Role Removal** (Hourly): Cek membership expired, copot role otomatis

### Testing Mode (Sandbox)
Bot saat ini menggunakan **Midtrans Sandbox** untuk testing:
- Transaksi tidak real
- Gunakan test credit cards dari Midtrans
- Data payment tidak akan charge uang asli
- Cocok untuk test auto role assignment & removal

### Production Checklist (Untuk Nanti)
Sebelum pindah ke production mode:
- [ ] Ganti `is_production=False` menjadi `True` di main.py line 83
- [ ] Update MIDTRANS_SERVER_KEY dan CLIENT_KEY ke production keys
- [ ] Update webhook URL di Midtrans dashboard production
- [ ] Setup email service (Gmail/SendGrid) untuk notifikasi email
- [ ] Test semua fitur sekali lagi

### User Preferences
- Bahasa: Indonesian
- Bot untuk testing (sandbox mode)
- Admin commands hanya untuk role "Origin"
- Data member: Nama, Email, Nomor HP (tanpa alamat)
- Auto role management (assign & remove)

### Notes
- Email integration akan disetup nanti setelah user siap
- Saat ini hanya Discord DM notifications yang aktif
- Semua fitur payment dan role management sudah berfungsi
