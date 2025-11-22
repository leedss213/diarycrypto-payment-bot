# DiaryCrypto Payment Bot

Discord bot dengan integrasi pembayaran Midtrans untuk membership The Warrior dengan sistem referral komisi.

## Overview
Bot ini mengelola sistem membership berbasis Discord dengan pembayaran melalui Midtrans Sandbox Mode (untuk testing). Bot memiliki fitur pembelian dengan form data, perpanjangan membership, notifikasi expiry, auto role removal, statistik untuk admin, dan **sistem referral dengan komisi 30% untuk 6 Analysts + 1 Analyst's Lead**.

## Recent Changes (2025-11-22)
- ✅ **Referral System**: 6 Analysts (Bay, Dialena, Kamado, Ryzu, Zen, Rey) + 1 Lead (Bell)
- ✅ **Commission Tracking**: Otomatis track 30% komisi dari harga SETELAH diskon
- ✅ **Personal Commission Commands**: /komisi_saya_[nama] untuk setiap analyst
- ✅ **Admin Stats Command**: /komisi_stats untuk lihat semua komisi
- ✅ **Referral Link Command**: /refer_link untuk info kode referral
- ✅ **Referral Code Field**: Form input untuk kode referral saat /buy
- ✅ **Form Data Collection**: Nama, Email, Nomor HP (ALAMAT DIHAPUS)
- ✅ **Auto Role Assignment**: Otomatis dapat role setelah payment berhasil
- ✅ **Auto Role Removal**: Otomatis copot role saat membership expired (interval 5 menit)
- ✅ **Fixed**: InteractionResponded error di /buy command
- ✅ **Fixed**: Database schema referred_username column
- ✅ **NEW**: Randomized Referral Codes (B4Y_kTx, D1L3n4X, K4m4d0Z, Ry2uW3k, Z3nQp0x, R3yT8m2, B3LLrFT)

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

### Commands (14 Total)

#### Public Commands (Semua Member)
1. `/buy` - Beli atau perpanjang membership The Warrior
   - **Flow**:
     1. Pilih package (1 month / 3 months)
     2. Pilih action (Beli Baru / Perpanjang Member)
     3. **Form popup**: Nama, Email, Nomor HP, Kode Referral (opsional)
     4. Submit → Payment link dikirim ke DM
   - **Kode Referral** (Randomized): B4Y_kTx, D1L3n4X, K4m4d0Z, Ry2uW3k, Z3nQp0x, R3yT8m2, B3LLrFT

2. `/refer_link` - Tampilkan semua kode referral dan cara kerja

#### Analyst Commission Commands (7)
3. `/komisi_saya_bay` - Cek komisi Bay
4. `/komisi_saya_dialena` - Cek komisi Dialena
5. `/komisi_saya_kamado` - Cek komisi Kamado
6. `/komisi_saya_ryzu` - Cek komisi Ryzu
7. `/komisi_saya_zen` - Cek komisi Zen
8. `/komisi_saya_rey` - Cek komisi Rey
9. `/komisi_saya_bell` - Cek komisi Bell (Analyst's Lead)

**Output setiap command:**
- Total Referral (jumlah orang yang refer)
- Total Komisi (Rp total)
- Komisi Terbayar (Rp yang sudah dibayar)
- 10 Transaksi Terbaru (username, harga, komisi, diskon%)

#### Admin Commands (Role: Origin Only)
10. `/statistik` - Statistik langganan dan revenue
11. `/export_monthly` - Export CSV transaksi bulanan
12. `/creat_discount` - Buat kode diskon baru
13. `/manage_package` - Kelola paket membership (create/delete/list)
14. `/komisi_stats` - Statistik komisi SEMUA analyst (admin dashboard)
    - **Reset Button**: Hanya role "Com Manager" yang bisa reset komisi (tutup buku bulanan)
    - Ketika diklik, semua data komisi & referral dihapus dan balik ke nol

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

#### 7. Referral System ✅ (NEW)
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

### Next Steps (Optional Future Features)
- [ ] Email notifikasi komisi ke analyst
- [ ] Payout system untuk tarik komisi
- [ ] Leaderboard analyst berdasarkan komisi
- [ ] Bonus tier untuk analyst top performer
- [ ] Marketing dashboard untuk analyst
- [ ] Advanced referral link dengan tracking ID
