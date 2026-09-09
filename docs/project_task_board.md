# Project Task Board — BlueROV2 LED-Based Tracking and Control Pipeline

## 0. Genel Durum

Bu doküman, BlueROV2 LED tabanlı hedef takip sistemi için şu ana kadar yapılan işleri ve bundan sonra yapılacakları takip etmek amacıyla hazırlanmıştır.

Projenin güncel ana hedefi:

* Unity tarafında LED pattern üreten lider robotu izlemek,
* OpenCV tarafında LED çiftlerini ve pattern bilgisini çözmek,
* LED çiftinin orta noktasından hizalama hatası üretmek,
* LED arası piksel mesafesinden yaklaşık mesafe kestirmek,
* bu bilgileri Windows/OpenCV tarafından Linux kontrol tarafına UDP ile göndermek,
* sonrasında takipçi robotun bu verilere göre yönelim ve takip komutları üretmesini sağlamaktır.

---

# 1. Görüntü İşleme / OpenCV

## 1.1 Yapıldı

### PNG sequence okuma

* Unity Recorder ile alınan PNG frame dizileri başarıyla okunuyor.
* `01_preview_png_sequence.py` ile frame sırası, frame sayısı ve yaklaşık süre kontrol ediliyor.
* 600 frame / 60 FPS test akışı doğrulandı.

### HSV tabanlı LED aday çıkarımı

* `03_hsv_tuner.py` ile LED renkleri için HSV aralıkları test edildi.
* Renk bilgisinin tek başına güvenilir olmadığı görüldü.
* HSV, ana karar verici değil; sadece aday çıkarma katmanı olarak konumlandırıldı.

### Back LED pair detection

* İlk kontrollü testlerde yalnızca arka yüzey LED’leri aktif edildi.
* Arka yüzey rengi: yeşil.
* Arka yüzey pattern’i: `11001100`.
* `04_back_pair_distance_extract.py` ile:

  * LED adayları çıkarıldı,
  * iki LED merkezi bulundu,
  * iki LED arası piksel mesafesi hesaplandı,
  * frame bazlı ON/OFF bit dizisi üretildi.

### Pattern decode

* `05_back_pattern_decode.py` ile `11001100` pattern’i başarıyla decode edildi.
* İlk başta sadece local 8-bit pattern eşleşmesi kullanılıyordu.
* Daha sonra global repeated-pattern accuracy eklendi.
* Test 06 gibi uzak/sınır durumda local score `1.0` iken global accuracy `0.99`, bit error count `1` olarak ölçüldü.
* Bu sayede yalnızca “pattern bulundu mu?” değil, “tüm kayıt boyunca pattern ne kadar temiz?” sorusu da cevaplanabiliyor.

### Distance analysis

* `06_back_distance_analysis.py` ile güvenilir frame’ler filtrelendi.
* Kullanılan geçici güvenilirlik koşulu:

```text
bit == 1
pair_found == 1
candidate_count == 2
pixel_distance is not null
```

* Bu filtre, false positive veya ekstra blob çıkan frame’lerin mesafe hesabını bozmasını engelledi.
* Sabit kamera/robot testinde filtered std yaklaşık `0.61 px` seviyesine indirildi.

### Midpoint, normalized error ve camera ray

* `04_back_pair_distance_extract.py` içine şu alanlar eklendi:

  * `mid_x`
  * `mid_y`
  * `error_x`
  * `error_y`
  * `ray_x`
  * `ray_y`
  * `ray_z`
  * `image_width`
  * `image_height`

Bu değerler kontrol tarafına gönderilecek temel gözlem verisidir.

Örnek:

```text
midpoint_px = [890.0, 555.5]
error_norm = [-0.0729, -0.0287]
ray_cam = [-0.0746, -0.0165, 0.9971]
```

Bu şu anlama gelir:

* hedef görüntü merkezinin biraz solunda,
* hedef görüntü merkezinin biraz altında,
* hedef kamera önünde ve ray vektörü stabil.

---

## 1.2 Yapılacak

### Aday eşleştirme geliştirme

Şu anda back-only testte `candidate_count == 2` olan frame’ler güvenilir kabul ediliyor.

Sonraki aşamada:

* `candidate_count > 2` durumunda tüm aday çiftleri denenmeli,
* çiftler geometriye göre skorlanmalı,
* en mantıklı LED çifti seçilmeli.

Skorlama için kullanılabilecek ölçütler:

* LED alan benzerliği,
* y ekseni hizalılığı,
* önceki frame’deki mesafeye yakınlık,
* pattern tutarlılığı,
* temporal süreklilik.

### Temporal tracking

Sonraki aşamada LED merkezleri frame’den frame’e takip edilmeli.

Amaç:

* kısa süreli false positive etkisini azaltmak,
* LED merkezlerindeki ani sıçramaları bastırmak,
* daha kararlı kontrol verisi üretmek.

### Multi-face detection

Back-only test tamamlandıktan sonra:

* front,
* left,
* right

yüzleri için aynı pipeline genişletilecek.

Her yüz için ayrı:

* HSV aralığı,
* pattern,
* pair detection,
* pattern confidence,
* midpoint,
* distance confidence

hesaplanacak.

### Çapraz açı / 4 LED görünümü

Çapraz bakışlarda iki yüz aynı anda görülebilir.

Bu durumda tüm LED’lerin tek bir ortalaması alınmamalı.

Önerilen yaklaşım:

* Her yüz için ayrı observation üret.
* Örneğin:

  * BACK observation
  * RIGHT observation
* En yüksek confidence değerine sahip yüz `primary_face` seçilsin.
* Diğer görünür yüz `secondary_face` olarak gönderilebilir.

---

# 2. Mesafe Kalibrasyonu

## 2.1 Yapıldı

Back-only testlerde farklı kamera mesafeleri için LED arası piksel mesafesi ölçüldü.

Güncel kalibrasyon sonuçları:

| Test name        | Approx. distance | Pattern accuracy | Median pixel distance | Distance std | Notes                 |
| ---------------- | ---------------: | ---------------: | --------------------: | -----------: | --------------------- |
| BackOnly_Test_01 |             1.47 |             1.00 |                168 px |      0.61 px | Initial reference     |
| BackOnly_Test_02 |             2.00 |             1.00 |                118 px |     0.002 px | Stable                |
| BackOnly_Test_03 |             2.50 |             1.00 |                 92 px |      0.74 px | Usable                |
| BackOnly_Test_04 |             3.00 |             1.00 |              73.06 px |      0.82 px | Clean fixed-axis test |
| BackOnly_Test_05 |             4.00 |             1.00 |                 53 px |      0.67 px | Clean fixed-axis test |
| BackOnly_Test_06 |             5.00 |             0.99 |                 37 px |      2.24 px | Far-range boundary    |

Bu sonuçlar beklenen ilişkiyi doğruladı:

```text
kamera-hedef mesafesi artar → LED arası piksel mesafesi azalır
```

### Distance model

`07_distance_model.py` ile ilk mesafe modeli çıkarıldı.

Model:

```text
estimated_distance = 168.628584 / pixel_distance + 0.609526
```

Model performansı:

```text
Mean absolute error: 0.116 unit
RMSE: 0.131 unit
```

Bu model, ilk kontrol testleri için yeterli kabul edildi.

---

## 2.2 Yapılacak

### Daha temiz kalibrasyon seti

Test 02 ve Test 03 sırasında kamera X dışında Y/Z yönünde de küçük değişti.

Daha temiz final kalibrasyon için ileride sadece X değişen yeni bir kalibrasyon seti alınabilir:

```text
BackOnly_X_2m
BackOnly_X_2p5m
BackOnly_X_3m
BackOnly_X_4m
BackOnly_X_5m
```

Ancak mevcut model, ilk kontrol denemeleri için yeterlidir.

### LED düzlemi mesafesi

Şu an model, kamera ile robot root/pivot mesafesini kullanıyor.

Daha doğru mesafe için ileride:

* kamera pozisyonu,
* arka LED objelerinin world position değerleri,
* LED çiftinin gerçek merkez noktası

kullanılarak daha hassas kalibrasyon yapılabilir.

### Distance confidence geliştirme

Şu an distance confidence basit piksel mesafesi eşiklerine dayanıyor.

İleride confidence şu faktörlerle iyileştirilebilir:

* pixel distance büyüklüğü,
* pattern accuracy,
* candidate count,
* LED alan kararlılığı,
* temporal smoothness,
* görüş açısı.

---

# 3. Controller Observation Packet

## 3.1 Yapıldı

`08_generate_observation_packet.py` yazıldı.

Bu script:

* `back_pair_results.csv` dosyasını okuyor,
* pattern accuracy JSON özetini okuyor,
* distance model JSON özetini okuyor,
* güvenilir frame seçiyor,
* controller-ready JSON observation packet üretiyor.

Örnek packet:

```json
{
    "dataset": "BackOnly_Test_04",
    "requested_frame": 120,
    "selected_frame_delta": 0,
    "frame": 120,
    "valid": true,
    "face_id": "BACK",
    "pattern": "11001100",
    "pattern_accuracy": 1.0,
    "bit_error_count": 0,
    "bit_error_rate": 0.0,
    "pair_found": true,
    "candidate_count": 2,
    "midpoint_px": [890.0, 555.5],
    "error_norm": [-0.0729, -0.0287],
    "ray_cam": [-0.0746, -0.0165, 0.9971],
    "pixel_distance": 74.0068,
    "estimated_distance": 2.8881,
    "distance_confidence": 1.0,
    "image_size": [1920, 1080]
}
```

### Frame seçme opsiyonu

Script artık belirli frame’e en yakın valid observation seçebiliyor.

Örnek:

```powershell
python .\scripts\08_generate_observation_packet.py BackOnly_Test_04 120
```

Eğer 120. frame valid değilse, en yakın valid frame seçiliyor.

---

## 3.2 Yapılacak

### Real-time packet üretimi

Şu anda packet offline CSV’den üretiliyor.

Sonraki aşamada gerçek zamanlı pipeline’da her frame için:

* yeni observation oluşturulacak,
* valid/confidence kontrolü yapılacak,
* UDP ile Linux tarafına gönderilecek.

### Packet sadeleştirme

JSON debug için iyi.

Fakat gerçek zamanlı kullanımda gerekirse binary packet’e geçilebilir.

Binary packet’e geçmeden önce JSON ile:

* alanların doğru geldiği,
* Linux tarafında parse edildiği,
* kontrol tarafının beklenen verileri okuyabildiği

doğrulanmalı.

---

# 4. Haberleşme / UDP

## 4.1 Yapıldı

### Localhost UDP testi

İki script yazıldı:

```text
09_udp_send_observation.py
10_udp_receive_observation.py
```

Test:

```text
Sender: 127.0.0.1:5005
Receiver: 127.0.0.1:5005
Dataset: BackOnly_Test_04
Frame: 120
Packet count: 10
Rate: 10 Hz
```

Sonuç:

* 10 paket başarıyla gönderildi.
* 10 paket başarıyla alındı.
* JSON parse edildi.
* `udp_seq` değerleri 0’dan 9’a kadar doğru ilerledi.
* `valid`, `face_id`, `error_norm`, `ray_cam`, `estimated_distance`, `distance_confidence` alanları receiver tarafında doğru okundu.
* Localhost latency yaklaşık 0–1 ms aralığında gözlendi.

Bu aşama başarılıdır.

---

## 4.2 Yapılacak

### Windows → Linux UDP testi

Sonraki haberleşme testi:

* Windows tarafında sender,
* Linux tarafında receiver.

Linux tarafında:

```bash
python3 scripts/10_udp_receive_observation.py --host 0.0.0.0 --port 5005
```

Windows tarafında:

```powershell
python .\scripts\09_udp_send_observation.py --dataset BackOnly_Test_04 --frame 120 --ip LINUX_IP --port 5005 --count 50 --rate 10
```

Kontrol edilecekler:

* Windows ve Linux aynı ağda mı?
* Linux IP doğru mu?
* UDP 5005 firewall tarafından engelleniyor mu?
* Paketler sırayla geliyor mu?
* Packet loss var mı?
* Gecikme kabul edilebilir mi?

### Controller entegrasyonu

UDP receiver daha sonra kontrol kodu içine alınacak.

İlk kontrol tarafı şu alanları kullanabilir:

```text
valid
face_id
pattern_accuracy
error_norm
estimated_distance
distance_confidence
```

İlk kontrol davranışı:

* `valid == false` ise son geçerli gözlemi tut veya search mode’a geç.
* `pattern_accuracy` düşükse kontrol çıktısını azalt.
* `error_norm[0]` ile yaw düzelt.
* `error_norm[1]` ile dikey hizalama/pitch/depth düzelt.
* `estimated_distance` ile ileri/geri hız kararı ver.
* `distance_confidence` düşükse mesafe kontrolünü zayıflat.

---

# 5. Kontrol / Takip Davranışı

## 5.1 Yapıldı

Henüz gerçek takipçi kontrolüne bağlanmadı.

Ancak kontrol tarafına verilecek ölçümler hazırlandı:

* `error_norm`
* `ray_cam`
* `estimated_distance`
* `distance_confidence`
* `pattern_accuracy`
* `valid`

Bu değerler, kontrol algoritması için yeterli ilk observation formatını oluşturuyor.

---

## 5.2 Yapılacak

### İlk basit kontrol mantığı

Back-only takip için ilk kontrol mantığı şu olabilir:

```text
yaw_command      = K_yaw * error_norm[0]
vertical_command = K_z   * error_norm[1]
forward_command  = K_d   * (estimated_distance - desired_distance)
```

Gating:

```text
if valid == false:
    search mode veya son geçerli gözlem

if pattern_accuracy < threshold:
    kontrol komutunu zayıflat veya ignore et

if distance_confidence düşük:
    mesafe kontrolünü azalt, sadece hizalama yap
```

### Desired distance

Bir hedef takip mesafesi belirlenmeli.

Örneğin:

```text
desired_distance = 3.0 unit
```

Eğer:

```text
estimated_distance > desired_distance
```

takipçi ileri gitmeli.

Eğer:

```text
estimated_distance < desired_distance
```

takipçi yavaşlamalı veya geri gitmeli.

### Search / lost target mode

Hedef kaybolursa:

* kısa süre son valid observation tutulabilir,
* sonra yaw scan/search davranışı başlatılabilir,
* confidence geri yükselince track mode’a dönülür.

---

# 6. Unity / Simülasyon

## 6.1 Yapıldı

### LED pattern üretimi

Unity tarafında arka LED’ler için frame tabanlı pattern üretimi doğrulandı.

Kullanılan ayarlar:

```text
FPS = 60
framesPerBit = 6
pBack = 11001100
```

### Back-only test

Back-only test senaryosu kullanıldı.

Bu senaryoda:

* yalnızca arka LED’ler aktif,
* diğer yüzler kapalı,
* pattern ve mesafe ölçümü daha kontrollü şekilde test edildi.

---

## 6.2 Yapılacak

### Tüm yüzlerin açılması

Back-only pipeline stabil hale geldikten sonra tüm yüzler açılacak:

```text
frontLEDs
backLEDs
leftLEDs
rightLEDs
```

Her yüz kendi pattern’iyle aktif olacak.

### Çapraz açı testleri

Robot farklı açılardan gözlemlenecek.

Test edilecek durumlar:

* yalnızca back görünür,
* back + right görünür,
* back + left görünür,
* side-only görünüm,
* kısmi LED kaybı,
* uzak mesafe,
* bloom/yansıma etkisi.

---

# 7. GitHub / Versiyon Kontrol

## 7.1 Yapıldı

Repo oluşturuldu ve ilk pipeline commitleri atıldı.

Kodlar şu yapıya taşındı:

```text
scripts/
unity/
docs/
datasets/
outputs/
```

`datasets/` ve `outputs/` Git tarafından ignore ediliyor.

Bu sayede:

* kodlar GitHub’da tutuluyor,
* büyük PNG ve CSV çıktıları repo’ya eklenmiyor,
* deney çıktıları lokal veya Drive/OneDrive üzerinden saklanıyor.

---

## 7.2 Yapılacak

### Commit disiplini

Her anlamlı geliştirme sonrası commit atılmalı.

Örnek commit başlıkları:

```text
Add UDP observation packet test scripts
Add multi-face detection pipeline
Improve LED pair candidate scoring
Add controller integration receiver
Update calibration log
```

### Dokümantasyon

Her büyük aşama sonrası:

* `README.md`
* `docs/progress_log.md`
* `docs/calibration_log.md`
* `docs/next_steps.md`

güncellenmeli.

---

# 8. Önceliklendirilmiş Sonraki İşler

## Kısa vadeli işler

1. Windows → Linux UDP testini yap.
2. Linux tarafında packet parse edildiğini doğrula.
3. Controller tarafında `error_norm` ve `estimated_distance` alanlarını kullanacak basit bir debug script yaz.
4. Back-only takip için ilk kontrol mantığını tanımla.
5. Search/lost target davranışının basit taslağını çıkar.

## Orta vadeli işler

1. Tüm yüzlerin LED patternlerini birlikte aktif et.
2. Multi-face detection pipeline oluştur.
3. Her yüz için ayrı observation üret.
4. Primary/secondary face seçimi yap.
5. Çapraz açı ve kısmi görünüm testleri yap.

## Uzun vadeli işler

1. JSON UDP yerine binary UDP packet’e geçmeyi değerlendir.
2. Gerçek zamanlı frame processing pipeline kur.
3. Unity/Gazebo/ArduSub kontrol döngüsüne tam entegrasyon yap.
4. Bitirme raporu için deney tabloları ve görselleri üret.
5. Final demo senaryosunu oluştur.





30.05.26 update



# Project Task Board — BlueROV2 LED-Based Tracking and Control Pipeline

## 0. Genel Durum

Bu doküman, BlueROV2 LED tabanlı hedef takip sistemi için yapılan işleri ve sonraki geliştirme adımlarını takip etmek amacıyla hazırlanmıştır.

Güncel sistem seviyesi:

```text
Unity recorded video
→ OpenCV video detection
→ UDP observation packet
→ Linux controller
→ MAVLink MANUAL_CONTROL
→ ArduSub/Gazebo motion
→ STOP/DISARM safety

Bu aşama offline video tabanlı entegrasyon testidir. Gerçek canlı kapalı çevrim henüz tamamlanmamıştır.

1. Done
1.1 OpenCV / Vision

Unity PNG sequence okuma

HSV tabanlı LED aday çıkarımı

Back-only LED pair detection

Back pattern decode: 11001100

Global repeated-pattern accuracy hesabı

Distance analysis

Distance model fitting

Current distance model:

estimated_distance = 168.628584 / pixel_distance + 0.609526

LED pair midpoint calculation

Normalized image error calculation

Camera ray calculation

Controller-ready JSON observation packet generation

1.2 UDP / Communication

Localhost UDP send/receive test

Windows-to-Linux UDP observation streaming

CSV replay UDP sender

Script:

scripts/11_replay_back_observation_from_csv.py

PNG sequence OpenCV UDP sender

Script:

scripts/12_live_back_png_sequence_sender.py

MP4 video OpenCV UDP sender

Script:

scripts/13_live_back_video_sender.py
1.3 Unity / Dataset Generation

Frame-based LED timing

Back-only test mode

Unity GazeboDataReceiver keyboard-relative mode

Python keyboard pose sender

Unity Movie Recorder setup

Dynamic BACK video recording

Dataset:

BackOnly_Dynamic_Test_01.mp4

Properties:

1201 frames
60 FPS
20.0167 seconds
1920x1080
1.4 Linux Control Integration

MAVLink heartbeat connection

MANUAL mode request

ARM/DISARM test

MANUAL_CONTROL axis mapping

Safe UDP-to-MAVLink controller

Script:

05_udp_to_mavlink_controller_safe.py

Arms-off CSV replay test

Armed CSV replay test

Arms-off PNG sequence test

Armed PNG sequence test

Arms-off video sender test

Armed video sender test with reduced gains

Safe armed-test parameters:

k_forward = 100
k_yaw = 120
max_x = 120
max_r = 120
runtime = 10 s
2. In Progress

Improve video detection stability

Analyze video_observation_log.csv

Render debug overlay video

Improve candidate pair selection when candidate_count > 2

Improve held_observation logic

Add command smoothing and deadband to Linux controller

Prepare live Unity/Unreal render capture

3. Next
3.1 Vision-side next tasks

Create scripts/14_analyze_video_observation_log.py

Create scripts/15_render_video_detection_debug.py

Add pair scoring for candidate selection

Add reason-based hold duration

Add temporal continuity checks

Tune HSV thresholds for MP4 and live-render cases

3.2 Control-side next tasks

Create 06_live_udp_to_mavlink_controller.py

Add yaw deadband

Add forward deadband

Add command EMA smoothing

Add acceleration limiting

Add confidence-based gain scaling

Add explicit state machine:

TRACK
ALIGN_ONLY
INVALID
PACKET_TIMEOUT
STOP
SEARCH
3.3 Simulation-side next tasks

Test cleaner Unity video without fish occlusion

Record dynamic videos at different distances

Record videos with controlled lateral motion

Record videos with controlled yaw motion

Add live Unity window/render capture

Repeat the same process in Unreal Engine

3.4 Long-term tasks

Move from offline video to live render capture

Build true closed-loop tracking

Extend from BACK-only to multi-face tracking

Add FRONT / LEFT / RIGHT face patterns

Add primary/secondary face selection

Add search/lost-target behavior

Evaluate JSON vs compact binary UDP packet


---