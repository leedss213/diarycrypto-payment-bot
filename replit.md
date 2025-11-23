# DiaryCrypto Payment Bot

Discord bot dengan integrasi pembayaran Midtrans untuk membership The Warrior dengan sistem referral komisi.

## Overview
Bot ini mengelola sistem membership berbasis Discord dengan pembayaran melalui Midtrans Sandbox Mode (untuk testing). Bot memiliki fitur pembelian dengan form data, perpanjangan membership, notifikasi expiry, auto role removal, statistik untuk admin, dan **sistem referral dengan komisi 30% untuk 6 Analysts + 1 Analyst's Lead**.

## Recent Changes (2025-11-23 - Session 2)
- ✅ **Email on Role Removal**: Member dapat email saat The Warrior role dicopot (auto/manual kick)
  - Konten: Membership expired notification dengan detail paket & tanggal
- ✅ **Bot Status Command**: `/bot_status` (Com-Manager only)
  - Track uptime, last start time, availability %, system status
  - Warna border ORANGE
  - Hidden dari public member
- ✅ **Welcome & Goodbye Cards** (NEW - functions created, pending integration):
  - `send_welcome_card()` - Card dengan member avatar saat jadi member
  - `send_trial_welcome_card()` - Card dengan member avatar saat redeem trial
  - `send_goodbye_card()` - Card dengan member avatar saat membership expired
  - Semua include: Nama, Foto/Avatar member, Package info, Tanggal expired
- ✅ **Permission Updates**:
  - `/bot_status` → Com-Manager only (hidden dari public)
  - `/refer_link` → Analyst & Admin only (hidden dari public)

## Recent Changes (2025-11-23 - Session 1)
- ✅ **Gmail Invoice System**: Otomatis kirim invoice ke member setelah payment sukses
- ✅ **Admin Notification**: Admin otomatis dapat email notifikasi member baru
- ✅ **Referral System**: 6 Analysts + 1 Lead dengan komisi 30%
- ✅ **Commission Tracking & Personal Commands**: /komisi_saya_[nama]
- ✅ **Auto Role Assignment & Removal**: Otomatis assign/remove dengan interval check
- ✅ **Form Data Collection**: Nama, Email, Nomor HP, Referral Code
- ✅ **Randomized Referral Codes**: B4Y_kTx, D1L3n4X, K4m4d0Z, Ry2uW3k, Z3nQp0x, R3yT8m2, B3LLrFT

## Project Architecture

### Tech Stack
- **Language**: Python 3.11
- **Framework**: Discord.py (with Modal UI), Flask
- **Payment**: Midtrans (SANDBOX mode untuk testing) 🧪
- **Database**: SQLite
- **Total Commands**: 14 (5 public + 8 admin/analyst + 1 general)

### File Structure
```
.
├── main.py                      # Main bot file (1678 lines)
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
- referrer_name - Nama analyst yang refer

#### pending_orders
- order_id (PRIMARY KEY)
- discord_id, discord_username
- nama, email, nomor_hp
- package_type, duration_days
- is_renewal
- referrer_name - Kode referral yang digunakan
- created_at

#### discount_codes
- code, discount_percentage
- valid_until, usage_limit, used_count
- created_at

#### transactions
- id, discord_id, order_id
- package_type, amount, status
- transaction_date

#### packages
- package_id (PRIMARY KEY)
- name, price, duration_days, role_name
- created_at

#### referrals (NEW)
- id (PRIMARY KEY)
- referrer_name - Nama analyst (Bay, Dialena, Kamado, Ryzu, Zen, Rey, Bell)
- referred_discord_id, referred_username
- order_id
- created_at

#### commissions (NEW)
- id (PRIMARY KEY)
- referrer_name - Nama analyst
- referred_discord_id, referred_username
- order_id, package_type
- original_amount, discount_percentage
- final_amount - Harga setelah diskon
- commission_amount - 30% dari final_amount
- paid_status (pending/paid)
- transaction_date

### Commands (16 Total)

#### Public Commands (Semua Member)
1. `/buy` - Beli atau perpanjang membership The Warrior
   - **Flow**: Pilih package → Pilih action → Form (Nama, Email, HP, Referral) → Payment link ke DM
   - **Kode Referral**: B4Y_kTx, D1L3n4X, K4m4d0Z, Ry2uW3k, Z3nQp0x, R3yT8m2, B3LLrFT

2. `/redeem_trial` - Gunakan kode trial member

#### Analyst Commands (8 - HIDDEN dari public)
3. `/refer_link` - **[Analyst & Admin Only]** Tampilkan kode referral (HIDDEN)
4. `/komisi_saya_bay` - Cek komisi Bay
5. `/komisi_saya_dialena` - Cek komisi Dialena
6. `/komisi_saya_kamado` - Cek komisi Kamado
7. `/komisi_saya_ryzu` - Cek komisi Ryzu
8. `/komisi_saya_zen` - Cek komisi Zen
9. `/komisi_saya_rey` - Cek komisi Rey
10. `/komisi_saya_bell` - Cek komisi Bell (Analyst's Lead)

#### Admin Commands (Com-Manager only - HIDDEN)
11. `/statistik` - Statistik langganan dan revenue
12. `/export_monthly` - Export Excel transaksi bulanan (7 kolom)
13. `/creat_discount` - Buat kode diskon baru
14. `/manage_package` - Kelola paket membership
15. `/kick_member` - Manual kick member dari role
16. `/komisi_stats` - Statistik komisi SEMUA analyst + Reset button
17. `/bot_status` - **[Com-Manager Only]** Lihat uptime bot dan availability (HIDDEN)

### Referral System Flow

```
1. Member baru input kode referral saat /buy
   - Gunakan kode randomized: B4Y_kTx, D1L3n4X, K4m4d0Z, Ry2uW3k, Z3nQp0x, R3yT8m2, B3LLrFT
   ↓
2. Payment dikirim ke Midtrans
   ↓
3. Payment sukses → Webhook triggered
   ↓
4. Komisi otomatis tercatat:
   - referrer_name = nama analyst
   - commission = 30% dari final_amount (SETELAH diskon)
   ↓
5. Analyst cek komisi dengan /komisi_saya_[nama]
```

**Contoh kalkulasi:**
```
Paket: 1 Month - Rp 299.000
Diskon: 20% (-Rp 59.800)
Final Amount: Rp 239.200
Komisi (30%): Rp 71.760 ← Analyst dapat bagian ini
```

**Kode Referral Mapping:**
```
Bay → B4Y_kTx
Dialena → D1L3n4X
Kamado → K4m4d0Z
Ryzu → Ry2uW3k
Zen → Z3nQp0x
Rey → R3yT8m2
Bell (Lead) → B3LLrFT
```

### Environment Variables Required
- `DISCORD_TOKEN` - Discord bot token
- `MIDTRANS_SERVER_KEY` - Midtrans server key (SANDBOX) 🧪
- `MIDTRANS_CLIENT_KEY` - Midtrans client key (SANDBOX) 🧪
- `GMAIL_SENDER` - Email pengirim invoice (diarycryptopayment@gmail.com)
- `GMAIL_PASSWORD` - Google App Password (16 char dengan spasi)
- `ADMIN_EMAIL` - Email admin notifikasi (diarycryptoid@gmail.com)
- `REPL_SLUG` - Auto-detected
- `REPL_OWNER` - Auto-detected

### Webhook Configuration
**SANDBOX MODE WEBHOOK URL:**
```
https://731965a2-9e6d-459e-bf1c-a6a9c8f7ce8e-00-3odeyiucwl0ar.pike.replit.dev/webhook/midtrans
```

⚠️ **PENTING**: 
- Update URL ini di dashboard Midtrans **SANDBOX** (bukan production)
- Endpoint: `/webhook/midtrans` (POST)
- Health check: `/health` (GET)

### Features

#### 1. Data Collection System ✅
- Modal form: Nama Lengkap, Email, Nomor HP, Kode Referral (opsional)
- **TIDAK ADA ALAMAT** (sudah dihapus)
- Discord username otomatis tercatat

#### 2. Payment Integration ✅
- Midtrans payment gateway (SANDBOX mode) 🧪
- Auto role assignment setelah payment berhasil
- Transaction history tracking
- Support promo code & referral code

#### 3. Renewal System ✅
- Member bisa perpanjang membership
- Durasi ditambahkan dari end date lama
- Jika expired, mulai dari tanggal perpanjangan

#### 4. Expiry Notification System ✅
- Discord DM 3 hari sebelum expired
- Notifikasi mencantumkan nama member dan tanggal expiry
- **Email integration: DITUNDA** (user belum setup)

#### 5. Auto Role Removal ✅
- Background task check setiap 1 menit
- Otomatis copot role saat membership expired
- Kirim notifikasi saat role dicopot
- Update status subscription menjadi "expired"

#### 6. Admin Dashboard ✅
- **Statistik**: Active/total subs, revenue, breakdown
- **Export Monthly**: Download CSV transaksi per bulan
- **Discount Codes**: Buat kode diskon
- **Package Management**: Create/delete/list paket
- **Commission Stats**: Lihat komisi semua analyst
- **Security**: Hanya role "Origin" yang bisa akses

#### 7. Gmail Invoice System ✅ (NEW - 2025-11-23)
- **Member Invoice**: Otomatis dikirim ke email member setelah payment settlement
  - Konten: Order ID, Paket, Harga, Durasi, Tanggal expired
  - Format: HTML email dengan styling profesional
  - Sender: `diarycryptopayment@gmail.com`
- **Admin Notification**: Email notifikasi ke admin setiap ada member baru beli
  - Info: Member name, email, order ID, paket, harga
  - Recipient: `diarycryptoid@gmail.com`
- **SMTP**: Gmail App Password authentication (secure)

#### 8. Referral System ✅
- **6 Analysts**: Bay, Dialena, Kamado, Ryzu, Zen, Rey
- **1 Analyst's Lead**: Bell
- **Komisi**: 30% dari harga SETELAH diskon
- **Tracking**: Otomatis tercatat di database
- **Personal Dashboard**: Setiap analyst bisa cek komisi mereka
- **Admin Oversight**: Admin bisa lihat semua komisi di `/komisi_stats`

### Automated Tasks
1. **Expiry Check** (Daily): Cek membership 3 hari lagi expired, kirim notifikasi
2. **Auto Role Removal** (Every 1 minute): Cek membership expired, copot role otomatis
3. **Stale Order Cleanup** (Every 10 minutes): Hapus pending orders yang >15 menit tanpa payment

### Testing Mode (Sandbox)
Bot saat ini menggunakan **Midtrans Sandbox** untuk testing:
- Transaksi tidak real
- Gunakan test credit cards dari Midtrans
- Data payment tidak akan charge uang asli
- Cocok untuk test auto role assignment & removal
- Referral system bisa di-test dengan input kode referral saat /buy

### Production Checklist (Untuk Nanti)
Sebelum pindah ke production mode:
- [ ] Ganti `is_production=False` menjadi `True` di main.py
- [ ] Update MIDTRANS_SERVER_KEY dan CLIENT_KEY ke production keys
- [ ] Update webhook URL di Midtrans dashboard production
- [ ] Setup email service (Gmail/SendGrid) untuk notifikasi email
- [ ] Test semua fitur sekali lagi
- [ ] Setup payment payout untuk komisi analyst

### User Preferences
- Bahasa: Indonesian 🇮🇩
- Bot untuk testing (sandbox mode)
- Admin commands hanya untuk role "Origin"
- Data member: Nama, Email, Nomor HP (tanpa alamat)
- Auto role management (assign & remove)
- Referral system untuk 7 analyst dengan komisi 30%
- Komisi dihitung dari harga SETELAH diskon

### Known Issues & Solutions
- **Issue**: Bot terasa lemot setelah tutup laptop
  - **Cause**: Error di /buy command interaction
  - **Fix**: ✅ Fixed - removed double response

- **Issue**: ❌ Error: no such column: referred_username
  - **Cause**: Database schema missing column
  - **Fix**: ✅ Fixed - added referred_username to commissions table

- **Issue**: ❌ Gmail invoice tidak terkirim
  - **Cause**: Password bukan Google App Password (harus 16 karakter)
  - **Fix**: ✅ Fixed - gunakan Google App Password dari myaccount.google.com/security

- **Issue**: LSP errors di KickMemberView
  - **Cause**: Guild nullable type tidak di-handle
  - **Fix**: ✅ Fixed - added null checks sebelum akses guild.roles dan guild.members

### Pending Integration (Session 2 - Cards)
- ⏳ **Welcome Card Integration**: Integrate `send_welcome_card()` ke `activate_subscription()` saat member baru
- ⏳ **Trial Card Integration**: Integrate `send_trial_welcome_card()` ke `redeem_trial_command()`
- ⏳ **Goodbye Card Integration**: Integrate `send_goodbye_card()` ke auto role removal & manual kick

### Next Steps (Optional Future Features)
- [ ] Publish bot ke production (24/7 always online)
- [ ] Email notifikasi komisi ke analyst
- [ ] Payout system untuk tarik komisi
- [ ] Leaderboard analyst berdasarkan komisi
- [ ] Bonus tier untuk analyst top performer
- [ ] Marketing dashboard untuk analyst
