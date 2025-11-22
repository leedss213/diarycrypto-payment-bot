# 🔧 FIX: Bot Role Hierarchy untuk Auto-Role Assignment

## ❌ Masalah Saat Ini
Bot tidak bisa assign role karena error:
```
403 Forbidden (error code: 50013): Missing Permissions
```

## ✅ Solusi: Atur Role Hierarchy

Bot hanya bisa assign role yang **LEBIH RENDAH** darinya di hierarchy. 

**Langkah-langkah:**

1. **Buka Discord Server**
2. **Server Settings → Roles**
3. **Lihat urutan role** - sekarang mungkin seperti ini:
   ```
   ❌ The Warrior Role  (TINGGI - Bot tidak bisa atur)
   ❌ Bot Role          (RENDAH - perlu dinaikkan)
   ```

4. **Drag Bot Role ke atas** sehingga menjadi:
   ```
   ✅ Bot Role          (PALING ATAS - sekarang bisa atur role lain)
   ✅ The Warrior Role  (DIBAWAH Bot Role)
   ```

5. **Selesai!** Bot sekarang bisa assign role otomatis

---

## 📋 Checklist Lengkap:

- [ ] Bot role lebih tinggi dari "The Warrior" role
- [ ] Bot punya permission "Manage Roles" (sudah aktif)
- [ ] Bot sudah di-restart setelah setup role hierarchy
- [ ] Coba `/buy` dan bayar lagi

Setelah itu role akan otomatis diberikan saat payment berhasil! 🎉
