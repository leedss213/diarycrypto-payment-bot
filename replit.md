# DiaryCrypto Payment Bot

Discord bot dengan integrasi pembayaran Midtrans untuk membership The Warrior.

## Overview
Bot ini mengelola sistem membership berbasis Discord dengan pembayaran melalui Midtrans. Bot memiliki fitur pembelian, perpanjangan membership, statistik untuk admin, export data, dan notifikasi expiry.

## Recent Changes (2024-11-22)
- ✅ Fixed `/buy` command - sekarang bisa digunakan oleh semua member
- ✅ Added admin commands (role Origin):
  - `/statistik` - Melihat statistik langganan
  - `/export_monthly` - Export data transaksi bulanan
  - `/creat_discount` - Membuat kode diskon
- ✅ Added renewal feature - Member bisa perpanjang membership lewat `/buy`
- ✅ Added expiry notification - Discord DM 3 hari sebelum membership expired
- ✅ Improved database schema untuk tracking renewal dan notifications

## Project Architecture

### Tech Stack
- **Language**: Python 3.11
- **Framework**: Discord.py, Flask
- **Payment**: Midtrans (Production mode)
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
- **subscriptions**: Membership data dengan email dan notification tracking
- **pending_orders**: Order yang menunggu pembayaran
- **discount_codes**: Kode diskon untuk promosi
- **transactions**: History transaksi

### Commands

#### Public Commands
- `/buy` - Beli atau perpanjang membership The Warrior
  - Parameter: package (1 month / 3 months)
  - Parameter: action (Beli Baru / Perpanjang Member)

#### Admin Commands (Role: Origin)
- `/statistik` - Statistik langganan dan revenue
- `/export_monthly` - Export CSV transaksi bulanan
- `/creat_discount` - Buat kode diskon baru

### Environment Variables Required
- `DISCORD_TOKEN` - Discord bot token
- `MIDTRANS_SERVER_KEY` - Midtrans server key (production)
- `MIDTRANS_CLIENT_KEY` - Midtrans client key (production)

### Webhook Configuration
Webhook URL untuk Midtrans:
- Endpoint: `/webhook/midtrans`
- Method: POST
- Health check: `/health` (GET)

### Features
1. **Payment Integration**: Midtrans payment gateway
2. **Auto Role Assignment**: Otomatis assign role setelah payment berhasil
3. **Renewal System**: Member bisa perpanjang, durasi ditambahkan dari end date
4. **Expiry Notification**: Notifikasi Discord DM 3 hari sebelum expired
5. **Admin Dashboard**: Statistik dan export data untuk admin
6. **Discount System**: Admin bisa buat kode diskon (database ready, belum terintegrasi ke payment)

### User Preferences
- Bahasa: Indonesian
- Bot harus reliable dan responsive
- Admin commands hanya untuk role "Origin"
