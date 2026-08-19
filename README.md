# JET Otomasyon Aracı — Masaüstü Sürüm

Journal Entry Testing için offline Windows masaüstü uygulaması.  
Flask backend + PyWebView ile çalışır. İnternet bağlantısı gerekmez.

---

## Dosya Yapısı

```
jet_desktop/
├── src/
│   ├── app.py          ← Ana uygulama (Flask backend)
│   └── index.html      ← Arayüz (frontend)
├── CALISTIR.bat        ← Çalıştır (geliştirici modu)
├── EXE_OLUSTUR.bat     ← Tek .exe dosyası oluştur
├── JET.spec            ← PyInstaller yapılandırması
├── requirements.txt    ← Python kütüphaneleri
└── README.md
```

---

## Kurulum ve Çalıştırma

### Yöntem 1 — Direkt Çalıştır (Python gerekli)

1. **Python 3.9+** yükleyin: https://www.python.org/downloads/
   - Kurulum sırasında **"Add Python to PATH"** seçeneğini işaretleyin
2. `CALISTIR.bat` dosyasına çift tıklayın
3. İlk çalıştırmada kütüphaneler otomatik kurulur (~1 dakika)
4. Uygulama penceresi açılır

### Yöntem 2 — Tek EXE (Python gerekmez, paylaşım için)

1. Önce Yöntem 1'i bir kez çalıştırın (sanal ortam kurulsun)
2. `EXE_OLUSTUR.bat` dosyasına çift tıklayın
3. `dist/JET_Otomasyon.exe` oluşturulur
4. Bu EXE'yi istediğiniz bilgisayara taşıyabilirsiniz

---

## Kullanım

### Adım 1 — Veri Yükle
- Excel dosyasını sürükleyin veya "Seç" ile açın
- Sheet seçin (birden fazla sheet varsa)
- Çıktı klasörü adını belirleyin (masaüstünde oluşturulur)
- JET Template yolunu girin (opsiyonel)

### Adım 2 — Kullanıcı Taraması
- Kullanıcı kimliği kolonunu seçin
- Borç / Alacak kolonlarını seçin (opsiyonel)
- "Analizi Çalıştır" → `Kullanici_Taramasi.xlsx` oluşur

### Adım 3 — Kelime Taraması
- Taranacak kolonları seçin (çoklu)
- Eşleşme modunu seçin (Tam Kelime / İçerik)
- Anahtar kelimeleri girin
- "Tara" → `Kelime_Taramasi.xlsx` oluşur

### Adım 4 — Unusual Analizi
- Hesap kodu kolonunu seçin
- Gruplama kolonunu seçin (Fiş No / Yevmiye No)
- Ana hesap kodlarını girin (ör: 600, 601)
- Karşı hesap kodlarını girin (ör: 120, 391)
- "Unusual Çalıştır" → `Unusual_Analiz.xlsx` oluşur

---

## Çıktı Dosyaları

Masaüstündeki klasörde oluşturulur:

| Dosya | İçerik |
|-------|---------|
| `Kullanici_Taramasi.xlsx` | Kullanıcı bazında kayıt ve tutar özeti |
| `Kelime_Taramasi.xlsx` | Eşleşen satırlar + özet sheet |
| `Unusual_Analiz.xlsx` | Unusual fişler + fiş bazında özet |
| `JET_Template_Doldurulmus.xlsm` | Template doldurulmuş kopyası |

---

## Teknik Gereksinimler

- **İşletim Sistemi:** Windows 10/11 (64-bit)
- **Python:** 3.9 veya üstü (Yöntem 1 için)
- **RAM:** En az 4 GB (büyük dosyalar için 8 GB önerilir)
- **Disk:** 500 MB boş alan (kütüphaneler için)

---

## Sorun Giderme

**"Python bulunamadı" hatası**  
→ Python'u yeniden kurun ve "Add to PATH" seçeneğini işaretleyin

**Pencere açılmıyor**  
→ `CALISTIR.bat` çalıştırın, sonra tarayıcıda `http://127.0.0.1:5757` adresine gidin

**Template yapıştırılamadı**  
→ Template dosya yolunun doğru girildiğini ve dosyanın açık olmadığını kontrol edin

**Büyük dosyalarda yavaşlık**  
→ Normal, 500K+ satır dosyalar için birkaç dakika sürebilir
