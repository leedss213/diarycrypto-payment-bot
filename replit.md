# DiaryCrypto Payment Bot

Discord bot dengan integrasi pembayaran Midtrans untuk membership The Warrior dengan sistem referral komisi.

## Overview
Bot ini mengelola sistem membership berbasis Discord dengan pembayaran melalui Midtrans Sandbox Mode (untuk testing). Bot memiliki fitur pembelian dengan form data, perpanjangan membership, notifikasi expiry, auto role removal, statistik untuk admin, sistem referral dengan komisi 30% untuk 6 Analysts + 1 Analyst's Lead, dan **auto-posting crypto news** ke channel.

## Recent Changes (2025-11-24 - Session 4)
- ✅ **15-minute Package**: Paket baru durasi 15 menit dengan harga Rp 200,000
- ✅ **Crypto News Feature**: Manual-post crypto news articles dengan link ke channel `#💳｜payment`
  - Data: 5 berita crypto dengan informasi lengkap
  - Include: Title, Description, Link, Source, Image, Published date
  - Format: Embed card dengan orange color (#f7931a)
  - Semua konten dalam **BAHASA INDONESIA** 🇮🇩
  - Manual trigger: `/post_crypto_news_now` (Com-Manager only)
  - URLs: Reliable links ke CoinMarketCap & CoinGecko (tidak ada 404 error)
  - Content: Bitcoin, Ethereum, Solana, DeFi, Crypto News
  - Status: Testing (siap untuk auto-posting 24 jam nanti)

## Recent Changes (2025-11-23 - Session 3)
- ✅ **Avatar in Discord DMs**: Member avatars ditampilkan di semua DM messages
- ✅ **Admin Kick Notification**: Admin dapat email notifikasi saat role dicopotan
- ✅ **Removed Discord Card Embeds**: Card embeds Discord DM dihapus, hanya email cards

## Project Architecture

### Tech Stack
- **Language**: Python 3.11
- **Framework**: Discord.py (with Modal UI), Flask
- **Payment**: Midtrans (SANDBOX mode untuk testing) 🧪
- **Database**: SQLite
- **News API**: CoinTelegraph JSON Feed
- **Total Commands**: 19 (2 public + 10 admin/analyst + 7 general)

### File Structure
```
.
├── main.py                      # Main bot file (3300+ lines)
├── requirements.txt             # Python dependencies
├── warrior_subscriptions.db     # SQLite database (auto-created)
└── replit.md                   # Project documentation
```

### Packages Available
- `warrior_15min` - The Warrior 15 Minutes (Rp 200,000)
- `warrior_1hour` - The Warrior 1 Hour (Rp 50,000) [Test]
- `warrior_1month` - The Warrior 1 Month (Rp 299,000)
- `warrior_3month` - The Warrior 3 Months (Rp 649,000)

### Commands (19 Total)

#### Public Commands (Semua Member)
1. `/buy` - Beli atau perpanjang membership The Warrior
2. `/redeem_trial` - Gunakan kode trial member

#### Crypto News Commands
19. `/post_crypto_news_now` - **[Com-Manager Only]** Manual post crypto news (testing)

#### Admin Commands (Com-Manager only - HIDDEN)
3-18. [Previous admin commands as documented]

### Features

#### Latest: Crypto News System ✅
- **Auto-Post**: Setiap 24 jam post top crypto news ke channel
- **Format**: Title + Description + Link + Source + Image
- **Source**: CoinTelegraph JSON Feed (real articles)
- **Channel**: `#📰｜berita-crypto`
- **Manual Trigger**: `/post_crypto_news_now` for testing
- **Language**: Indonesian metadata

#### Previous Features
- Payment integration (Midtrans Sandbox)
- Auto role assignment & removal
- Email system (invoices, notifications, cards)
- Referral system (7 analysts, 30% commission)
- Trial member system
- Bot uptime monitoring
- Commission tracking
- Export & statistics

### User Preferences
- Bahasa: Indonesian 🇮🇩
- Bot untuk testing (sandbox mode)
- Auto-post berita crypto dengan link & sumber
- Channel: `#📰｜berita-crypto` (dengan emoji prefix)
- Format: Article title + Link + Source (seperti iHODL bot)

### Next Steps
- [ ] Test `/post_crypto_news_now` command
- [ ] Verify crypto news posting format
- [ ] Enable auto-posting (24h interval)
- [ ] Publish bot ke production (24/7 always online)
