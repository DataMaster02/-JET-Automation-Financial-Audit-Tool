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

### 1. Uygulamayı açma

1. `CALISTIR.bat` dosyasına çift tıklayın.
2. Uygulama masaüstü penceresi olarak açılmazsa tarayıcıdan `http://127.0.0.1:5757` adresine gidin.
3. İlk açılışta Python kütüphaneleri kurulabilir; bu işlem sadece ilk çalıştırmada zaman alır.

### 2. Veri yükleme

1. Ana ekranda Excel, CSV, TXT, TSV, JSON veya XML dosyasını sürükleyip bırakın ya da dosya seçiciden yükleyin.
2. Excel dosyasında birden fazla sheet varsa uygulama sheet seçim ekranı gösterir.
3. Yüklenecek sheet veya sheetleri seçin.
4. Büyük dosyalarda yükleme parça parça yapılır; ilerleme durumu ekranda takip edilebilir.
5. Yükleme tamamlandığında dataset bellek içine alınır ve ön izleme alanında ilk satırlar gösterilir.

Desteklenen temel formatlar:

- `.xlsx`, `.xlsm`, `.xls`
- `.csv`, `.txt`, `.tsv`
- `.json`, `.xml`

Notlar:

- Excel sheetleri ayrı dataset olarak yüklenebilir.
- Dataset adı oluşturulurken kaynak dosyanın uzantısı gereksiz şekilde tekrar eklenmez.
- Büyük yevmiye dosyalarında RAM kullanımını azaltmak için veri okuma işlemleri parça bazlı yapılır.

### 3. Ön izleme ve dataset seçimi

Veri yüklendikten sonra:

- Aktif dataset seçilebilir.
- Satır ve kolon sayısı görülebilir.
- İlk kayıtlar tablo halinde incelenebilir.
- Kolon adları, veri tipleri ve temel içerik kontrol edilebilir.
- Birden fazla dataset yüklendiyse DataLab ve export işlemleri için hangi datasetin kullanılacağı seçilebilir.

### 4. Kullanıcı Taraması

Kullanıcı bazlı işlem yoğunluğu ve tutar analizi için kullanılır.

1. Kullanıcı kimliği kolonunu seçin.
2. Borç, alacak veya tutar kolonlarını seçin.
3. İsteğe bağlı olarak tarih, fiş veya açıklama kolonlarını belirleyin.
4. Analizi çalıştırın.

Oluşan çıktı:

- `Kullanici_Taramasi.xlsx`
- Kullanıcı bazında kayıt sayısı, toplam tutar ve işlem dağılımı içerir.

### 5. Kelime Taraması

Açıklama, belge açıklaması, fiş açıklaması veya benzeri metin kolonlarında anahtar kelime aramak için kullanılır.

1. Taranacak metin kolonlarını seçin.
2. Anahtar kelimeleri girin.
3. Eşleşme modunu seçin:
   - Tam kelime
   - İçerir
   - Büyük/küçük harf duyarsız arama
4. Analizi çalıştırın.

Oluşan çıktı:

- `Kelime_Taramasi.xlsx`
- Eşleşen satırlar, eşleşen kelime bilgisi ve özet sheet içerir.

### 6. Unusual Analizi

Hesap ve karşı hesap ilişkilerini denetlemek için kullanılır.

1. Hesap kodu kolonunu seçin.
2. Fiş no, yevmiye no veya belge no gibi gruplama kolonunu seçin.
3. Ana hesap kodlarını girin. Örnek: `600, 601, 602`
4. Beklenen veya hariç tutulacak karşı hesap kodlarını girin. Örnek: `120, 391, 102`
5. Analizi çalıştırın.

Oluşan çıktı:

- `Unusual_Analiz.xlsx`
- Aykırı fiş detayları, fiş bazında özet ve kriter bilgileri içerir.

### 7. DataLab

DataLab, yüklenen dataset üzerinde kod yazmadan veya kontrollü Python kodu ile çalışma yapmak için kullanılır.

DataLab içinde yapılabilecek başlıca işlemler:

- Hazır filtrelerle yeni dataset oluşturma
- Manuel filtre oluşturma
- Gelişmiş AND / OR koşulları kurma
- Formüllü kolon ekleme
- Sabit kolon ekleme
- Kolon silme veya yeniden adlandırma
- Boş değer doldurma
- Tip dönüştürme
- Metin ve tarih işlemleri
- GroupBy / özet tablo oluşturma
- Join / Merge işlemleri
- Append / Union ile datasetleri birleştirme
- Profiling paneli ile kolon bazında veri kalitesi kontrolü

### 8. Hızlı Filtreler

Hızlı filtreler, finansal denetim senaryolarında sık kullanılan kontrolleri tek ekranda sunar.

Örnek filtreler:

- Boş kayıtlar
- Boş olmayan kayıtlar
- Tekrar eden kayıtlar
- Benzersiz kayıtlar
- Negatif tutarlar
- Sıfır tutarlı kayıtlar
- Hafta sonu kayıtları
- Mesai dışı kayıtlar
- Açıklaması kısa kayıtlar
- Belirli tarih aralığı
- Belirli hesap kodları
- Hesap kodu başlangıcı
- Tutar aralığı
- En yüksek N kayıt
- En düşük N kayıt
- Rastgele N kayıt
- Yuvarlak tutarlar
- Dönem sonu kayıtları
- Borç / alacak dengesizliği
- Ters kayıt kontrolü
- Generic kullanıcı işlemleri

Kullanım akışı:

1. DataLab bölümünde `Filtre / Yeni Dataset` ekranını açın.
2. Üstteki `Filtre Ara` alanından filtre adını arayın.
3. İlgili filtre kartına tıklayın.
4. Kartın altında açılan `Filtre Parametreleri` alanını doldurun.
5. Kolon veya kolonları seçin.
6. Çoklu kolon seçildiğinde kolon çalışma yöntemini belirleyin:
   - Herhangi biri koşulu sağlasın
   - Tüm kolonlar koşulu sağlasın
   - Kolon kombinasyonu olarak değerlendir
   - Her kolon için ayrı kontrol yap
   - Kolonları birleştirerek kontrol et
   - İlk dolu kolonu kullan
7. `Sonuç Sayısını Göster` ile filtreyi kaydetmeden önce kaç kayıt geleceğini kontrol edin.
8. `İlk 20 Kaydı Göster` ile sonucu ön izleyin.
9. `Filtreyi Uygula` ile sonucu kaydedin.

Sonuç kaydı seçenekleri:

- Yeni dataset olarak kaydet
- Mevcut dataset üzerinde uygula
- Sonuçları başka datasete ekle
- Sadece eşleşen kayıtları kaydet
- Sadece eşleşmeyen kayıtları kaydet

### 9. Python Notebook

Notebook alanında seçili dataset `df` değişkeni olarak kullanılabilir.

Örnek:

```python
df.head()
```

Notebook çıktısı DataFrame veya Series ise:

- Yeni dataset olarak kaydedilebilir.
- XLSX veya CSV olarak dışa aktarılabilir.
- Sonraki DataLab işlemlerinde tekrar kullanılabilir.

Bu alan özellikle veri analistleri ve IT denetçileri için esnek analiz yapmak amacıyla eklenmiştir.

### 10. Dışa Aktarma

DataLab veya genel export ekranından datasetler dışa aktarılabilir.

Desteklenen seçenekler:

- XLSX olarak dışa aktar
- CSV olarak dışa aktar
- TXT olarak dışa aktar
- TSV olarak dışa aktar
- JSON olarak dışa aktar
- Parquet olarak dışa aktar

XLSX export gerçek Excel workbook formatında oluşturulur. Sadece dosya uzantısı değiştirilmez.

Export sırasında:

- Türkçe karakterler korunur.
- Sayısal kolonlar sayı olarak kalır.
- Tarih kolonları Excel tarafından okunabilir formatta yazılır.
- Null ve NaN değerler hata oluşturmadan boş hücreye dönüştürülür.
- Dosya adı boş bırakılırsa dataset adına göre otomatik oluşturulur.
- `.xlsx.xlsx` gibi çift uzantı oluşması engellenir.

Append & Export ekranında ayrıca `Export Hedefi` alanı kullanılabilir:

1. `Dosya Yeri Seç` ile hedef panelini açın.
2. Sadece klasör adı girerseniz dosya seçilen klasöre kaydedilir.
3. Tam dosya yolu girerseniz çıktı doğrudan o dosyaya yazılır. Örnek: `C:\Raporlar\muavin_export.json`
4. Masaüstü uygulaması PyWebView ile çalışıyorsa `Dosya Seç / Kaydet` butonu Windows kaydetme penceresini açar.
5. Yazılan dosya uzantısı seçilen formatı otomatik belirleyebilir. Örnek: `.json` yazılırsa JSON export yapılır.

---

## Çıktı Dosyaları

Çıktılar iki şekilde alınabilir:

1. Analiz çıktıları masaüstünde seçilen çıktı klasörüne yazılır.
2. DataLab ve export ekranlarında sonuçlar doğrudan tarayıcı indirmesi olarak alınabilir.

### Standart analiz çıktıları

| Dosya | Ne zaman oluşur? | İçerik |
|-------|------------------|--------|
| `Kullanici_Taramasi.xlsx` | Kullanıcı Taraması çalıştırıldığında | Kullanıcı bazında kayıt sayısı, tutar toplamları, işlem yoğunluğu ve özet tablolar |
| `Kelime_Taramasi.xlsx` | Kelime Taraması çalıştırıldığında | Anahtar kelime eşleşen satırlar, eşleşen kelime bilgisi ve özet sheet |
| `Unusual_Analiz.xlsx` | Unusual Analizi çalıştırıldığında | Aykırı fiş detayları, fiş bazlı hesap/karşı hesap kontrolleri ve özet |
| `JET_Template_Doldurulmus.xlsm` | Template yolu girilip analiz sonucu template'e aktarılırsa | Seçilen JET template dosyasının analiz verisiyle doldurulmuş kopyası |

### DataLab çıktıları

| Çıktı tipi | Açıklama |
|------------|----------|
| Yeni dataset | Filtre, formül, groupBy, join veya notebook sonucu uygulama belleğine yeni dataset olarak eklenir |
| Mevcut dataset güncelleme | Filtre sonucu aktif dataset üzerine uygulanır |
| Append sonucu | Birden fazla dataset alt alta birleştirilerek yeni dataset oluşturulur |
| Join / Merge sonucu | İki dataset ortak kolonlara göre birleştirilir |
| GroupBy / Özet sonucu | Seçilen kolonlara göre gruplanmış özet dataset oluşturulur |
| Notebook sonucu | Python hücresinden dönen DataFrame veya Series yeni dataset olarak kaydedilir |

### Export çıktıları

| Format | Dosya örneği | Açıklama |
|--------|--------------|----------|
| XLSX | `Dataset_Adi.xlsx` | Gerçek Excel workbook formatında oluşturulur; Excel ile doğrudan açılabilir |
| CSV | `Dataset_Adi.csv` | UTF-8 BOM destekli CSV çıktısıdır; Türkçe karakterler korunur |
| TXT | `Dataset_Adi.txt` | Tab karakteriyle ayrılmış metin çıktısıdır |
| TSV | `Dataset_Adi.tsv` | Tab-separated value formatında metin çıktısıdır |
| JSON | `Dataset_Adi.json` | Kayıtları JSON liste formatında dışa aktarır; Türkçe karakterler korunur |
| Parquet | `Dataset_Adi.parquet` | Büyük veri işleme için kolon bazlı Parquet çıktısıdır |
| Filtrelenmiş XLSX | `Dataset_Adi_Filtre.xlsx` | Hızlı filtre veya manuel filtre sonucunda eşleşen kayıtları içerir |
| Filtrelenmiş CSV | `Dataset_Adi_Filtre.csv` | Filtre sonucunu CSV formatında indirir |

### Dosya adı kuralları

- Dosya adı boş bırakılırsa uygulama dataset adına göre otomatik ad üretir.
- Kaynak dosya adı `Muavin.xlsx` ise filtre çıktısı varsayılan olarak `Muavin_Filtre.xlsx` olur.
- Dataset adına kaynak dosyanın `.xlsx`, `.csv` gibi uzantısı tekrar eklenmez.
- Aynı uzantı iki kez eklenmez. Örnek: `Muavin.xlsx.xlsx` oluşturulmaz.
- Windows dosya adında kullanılamayan karakterler temizlenir.

### Büyük dosya notları

- Çok büyük XLSX çıktılarında veri parçalara ayrılarak yazılabilir.
- CSV çıktıları daha hızlı oluşur ve büyük veri aktarımı için tercih edilebilir.
- Excel satır sınırı nedeniyle çok büyük datasetlerde CSV daha uygun olabilir.
- Export edilen dosyada boş, NaN veya sonsuz değerler Excel hatası oluşturmadan güvenli şekilde yazılır.

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
