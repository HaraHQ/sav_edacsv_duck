# Referensi Definisi Event Penerbangan

**Classifier:** `flight_phase_classifier.py` — FOQAFlightClassifier v3  
**Pesawat:** Cessna 208 / 208B Grand Caravan / 208B Grand Caravan EX  
**Terakhir diperbarui:** 2026-03-02

---

## Gambaran Umum

Event penerbangan adalah kondisi tertentu yang ditandai selama proses klasifikasi fase penerbangan. Event disimpan di kolom `FLIGHT_EVENT` pada CSV yang telah diklasifikasi. Beberapa event pada baris yang sama dipisahkan dengan tanda pipa (contoh: `HIGH_DESCENT_RATE_S2|UNSTABLE_APPROACH_S2`).

### Tingkat Keparahan (Severity)

| Tingkat | Label | Arti | Tindakan |
|---|---|---|---|
| 1 | **S1 — Notifikasi** | Informasi. Ditandai untuk analisis tren dan pemantauan pola. | Catat dan pantau jika berulang. |
| 2 | **S2 — Peringatan** | Penyimpangan SOP atau risiko operasional. | Investigasi. Debrief dengan pilot. |
| 3 | **S3 — Kritis** | Masalah kelaikan udara atau risiko keselamatan yang segera. | Laporan wajib. Review teknik sebelum penerbangan berikutnya. |

### Konvensi Label

Setiap nama event menyertakan tingkat keparahannya sebagai akhiran: `NAMAVENT_S{1|2|3}`  
Contoh: `HARD_LANDING_S3`, `HIGH_DESCENT_RATE_S1`

---

## Event Pendaratan

### HARD_LANDING — Pendaratan Keras

Terdeteksi ketika beban vertikal (g-load) melebihi batas normal pendaratan saat pesawat berada di atau dekat permukaan landasan.

| Severity | Pemicu | Persistensi | Tindakan |
|---|---|---|---|
| S2 | NormAc ≥ 1,8 g, AGL < 30 ft, GndSpd > 20 kts | 2 baris | Catat. Pantau untuk tren struktural. |
| S3 | NormAc ≥ 2,1 g, AGL < 30 ft, GndSpd > 20 kts | 2 baris | Inspeksi struktural perawatan wajib sebelum penerbangan berikutnya. |

**Nilai puncak yang dicatat:** NormAc maksimum (g) selama jendela event.

> **Catatan:** Ambang batas mengacu pada POH Cessna 208B. Varian EX menggunakan batas g yang sama karena struktur airframe tidak berubah.

---

## Event Kualitas Pendekatan (Approach)

### HIGH_DESCENT_RATE — Laju Penurunan Berlebih

Laju penurunan yang berlebihan selama fase pendekatan dan pendaratan. Merupakan prekursor utama CFIT (Controlled Flight Into Terrain) dalam operasi penerbangan perintis turboprop.

| Severity | Pemicu | Persistensi | Tindakan |
|---|---|---|---|
| S1 | VSpd < −1.000 fpm di bawah 1.000 ft AGL | 3 baris | Tinjau manajemen energi pada pendekatan. |
| S2 | VSpd < −1.500 fpm di bawah 500 ft AGL | 3 baris | Memenuhi kriteria pendekatan tidak stabil. Investigasi. |
| S3 | VSpd < −2.000 fpm di bawah 500 ft AGL | 2 baris | Risiko CFIT. Koreksi segera diperlukan. Debrief wajib. |

**Nilai puncak yang dicatat:** VSpd minimum (fpm, paling negatif) selama jendela event.

---

### HIGH_APPROACH_SPEED — Kecepatan Pendekatan Terlalu Tinggi

Kecepatan angin indikasi (IAS) jauh di atas Vref saat final approach. Menyebabkan float, pendaratan panjang, dan risiko overrun landasan.

| Severity | Pemicu | Ketinggian | Persistensi | Tindakan |
|---|---|---|---|---|
| S1 | IAS > Vref + 20 kts | < 500 ft, menurun | 5 baris | Risiko float dan overrun. Tinjau manajemen daya. |
| S2 | IAS > Vref + 35 kts | < 500 ft, menurun | 5 baris | Risiko overrun landasan yang signifikan. Investigasi. |

**Nilai puncak yang dicatat:** IAS maksimum (kts) selama jendela event.

> Nilai Vref berdasarkan tipe pesawat: 208 Caravan — 82 kts, 208B — 85 kts, 208B EX — 88 kts (proxy berat sedang).

---

### LOW_APPROACH_SPEED — Kecepatan Pendekatan Terlalu Rendah

Kecepatan angin indikasi di bawah Vref saat final approach. Mengurangi margin stall pada fase penerbangan yang paling kritis.

| Severity | Pemicu | Ketinggian | Persistensi | Tindakan |
|---|---|---|---|---|
| S2 | IAS < Vref − 10 kts | < 500 ft, menurun | 3 baris | Margin stall berkurang. Go-around direkomendasikan. Debrief pilot. |

**Nilai puncak yang dicatat:** IAS minimum (kts) selama jendela event.

---

### UNSTABLE_APPROACH — Pendekatan Tidak Stabil

Ketidakstabilan multi-parameter saat pendekatan. Aktif ketika **2 atau lebih** kondisi berikut terpenuhi secara bersamaan di bawah 1.000 ft AGL pada sisi kedatangan:

- IAS di luar Vref ± 10/20 kts
- VSpd < −1.200 fpm
- Sudut bank > 10°
- Torque < 400 ft·lb (idle atau mendekati idle)

| Severity | Pemicu | Persistensi | Tindakan |
|---|---|---|---|
| S2 | Skor ≥ 2 dari 4 parameter, AGL 10–1.000 ft, menurun | 5 baris | Investigasi. Kriteria stabilisasi pendekatan tidak terpenuhi. |

---

## Event Manajemen Daya

### RAPID_POWER — Penambahan Daya Mendadak

Penambahan torque yang tiba-tiba terdeteksi dari diferensial torque 1-Hz mentah. Penambahan daya yang agresif memberi tekanan pada seksi kompresor PT6 dan meningkatkan risiko compressor stall.

| Severity | Pemicu | Kondisi | Persistensi | Tindakan |
|---|---|---|---|---|
| S1 | Laju torque > 200 ft·lb/s | Sedang terbang | 1 baris | Penambahan mendadak. Tinjau teknik penggunaan throttle. |
| S2 | Laju torque > 400 ft·lb/s | Sedang terbang | 1 baris | Penambahan agresif. Risiko compressor stall. Debrief. |

**Nilai puncak yang dicatat:** Laju perubahan torque maksimum (ft·lb/s) selama jendela event.

> **Catatan:** Laju dihitung dari selisih torque 1-Hz mentah (bukan `Torq_deriv` yang telah dihaluskan) agar dapat menangkap hentakan throttle singkat yang akan tersamarkan jika dihaluskan.

---

## Event Penyimpangan Kecepatan

### OVERSPEED — Kecepatan Berlebih

Kecepatan angin indikasi melebihi Kecepatan Operasi Maksimum (Vmo = 175 KIAS untuk semua varian 208).

| Severity | Pemicu | Kondisi | Persistensi | Tindakan |
|---|---|---|---|---|
| S2 | IAS > 175 kts | Sedang terbang | 3 baris | Risiko beban struktural. Catat dan inspeksi. |
| S3 | IAS > 185 kts | Sedang terbang | 3 baris | Mendekati batas struktural. Laporan perawatan wajib. |

**Nilai puncak yang dicatat:** IAS maksimum (kts) selama jendela event.

---

### LOW_AIRSPEED — Kecepatan Terlalu Rendah

Kecepatan angin indikasi di bawah referensi minimum yang aman saat sedang terbang di atas 100 ft AGL. Tidak termasuk zona flare dan pendaratan untuk menghindari pemicu palsu saat deselerasi normal menuju touchdown.

| Severity | Pemicu | Kondisi | Persistensi | Tindakan |
|---|---|---|---|---|
| S2 | IAS di bawah `low_airspeed_warn` | AGL > 100 ft, sedang terbang | 3 baris | Margin stall berkurang. Tinjau manajemen energi. |
| S3 | IAS di bawah `low_airspeed_critical` | AGL > 100 ft, sedang terbang | 2 baris | Risiko stall / LOC-I segera. Debrief wajib. |

**Nilai puncak yang dicatat:** IAS minimum (kts) selama jendela event.

Nilai referensi berdasarkan tipe pesawat:

| Pesawat | Ambang S2 | Ambang S3 |
|---|---|---|
| Cessna 208 Caravan | 78 kts | 68 kts |
| Cessna 208B Grand Caravan | 78 kts | 68 kts |
| Cessna 208B Grand Caravan EX | 80 kts | 70 kts |

---

## Event Sikap dan Manuver

### STEEP_BANK — Bank Terlalu Curam

Sudut bank melebihi batas operasional. Tingkat keparahan ditentukan oleh kombinasi sudut bank dan AGL — semakin rendah ketinggian, semakin berbahaya sudut bank yang sama.

| Severity | Pemicu | Ketinggian AGL | Persistensi | Tindakan |
|---|---|---|---|---|
| S1 | Bank > 45° | Di atas 1.000 ft | 3 baris | Di luar operasi normal. Tinjau airmanship. |
| S2 | Bank > 30° | 50–1.000 ft | 3 baris | Melebihi batas operasional dekat terrain. Debrief. |
| S3 | Bank > 45° | 50–500 ft | 2 baris | Zona risiko LOC-I. Koreksi segera diperlukan. Laporan wajib. |

**Nilai puncak yang dicatat:** Sudut roll absolut maksimum (derajat) selama jendela event.

---

### NEGATIVE_G — Beban G Negatif

Faktor beban vertikal negatif terdeteksi saat sedang terbang. Sistem bahan bakar dan oli PT6A tidak disertifikasi untuk operasi G negatif yang berkelanjutan.

| Severity | Pemicu | Kondisi | Persistensi | Tindakan |
|---|---|---|---|---|
| S1 | NormAc < 0 g | Sedang terbang | 1 baris | Unloading singkat. Pantau jika berulang. |
| S2 | NormAc < 0 g | Sedang terbang | 3 baris | G negatif berkelanjutan. Risiko gangguan sistem bahan bakar dan oli. Debrief. |

**Nilai puncak yang dicatat:** NormAc minimum (g, paling negatif) selama jendela event.

---

### TAIL_STRIKE_RISK — Risiko Tail Strike

Sikap pitch tinggi dikombinasikan dengan kecepatan rendah dekat permukaan tanah. Menandai geometri yang dapat menyebabkan kontak ekor sebelum kondisi tersebut tidak dapat diperbaiki.

| Severity | Pemicu | Kondisi | Persistensi | Tindakan |
|---|---|---|---|---|
| S2 | Pitch > 15°, IAS < Vr + 10 kts, AGL < 50 ft, GndSpd > 30 kts | Ground roll / rotasi | 2 baris | Geometri tail strike. Debrief teknik rotasi. |

**Nilai puncak yang dicatat:** Sudut pitch maksimum (derajat) selama jendela event.

---

## Event Mesin dan Sistem

### HIGH_ITT — Suhu Turbin Tinggi

Inter-Turbine Temperature di atas batas operasional. ITT tinggi yang berkelanjutan mempercepat degradasi hot-section dan memperpendek Time Between Overhaul (TBO).

| Severity | Pemicu | Kondisi | Persistensi | Tindakan |
|---|---|---|---|---|
| S2 | ITT di atas `itt_warn` | Sedang terbang | 5 baris | Di atas batas max continuous. Keausan hot-section dipercepat. Catat untuk tren perawatan. |
| S3 | ITT di atas `itt_limit` | Sedang terbang | 3 baris | Pada atau di atas batas takeoff saat cruise. Inspeksi mesin wajib sebelum penerbangan berikutnya. |

**Nilai puncak yang dicatat:** ITT maksimum (°C) selama jendela event.

Nilai referensi ITT berdasarkan tipe pesawat:

| Pesawat | Mesin | Ambang S2 | Ambang S3 |
|---|---|---|---|
| Cessna 208 / 208B | PT6A-114A | 740 °C | 800 °C |
| Cessna 208B EX | PT6A-140A | 750 °C | 810 °C |

> ⚠️ **Nilai-nilai ini harus diverifikasi terhadap AMM pesawat sebelum digunakan di lingkungan produksi.** Batas bervariasi berdasarkan nomor seri mesin, status modifikasi, dan ketinggian operasi.

---

## Event Prosedural / Informasional

Event-event ini bukan merupakan kesalahan pilot secara langsung. Merupakan penanda kontekstual yang mendukung analisis rute, debrief, dan pemantauan tren.

### GO_AROUND — Go-Around

Penambahan daya yang cepat dengan pemulihan vertical speed positif di bawah 300 ft AGL, dari fase landing band. Menandakan bahwa go-around telah dilaksanakan.

| Severity | Pemicu | Kondisi | Persistensi |
|---|---|---|---|
| S1 | Laju torque > 200 ft·lb/s DAN VSpd memulih DAN VSpd > −200 fpm | AGL < 300 ft, dari fase APPROACH / FLARE | 3 baris |

---

### REJECTED_TAKEOFF — Penolakan Takeoff

Deselerasi kecepatan tinggi di darat dengan pengurangan daya secara bersamaan. Menandakan bahwa RTO dilakukan di atas 40 kts groundspeed.

| Severity | Pemicu | Kondisi | Persistensi | Tindakan |
|---|---|---|---|---|
| S2 | GndSpd > 40 kts, laju torque < −200 ft·lb/s, deselerasi | AGL < 30 ft | 3 baris | Inspeksi rem dan struktural sesuai manual perawatan. |

---

### UNSTABLE_DEPARTURE — Keberangkatan Tidak Stabil

Ketidakstabilan kecepatan, vertical speed, bank, atau torque selama climb keberangkatan di bawah 1.500 ft AGL. Aktif ketika **2 atau lebih** kondisi berikut terpenuhi pada sisi keberangkatan:

- IAS di luar band climb normal
- VSpd < 50% dari laju climb yang diharapkan
- Bank > 20°
- Torque < 70% dari torque climb minimum

| Severity | Pemicu | Persistensi |
|---|---|---|
| S1 | Skor ≥ 2 dari 4 parameter, AGL 30–1.500 ft, sisi keberangkatan | 5 baris |

---

### UNSTABLE_CIRCUIT — Sirkuit Tidak Stabil

Ketidakstabilan kecepatan, vertical speed, atau bank di zona traffic pattern (200–1.500 ft AGL), tidak termasuk baris yang sudah ditandai sebagai unstable approach atau departure.

| Severity | Pemicu | Persistensi |
|---|---|---|
| S1 | ≥ 2 dari: IAS di luar band / VSpd > ±1.500 fpm / Bank > 30° | 4 baris |

---

### ENGINE_IDLE_DESCENT — Descent dengan Mesin Idle

Tiga puluh detik atau lebih secara berurutan melakukan descent dengan fuel flow idle di atas 500 ft AGL. Descent idle yang berkepanjangan dapat menyebabkan thermal shock pada turbin PT6.

| Severity | Pemicu | Persistensi |
|---|---|---|
| S1 | VSpd < −300 fpm, fuel flow pada idle, AGL > 500 ft | 30 baris berurutan |

---

### HIGH_WIND_LANDING — Pendaratan Angin Kencang

Komponen angin silang (crosswind) melebihi batas demonstrated crosswind pesawat saat pendekatan atau pendaratan.

| Severity | Pemicu | Kondisi |
|---|---|---|
| S1 | CrosswindComp > 15 kts | AGL < 500 ft, GndSpd > 20 kts |

> Batas 15 kts berlaku untuk semua varian 208 sesuai POH. Sesuaikan `high_wind_landing_kts` dalam konfigurasi jika SOP perusahaan menggunakan batas yang lebih rendah.

---

## Referensi Konfigurasi

Semua ambang batas didefinisikan per tipe pesawat dalam `AIRCRAFT_CONFIGS` di dalam `flight_phase_classifier.py`. Batas spesifik event menggunakan kunci konfigurasi berikut:

| Kunci Konfigurasi | Digunakan Oleh | Satuan |
|---|---|---|
| `vmo_kias` | OVERSPEED | KIAS |
| `vref_approach` | HIGH/LOW_APPROACH_SPEED | kts |
| `hard_landing_g` | HARD_LANDING S2 | g |
| `hard_landing_g_critical` | HARD_LANDING S3 | g |
| `low_airspeed_warn` | LOW_AIRSPEED S2 | kts |
| `low_airspeed_critical` | LOW_AIRSPEED S3 | kts |
| `itt_warn` | HIGH_ITT S2 | °C |
| `itt_limit` | HIGH_ITT S3 | °C |
| `rapid_power_warn` | RAPID_POWER S1 | ft·lb/s |
| `rapid_power_critical` | RAPID_POWER S2 | ft·lb/s |
| `high_wind_landing_kts` | HIGH_WIND_LANDING | kts |
| `steep_turn_bank` | STEEP_BANK | derajat |

---

## Event yang Dihapus dari Versi Sebelumnya

| Event Lama | Digantikan Oleh | Alasan |
|---|---|---|
| `HARD_LANDING` | `HARD_LANDING_S2` / `S3` | Penambahan tiering severity |
| `GO_AROUND` | `GO_AROUND_S1` | Standarisasi konvensi akhiran |
| `REJECTED_TAKEOFF` | `REJECTED_TAKEOFF_S2` | Standarisasi konvensi akhiran |
| `UNSTABLE_APPROACH` | `UNSTABLE_APPROACH_S2` | Standarisasi konvensi akhiran |
| `UNSTABLE_DEPARTURE` | `UNSTABLE_DEPARTURE_S1` | Standarisasi konvensi akhiran |
| `UNSTABLE_CIRCUIT` | `UNSTABLE_CIRCUIT_S1` | Standarisasi konvensi akhiran |
| `STEEP_TURN` | `STEEP_BANK_S1/S2/S3` | Diganti dengan versi bertingkat berdasarkan AGL |
| `ENGINE_IDLE_DESCENT` | `ENGINE_IDLE_DESCENT_S1` | Standarisasi konvensi akhiran |
| `HIGH_WIND_LANDING` | `HIGH_WIND_LANDING_S1` | Standarisasi konvensi akhiran |
