# VPN Benchmark Suite - Kapsamlı Proje Dokümantasyonu

Bu belge, "VPN Benchmark Suite" projesinin mimarisini, çalışma mantığını, test süreçlerini ve kullanılan teknolojilerin detaylarını açıklamak için hazırlanmıştır. Bir sunum veya slayt hazırlamak için gereken tüm detayları içerir.

---

## 1. Proje Özeti ve Amacı
VPN Benchmark Suite, farklı VPN protokollerinin (WireGuard, OpenVPN UDP/TCP, IPsec) gerçek dünya koşullarında nasıl performans gösterdiğini test etmek, karşılaştırmak ve puanlamak için tasarlanmış tam otomatik bir sistemdir.

Geleneksel hız testlerinin aksine, bu proje **"Ağ Emülasyonu"** (Network Emulation) yaparak, 3G bağlantısı, yüksek paket kayıplı uydu interneti veya yoğun DDoS altındaki ağlar gibi senaryoları simüle eder. Böylece hangi protokolün zorlu şartlarda daha dirençli olduğu tespit edilir.

---

## 2. Sistem Mimarisi ve Bileşenler

Sistem 3 temel parçadan oluşur:

### A. Frontend (Kullanıcı Arayüzü)
- **Teknolojiler:** React, Vite, TypeScript, Zustand (State Management), Tailwind CSS, Framer Motion, Recharts.
- **Görevleri:** 
  - Test konfigürasyonlarını ayarlamak (Protokol ve Ağ koşulu seçimi).
  - Canlı (real-time) olarak backend'den gelen metrikleri (WebSocket üzerinden) çizgi grafiklere yansıtmak.
  - Test aşamalarını bir log akışı olarak göstermek.
  - VM (Sanal Makine) bağlantı ayarlarını ve durumlarını yönetmek.

### B. Backend (Orkestratör)
- **Teknolojiler:** Python, FastAPI, Uvicorn, Asyncio, AsyncSSH.
- **Görevleri:**
  - Frontend'den gelen HTTP/WebSocket komutlarını dinlemek.
  - Sanal makinelere (VM'lere) **SSH üzerinden asenkron olarak** bağlanmak.
  - Ağ kısıtlamalarını uygulamak, VPN servislerini başlatmak, metrik toplama komutlarını çalıştırmak.
  - Toplanan raw (ham) verileri parse edip anlamlı metrikler ve skorlar üretmek.

### C. Altyapı (Sanal Makineler - VMs)
- **VM1 (VPN Server):** VPN sunucularının (Wireguard, OpenVPN, IPSec) çalıştığı ve metrik sunucularının (iperf3) bulunduğu ana sunucu.
- **VM2 & VM3 (VPN Clients):** VPN istemci yazılımlarının çalıştığı ve test trafiğini başlatan istemci makineler. Ağ emülasyonları (gecikme, paket kaybı) bu makinelerin ağ arayüzlerinde uygulanır.

*(Not: Makineler arası güvenli ve kolay iletişim için Tailscale overlay network kullanılmıştır. IP'ler 100.x.x.x bloklarındadır.)*

---

## 3. Desteklenen VPN Protokolleri ve Farkları

Proje, güncel ve yaygın VPN teknolojilerini kıyaslar:

1. **WireGuard (`wireguard`):** 
   - Yeni nesil, çok hafif, kernel seviyesinde çalışan VPN protokolü.
   - En yüksek hızı ve en düşük gecikmeyi sunar. Modern kriptografi (ChaCha20, Curve25519) kullanır.
2. **OpenVPN UDP (`openvpn_udp`):**
   - Endüstri standardı. UDP üzerinden çalıştığı için nispeten hızlıdır.
   - Güvenilir ağlarda iyi performans gösterir, yüksek firewall atlatma potansiyeline sahiptir.
3. **OpenVPN TCP (`openvpn_tcp`):**
   - TCP katmanının hata doğrulama mekanizmasını kullandığı için çok yüksek paket kayıplı ağlarda tünelin çökmesini engeller ama TCP Over TCP (Meltdown) problemi yüzünden ciddi hız düşüşü yaşatır.
   - DPI (Derin Paket İncelemesi) ve katı firewall'ları (örneğin HTTPS gibi görünerek) aşmak için idealdir.
4. **IPsec/IKEv2 (`ipsec`):**
   - Kurumsal alanda çok yaygındır. Kernel seviyesinde yüksek şifreleme sunar.

---

## 4. Test Yaşam Döngüsü (Test Lifecycle)

Kullanıcı "Start Test" dediğinde arka planda şu adımlar (Phase) sırasıyla işletilir (`backend/routers/tests.py`):

1. **`APPLYING_CONDITION` (Ağ Koşullarının Uygulanması):**
   - İstemci makinesinde `tc qdisc netem` komutu çalıştırılarak istenilen gecikme, paket kaybı veya bant genişliği sınırı ağ kartına işlenir.
2. **`STARTING_VPN_SERVER` (Sunucunun Başlatılması):**
   - VM1'de seçilen protokole ait servis başlatılır (Örn: `sudo systemctl start wg-quick@wg0`).
3. **`CONNECTING_CLIENT` (İstemcinin Bağlanması):**
   - İstemci makine (VM2), VPN'e bağlanır. (Örn: `sudo wg-quick up wg0`).
4. **`VERIFYING_TUNNEL` (Tünel Doğrulaması):**
   - VPN tünelinin kurulduğundan emin olmak için tünel IP'sine 3 adet ping atılır.
5. **`RUNNING_LATENCY` (Gecikme Ölçümü):**
   - Belirli bir süre/adet boyunca `ping` komutu çalıştırılarak anlık gecikmeler toplanır.
6. **`RUNNING_THROUGHPUT` (Bant Genişliği Ölçümü):**
   - `iperf3` kullanılarak veri indirme (download) ve yükleme (upload) hızları ölçülür.
7. **`COLLECTING_CPU` (CPU Kullanımının Ölçülmesi):**
   - Sunucuda `vmstat` çalıştırılarak VPN şifrelemesinin CPU'ya ne kadar yük bindirdiği analiz edilir.
8. **`CALCULATING_SCORE` (Skor Hesaplama):**
   - Elde edilen sonuçlar matematiksel modellere sokularak "Genel Skor" ve "DPI Direnç Skoru" hesaplanır.
9. **`CLEANING_UP` (Temizlik):**
   - VPN bağlantıları koparılır, servisler durdurulur ve ağ kısıtlamaları (`tc qdisc del`) kaldırılarak makine normal haline döndürülür.

---

## 5. Kullanılan Komutlar ve Araçlar (Ne Neden Kuruldu?)

### 🌐 Ağ Emülasyonu: `tc` (Traffic Control) ve `netem`
- **Neden Kuruldu?** Linux çekirdeğinin ağ trafiğini şekillendirme aracıdır. Farklı internet kalitelerini simüle etmek için şarttır.
- **Komut:** `sudo tc qdisc replace dev eth0 root netem delay 50ms 10ms distribution normal loss 5% rate 20mbit`
- **Ne Yapar?** Ağa 50ms gecikme (10ms dalgalanma ile), %5 paket kaybı ve 20 Mbit hız sınırı koyar.

### 📶 Hız Ölçümü: `iperf3`
- **Neden Kuruldu?** İki makine arasındaki maksimum elde edilebilir TCP/UDP bant genişliğini (Throughput) ölçmek için standart araçtır.
- **Komut:** `iperf3 -c 10.8.0.1 -p 5201 -t 10 -P 4 -J`
- **Ne Yapar?** Sunucuya 4 paralel bağlantı açarak 10 saniye boyunca yükleme hızı testi yapar. Çıktıyı JSON formatında (`-J`) verir, böylece backend doğrudan veriyi parse edebilir.

### ⏱️ Gecikme Ölçümü: `ping`
- **Neden Kuruldu?** Ağ katmanındaki tepki süresini (RTT) ve paket kaybını en basit ve kesin şekilde ölçer.
- **Komut:** `ping -i 0.5 -c 20 10.8.0.1`
- **Ne Yapar?** Yarım saniyede bir ping gönderir. Backend düzenli ifadeler (Regex) ile her bir ping çıktısını yakalar ve anında WebSocket üzerinden frontend'e iter.

### 📊 Kaynak Tüketimi: `vmstat`
- **Neden Kuruldu?** CPU idle (boşta) süresini hızlıca okumak için.
- **Komut:** `vmstat 1 10`
- **Ne Yapar?** 1'er saniyelik aralıklarla 10 kez sistem kaynak durumunu basar. VPN şifrelemesinin donanımı ne kadar yorduğunu gösterir.

### 💥 Stres Testi: `hping3`
- **Neden Kuruldu?** DoS (Denial of Service) saldırılarını simüle etmek için.
- **Komut:** `sudo hping3 --syn --flood -V -p 80 <hedef_ip>`
- **Ne Yapar?** Ağa yoğun paket göndererek VPN tünelinin yoğun yük altında (kargaşada) ne kadar stabil kaldığını test eder.

---

## 6. Ölçüm Kalemleri ve Puanlama Sistemleri

Toplanan ham verilerle iki ana skor hesaplanır:

### A. Genel Performans Skoru (0-100)
Şu ağırlıklara göre hesaplanır (`backend/routers/tests.py - compute_score`):
- **Gecikme (Latency):** Hedef değere göre ne kadar düşük olduğu.
- **Bant Genişliği (Throughput):** Sağlanan hızın tavan hıza oranı.
- **CPU Kullanımı:** Protokolün ne kadar verimli/hafif çalıştığı.
- **Paket Kaybı (Loss Tolerance):** Seçilen ağ profiline kıyasla protokolün kendi içinde ne kadar paket kaybettiği.
- **Stabilite (Jitter/StdDev):** Ping değerlerinin ne kadar istikrarlı olduğu.

### B. DPI (Derin Paket İnceleme) Direnç Skoru (0-100)
Bu skor, protokolün sansürcü veya kısıtlayıcı ağlarda (Çin Seddi, Kurumsal Firewall'lar) ayakta kalma yeteneğini tahmin eder.
- **Temel (Baseline):** Protokolün mimarisi (Örn: OpenVPN TCP yüksek, Wireguard düşük taban puan alır çünkü Wireguard'ın imzasını tespit etmek kolaydır).
- **Gözlemlenen Direnç:** Çok kötü şartlar altında (yüksek paket kaybı ve gecikme) protokol verimli veri taşıyabiliyor mu? Eğer zor şartlarda bağlantıyı koparmıyorsa bonus puan alır.

---

## 7. API Endpointleri

Sistem REST HTTP ve WebSocket protokollerini harmanlayarak kullanır.

- `POST /api/test/start`: İstenilen protokol ve koşulu alıp, testi asenkron başlatır. (Arka planda `asyncio.create_task` tetiklenir).
- `POST /api/test/stop`: Devam eden bir testi iptal eder. Temizlik foksiyonlarını (emergency cleanup) çalıştırır.
- `GET /api/test/status`: Sistemin o an boşta mı yoksa testte mi olduğunu döner.
- `GET /api/presets`: Kullanılabilir ağ senaryolarını (3G, Uydu, DoS vs.) döner.
- `GET /api/config`: VM altyapı ayarlarını getirir.
- `POST /api/config`: Yeni VM ayarlarını (IP, Kullanıcı, Şifre) kaydeder ve mevcut SSH havuzunu sıfırlar.
- `POST /api/config/test-connectivity`: VM'lere TCP bağlantısı ve ardından SSH bağlantısı deneyerek durumlarını (Açık/Kapalı/Hatalı) tespit eder.
- **`WS /ws/test` (WebSocket):** Saniyenin kesirlerinde toplanan ping, hız ve CPU verilerini canlı olarak React arayüzüne basar. Ayrıca her aşama değişikliğini (Test başladı, VPN bağlanıyor vb.) bildirir.

---

## 8. Neden Bu Mimariler Seçildi? (Tasarım Kararları)

1. **Neden Agent Kullanılmadı da Merkezi SSH (AsyncSSH) Tercih Edildi?**
   VM'lerin içerisine ajan (agent) bir yazılım kurmak yerine, FastAPI sunucusu VM'lere asenkron SSH (AsyncSSH) ile bağlanıp direkt Linux komutları işlemektedir. Bu, test edilecek makinelerde ekstra bağımlılık olmamasını sağlar (sadece `iperf3` ve `tc` yeterlidir).

2. **Neden Python FastAPI ve Asyncio?**
   Testler esnasında beklemeler (I/O Bound) çok yüksektir (örneğin pingin yanıt vermesi). `asyncio` sayesinde bu süreçler sunucuyu bloklamaz, aynı anda WebSocket üzerinden frontend'e veri akışı sekteye uğramadan sağlanır.

3. **Neden Zustand ve Tailwind?**
   Anlık akan verilerin (saniyede onlarca metrik) UI'ı dondurmaması için Zustand tercih edilmiştir. Re-render optimizasyonları kolaydır. Tailwind ise modern, dark mod destekli "hacker-vari" (premium) arayüzün hızlı inşasını sağlamıştır.
