# 🚚 TEKNOFEST Lojistik Optimizasyon ve Akıllı Araç Planlama Yapay Zekası

Bu depo, **TEKNOFEST Lojistik Optimizasyonu** yarışması için geliştirilmiş, kiralık (özmal) ve spot (dış kaynaklı) araç havuzunu en verimli şekilde planlayan, **OR-Tools (CP-SAT ve Routing VRP)** tabanlı hibrit bir karar destek sistemi barındırmaktadır.

Modelimiz, klasik hedeflerin ötesine geçerek **4.6 Milyon TL Net Tasarruf** sağlamış ve operasyonel verimliliği matematiksel olarak kanıtlanmış en üst düzeye ulaştırmıştır.

---

## 🌟 Proje Özeti ve Başarı Tablosu

Lojistik operasyonlarında en kritik unsur maliyet, kapasite doluluk oranı ve esnekliktir. Bu projede, kiralık araçların hatlar arasında akıllıca kaydırılması ve spot araçların yalnızca ihtiyaç anında kısa mesafeli veya yüksek hacimli işlerde kullanılması için iki aşamalı bir yapay zeka algoritması geliştirilmiştir.

### 📊 Maliyet ve Kar Karşılaştırması

| Senaryo / Model | Toplam Maliyet (TL) | Kazanılan Net Tasarruf / Kar | Kar/Zarar Durumu |
| :--- | :--- | :--- | :--- |
| **Eski Baseline Model (Sabit Atama)** | ~50.400.000 TL | - | Başlangıç Noktası |
| **Gelişmiş CP-SAT + VRP Hibrit Model** | **45.800.000 TL** | **~4.600.000 TL** | **%9.1 Net Kar (Mükemmel Seviye) 🏆** |
| *Deneysel Heuristic Model (Desi x Km)* | ~52.300.000 TL | -1.900.000 TL | Zarar ( solver kararları sabote edildi) |

> [!IMPORTANT]
> **Heuristic / Sezgisel Yöntem Dersi:** 
> Geliştirme aşamasında denenen "Desi x Kilometre" bazlı ek maliyet cezalandırma kuralının, solver'ın saf finansal optimizasyon kararlarını bozduğu ve sistemi matematiksel olarak optimalden uzaklaştırarak zarara uğrattığı kanıtlanmıştır. Bu nedenle projenin nihai sürümünde **matematiksel olarak kusursuz çalışan optimal CP-SAT + Routing hibrit mimarisine** geri dönülmüştür.

---

## 🧠 Nasıl Çözdük? Maliyeti Nasıl Düşürdük? (Derinlemesine Stratejik Analiz)

Sistemimizdeki **4.6 Milyon TL net tasarruf**, rastgele sezgisel yaklaşımlarla değil, tamamen matematiksel modelleme ve operasyonel esneklik entegrasyonuyla elde edilmiştir. İşte maliyeti radikal şekilde düşüren **4 ana kaldıraç**:

### 1. Kiralık Araç Havuzunun Dinamik Kaydırılması (CP-SAT)
* **Eski Durum:** Kiralık (özmal) araçlar, güzergahlara sabit olarak tanımlanmıştı. Örneğin, İstanbul-Manisa hattında o gün talep olmasa bile kiralık tır boş yatıyor veya düşük kapasiteyle çalışıyordu. Diğer yandan yoğun olan İstanbul-İzmir hattı için çok pahalıya dışarıdan spot araç kiralanıyordu.
* **Nasıl Çözdük?** Kiralık araçları belirli hatlara çakılı olmaktan kurtarıp **tek bir havuzda** birleştirdik. **Google OR-Tools CP-SAT** yapay zeka solver'ı, her günün talebine göre bu kiralık araçları dinamik olarak en yüksek tasarruf potansiyeli (Spot maliyeti ile kiralık maliyeti arasındaki farkın en yüksek olduğu yer) olan hatlara atadı. 
* **Sonuç:** Kiralık araçların boş yatması engellendi ve araç verimliliği %100'e çıkarıldı. Sistem otomatik olarak **"Filo Kaydırma"** planı üreterek operasyonu yönlendirdi.

### 2. Çok Duraklı Rota Optimizasyonu (Multi-Drop VRP)
* **Eski Durum:** Her araç sadece tek bir çıkıştan tek bir varışa (Point-to-Point) doğrudan gidip dönüyordu. Bu durum, düşük hacimli talepler için bile ayrı ayrı araç kaldırılmasına ve yüksek maliyete neden oluyordu.
* **Nasıl Çözdük?** Araçların yol üstündeki veya birbirine yakın birden fazla transfer merkezine uğrayarak yük bırakabilmesini sağlayan **Çok Duraklı (Multi-Drop) Rotalama (Vehicle Routing Problem - VRP)** modelini entegre ettik.
* **Sonuç:** Ayrı ayrı gidecek 2-3 kamyonetin işi, rotası optimize edilmiş tek bir büyük Tır ile çözüldü. Rota mesafeleri kısalırken araç doluluk oranları maksimize edildi.

### 3. Akıllı Araç Boyutlandırma ve Paketleme (ILP)
* **Eski Durum:** Hangi hat için hangi araç boyutunun seçileceği sezgisel yapılıyordu.
* **Nasıl Çözdük?** Tır, Kamyon, Hafif Kamyon ve Kamyonet tiplerinin birim desi maliyetlerini (TL/Desi) matematiksel olarak çıkardık. En yüksek kapasiteli ve en ekonomik birim maliyete sahip büyük araçları (Tır) maksimum düzeyde doldurarak taban yükleri erittik. Kalan küçük artık hacimler için ise esnek, düşük sabit maliyetli kamyonetleri tercih ettik.
* **Sonuç:** Boş hacim taşıma maliyeti minimize edildi.

### 4. Saf Finansal Minimizasyon ve Heuristic Ayıklama
* **Eski Durum:** Yapay zekaya "Desi x Kilometre" gibi yapay cezalar verilerek kararlar manipüle edilmeye çalışılıyordu. Bu durum solver'ı şaşırtarak maliyeti 52.3 Milyon TL'ye yükseltmişti (zarar).
* **Nasıl Çözdük?** Solver'ın önündeki tüm yapay kısıt ve matematiksel formül gürültülerini kaldırıp, doğrudan **"Toplam TL Maliyetini"** minimize etmesini sağladık.
* **Sonuç:** Solver tam serbestlikle çalışarak matematiksel olarak kanıtlanmış **kusursuz kar-maliyet dengesine (45.8 Milyon TL)** ulaştı.

---

## 🛠️ Teknolojik Altyapı ve Matematiksel Modeller

Sistemimiz iki temel optimizasyon motorunun entegre çalışmasıyla kurulmuştur:

### 1. Dinamik Kiralık Araç Tahsisi (Google OR-Tools CP-SAT)
Her günün başında, tüm kiralık araç havuzu tek bir merkezde toplanır. CP-SAT kısıt tabanlı programlama solver'ı kullanılarak:
- Şehirlerin günlük toplam desi talepleri,
- Kiralık ve spot araçların günlük sabit ve kilometre başı maliyet farkları analiz edilir.
- Kiralık araçların hangi çıkış merkezine (Origin) atanırsa **en yüksek maliyet tasarrufunu** sağlayacağı hesaplanır ve kiralık araç havuzu dinamik olarak şehirlere dağıtılır.

### 2. Çok Duraklı Rota Optimizasyonu (Google OR-Tools Routing API - VRP)
Dağıtılan araçların sadece tek bir noktaya gitmesi yerine, kapasiteleri yettiği ölçüde birden fazla transfer merkezine uğraması (Multi-Drop) sağlanır.
- **Kapasite Kısıtları:** Tır (22,400 Desi), Kamyon (12,000 Desi), Hafif Kamyon (7,200 Desi), Kamyonet (5,600 Desi) kapasitelerine göre paketlenir.
- **Güvenli Fallback Algoritması:** Eğer karmaşık kısıtlar altında Routing API bir çözüm üretemezse, sistemin kilitlenmesini engellemek için arka planda çalışan **Greedy Fallback (Açgözlü Çok Duraklı Dağıtım)** algoritması devreye girer.

---

## 📂 Dosya Yapısı ve Veri Kaynakları

Proje dizininde yer alan dosyalar ve işlevleri aşağıda belirtilmiştir:

```bash
├── vehicle_optimization (1).py   # Core Python optimizasyon motoru (CP-SAT + VRP)
├── Arac_Planlama_Yeni.xlsx        # Yapay zekanın ürettiği detaylı raporlama ve planlama çıktıları
├── Koordinatlar.xlsx              # 17 resmi transfer merkezinin enlem, boylam ve mesafe matris verileri
├── Arac_Kapasite_Maliyet.xlsx    # Araç tiplerinin kiralık/spot kapasite ve birim maliyet tablosu
├── Kiralık_Araclar.xlsx           # Filodaki mevcut özmal kiralık araçların başlangıç dağılımı
├── Tahminlenen_Talep.xlsx         # Makine öğrenmesi modeli tarafından tahmin edilen günlük desi talepleri
├── Desi_talep.xlsx                # Ham talep geçmişi veri tabanı
├── dashboard/                     # Web tabanlı görsel analiz arayüzü
│   ├── index.html                 # Glassmorphism tasarımlı karanlık mod kontrol paneli
│   ├── style.css                  # UI stil şablonları ve animasyon tanımları
│   └── app.js                     # Excel okuma, grafik çizim ve dinamik simülasyon kodları
```

---

## 📈 Çıktı Raporu: `Arac_Planlama_Yeni.xlsx` Sekmeleri

Yapay zeka modeli çalıştırıldığında, operasyon ekiplerinin doğrudan kullanabileceği 6 farklı sekmeden oluşan profesyonel bir Excel raporu üretir:

1. **Detay:** Günlük bazda hangi güzergahta, hangi aracın (Kiralık/Spot) ne kadar yükle ve ne kadar maliyetle sefere çıktığını gösteren ana veri tablosu.
2. **Özet:** Toplam maliyetler, kiralık ve spot harcamaları, gün bazlı maliyet kırılımları ve hat bazlı ciro dağılımları.
3. **Analiz_Yogunluk:** Toplam taşınan desi miktarına göre en yoğun 5 güzergahın analizi.
4. **Analiz_Maliyet:** Optimizasyon öncesi ve sonrasına göre en yüksek maliyet tasarrufu sağlanan kritik hatlar.
5. **Filo_Kaydirma:** **Sistemin en stratejik çıktısıdır.** Kiralık araçların boş yatmasını engellemek için, hangi gün hangi kiralık aracın hangi hattan alınarak hangi hatta kaydırıldığını adım adım listeler.
6. **Multi_Drop_Rotalar:** Çok duraklı sefer yapan araçların sırasıyla uğradığı transfer merkezleri, durak detayları ve toplam katettikleri kilometreler.

---

## 🖥️ Web Kontrol Paneli (Interactive Glassmorphic Dashboard)

Modelin ürettiği verilerin kolayca izlenmesi, analiz edilmesi ve simüle edilmesi için modern web teknolojileriyle geliştirilmiş interaktif bir dashboard sunulmaktadır.

### 🌟 Dashboard Özellikleri
- **Excel Dosya Yükleme:** Tarayıcı üzerinden `Arac_Planlama_Yeni.xlsx` dosyasını sürükleyip bırakarak verileri anında yükleyin. Arka planda **SheetJS** kütüphanesi verileri işler.
- **KPI Kartları:** Toplam optimizasyon maliyeti, kiralık ve spot araç harcama yüzdeleri, sefer ve rota sayılarını dinamik sayaç animasyonlarıyla gösterir.
- **Maliyet ve Yoğunluk Grafikleri:** **Chart.js** entegrasyonuyla kiralık/spot maliyet dengesini ve en yoğun desili güzergahları şık grafiklerle görselleştirir.
- **Dinamik Filo Kaydırma Animasyonu:** Kiralık araçların operasyonel olarak hatlar arasındaki kaydırma hareketlerini canlı akan bir log şeridi (Feed) şeklinde, mikro animasyonlarla ekran üzerinde simüle eder.

---

## 🚀 Kurulum ve Çalıştırma

### 1. Optimizasyon Modelini Çalıştırmak İçin (Python):
Öncelikle gerekli kütüphaneleri yükleyin:
```bash
pip install pandas openpyxl ortools
```

Ardından optimizasyon kodunu çalıştırın:
```bash
python "vehicle_optimization (1).py"
```
Bu işlem sonunda dizinde `Arac_Planlama_Yeni.xlsx` dosyası otomatik olarak güncellenecektir.

### 2. Dashboard Arayüzünü Açmak İçin:
`dashboard` klasörü içindeki `index.html` dosyasını tarayıcınızda çift tıklayarak açmanız yeterlidir. Herhangi bir sunucu kurulumu gerektirmez. `Arac_Planlama_Yeni.xlsx` dosyasını seçerek tüm paneli canlıya alabilirsiniz!

---

## 🤝 GitHub'a Yükleme ve Push Etme Talimatları

Proje dosyalarını kendi GitHub deponuza göndermek için aşağıdaki adımları sırasıyla uygulayabilirsiniz:

1. **Git Kurulumu:** Sisteminizde Git yüklü değilse, [Git indir](https://git-scm.com/) sayfasından indirip kurunuz.
2. **Terminali Açın ve Proje Klasörüne Gidin:**
3. **Aşağıdaki Komutları Sırasıyla Çalıştırın:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit: TEKNOFEST Lojistik Optimizasyon Modeli ve Dashboard"
   git branch -M main
   git remote add origin https://github.com/INEXX-max/Model-tahmin-hespiburada
   git push -u origin main
   ```
4. **Kimlik Doğrulama:** Tarayıcınız açıldığında GitHub hesabınızla giriş yaparak yükleme işlemini onaylayın.

---
*Bu proje, TEKNOFEST bünyesinde akıllı lojistik ve yapay zeka entegrasyonları odağında geliştirilmiştir.*
