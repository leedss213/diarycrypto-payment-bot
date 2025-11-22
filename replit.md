# DiaryCrypto Payment Bot

Discord bot dengan integrasi pembayaran Midtrans untuk membership The Warrior.

## Overview
Bot ini mengelola sistem membership berbasis Discord dengan pembayaran melalui Midtrans Production Mode. Bot memiliki fitur pembelian dengan form data lengkap, perpanjangan membership, notifikasi expiry, auto role removal, statistik untuk admin, dan export data.

## Recent Changes (2024-11-22)
- ✅ **MAJOR UPDATE**: Implementasi lengkap fitur data collection
  - Form input: Nama, Alamat, Email, Nomor HP sebelum payment
  - Discord username tersimpan otomatis untuk pencarian mudah
- ✅ **Email Integration Ready**: Placeholder untuk welcome email & expiry warning
- ✅ **Auto Role Removal**: Sistem otomatis mencopot role saat membership expired
- ✅ **Fixed Admin Commands**: /statistik, /export_monthly, /creat_discount untuk role Origin
- ✅ **Dynamic Webhook URL**: URL webhook otomatis berdasarkan REPL environment
- ✅ **Production Mode**: Midtrans dikonfigurasi untuk production (bukan sandbox)

## Project Architecture

### Tech Stack
- **Language**: Python 3.11
- **Framework**: Discord.py (with Modal UI), Flask
- **Payment**: Midtrans (Production mode) ✅
- **Database**: SQLite

### File Structure
```
.
├── main.py                      # Main bot file dengan semua fitur
├── requirements.txt             # Python dependencies
├── warrior_subscriptions.db     # SQLite database (auto-created)
└── replit.md                   # Project documentation
```

### Database Schema (UPDATED)

#### subscriptions
Menyimpan data membership lengkap:
- discord_id (PRIMARY KEY)
- discord_username - Username Discord untuk pencarian
- nama - Nama lengkap member
- alamat - Alamat lengkap
- email - Email member (untuk notifikasi)
- nomor_hp - Nomor HP/WhatsApp
- package_type
- start_date, end_date
- status (active/expired)
- order_id
- notified_3days - Flag notifikasi 3 hari
- email_sent - Flag email terkirim

#### pending_orders
Menyimpan order yang menunggu payment:
- order_id (PRIMARY KEY)
- discord_id, discord_username
- nama, alamat, email, nomor_hp
- package_type, duration_days
- is_renewal
- created_at

#### discount_codes
Kode diskon untuk promosi

#### transactions
History transaksi pembayaran

### Commands

#### Public Commands
- `/buy` - Beli atau perpanjang membership The Warrior
  - **Flow baru**:
    1. Pilih package (1 month / 3 months)
    2. Pilih action (Beli Baru / Perpanjang Member)
    3. **Form popup muncul** untuk isi: Nama, Alamat, Email, Nomor HP
    4. Submit → Payment link dikirim ke DM

#### Admin Commands (Role: Origin)
- `/statistik` - Statistik langganan dan revenue ✅
- `/export_monthly` - Export CSV transaksi bulanan ✅
- `/creat_discount` - Buat kode diskon baru ✅

### Environment Variables Required
- `DISCORD_TOKEN` - Discord bot token
- `MIDTRANS_SERVER_KEY` - Midtrans server key (PRODUCTION) ✅
- `MIDTRANS_CLIENT_KEY` - Midtrans client key (PRODUCTION) ✅
- `REPL_SLUG` - Auto-detected dari environment
- `REPL_OWNER` - Auto-detected dari environment

### Webhook Configuration
Webhook URL **dinamis** berdasarkan Repl environment:
- Format: `https://{REPL_SLUG}.{REPL_OWNER}.repl.co/webhook/midtrans`
- Method: POST
- Health check: `/health` (GET)
- **PENTING**: Update URL ini di dashboard Midtrans!

### Features

#### 1. Data Collection System ✅
- Modal form untuk collect data lengkap sebelum payment
- Fields: Nama Lengkap, Alamat, Email, Nomor HP
- Data tersimpan di database untuk tracking
- Discord username otomatis tercatat

#### 2. Payment Integration ✅
- Midtrans payment gateway (PRODUCTION mode)
- Auto role assignment setelah payment berhasil
- Transaction history tracking

#### 3. Renewal System ✅
- Member bisa perpanjang membership
- Durasi ditambahkan dari end date yang lama
- Jika sudah expired, mulai dari tanggal perpanjangan

#### 4. Expiry Notification System ✅
- **Discord DM**: 3 hari sebelum expired
- **Email placeholder**: Siap untuk integrasi email service
- Notifikasi mencantumkan nama member dan tanggal expiry

#### 5. Auto Role Removal ✅
- Background task check setiap jam
- Otomatis copot role saat membership expired
- Kirim notifikasi saat role dicopot
- Update status subscription menjadi "expired"

#### 6. Admin Dashboard ✅
- **Statistik**: Active/total subs, revenue, breakdown per package
- **Export Monthly**: Download CSV transaksi per bulan
- **Discount Codes**: Buat kode diskon (database ready)
- **Security**: Hanya role "Origin" yang bisa akses

### Automated Tasks
1. **Expiry Check** (Daily): Cek membership yang 3 hari lagi expired, kirim notifikasi
2. **Auto Role Removal** (Hourly): Cek membership expired, copot role otomatis

### Next Steps untuk Email Integration
Untuk aktifkan pengiriman email otomatis:
1. Setup SendGrid atau Gmail connector di Replit
2. Update fungsi `send_welcome_email()` dan `send_expiry_warning_email()`
3. Email akan terkirim otomatis saat:
   - Payment berhasil (welcome email)
   - 3 hari sebelum expired (warning email)

### User Preferences
- Bahasa: Indonesian
- Bot harus reliable dan responsive
- Admin commands hanya untuk role "Origin"
- Semua data member tersimpan lengkap (nama, alamat, email, HP)
- Auto role management (assign & remove)
