# Vendor assets

Semua berkas diunduh pada 2026-11-13 dan disimpan lokal. Runtime tidak melakukan permintaan jaringan. Ukuran dan SHA-256 diukur dari berkas yang benar-benar tersimpan di folder ini.

## Tabel aset

| Berkas | Nama | Versi | Lisensi | URL resmi | Cara memperoleh | Ukuran (byte) | SHA-256 |
|---|---|---|---:|---|---|---:|---|
| `js/chart.umd.js` | Chart.js UMD | 4.6.1 | MIT | https://github.com/chartjs/Chart.js | `curl https://cdn.jsdelivr.net/npm/chart.js@4.6.1/dist/chart.umd.js` | 210078 | `338399fb5bafe598d21cfc471b0590b61ceb321a985fade4f68499b151f67fbf` |
| `js/chart.LICENSE.md` | Chart.js license | 4.6.1 | MIT | https://github.com/chartjs/Chart.js/blob/master/LICENSE.md | diunduh bersama paket | 1093 | lihat berkas |
| `css/pico.min.css` | Pico CSS | 2.1.1 | MIT | https://github.com/picocss/pico | `curl https://cdn.jsdelivr.net/npm/@picocss/pico@2.1.1/css/pico.min.css` | 83319 | `fbc9a63fc9fc9f72d12fd7fc9806e11fa9f77ae4f9cad146b27003a1119ba3db` |
| `css/pico.LICENSE.md` | Pico license | 2.1.1 | MIT | https://github.com/picocss/pico/blob/master/LICENSE.md | diunduh bersama paket | 1066 | lihat berkas |
| `fonts/JetBrainsMono-Regular.ttf` | JetBrains Mono | 2.304 | SIL OFL 1.1 | https://github.com/JetBrains/JetBrainsMono | rilis v2.304, ekstrak `fonts/ttf/` | 273900 | `a0bf60ef0f83c5ed4d7a75d45838548b1f6873372dfac88f71804491898d138f` |
| `fonts/JetBrainsMono-Medium.ttf` | JetBrains Mono Medium | 2.304 | SIL OFL 1.1 | https://github.com/JetBrains/JetBrainsMono | idem | 273860 | `31c92d01a8a08528b718a43addf0ad3df0af2ca4b7b3290a452f70f358e14d3d` |
| `fonts/JetBrainsMono-SemiBold.ttf` | JetBrains Mono SemiBold | 2.304 | SIL OFL 1.1 | https://github.com/JetBrains/JetBrainsMono | idem | 277092 | `1b3bfa1ed5665a4ce3f9feb68d2d4e40e70bf8b4b7d9a3edd418f321b4e166a0` |
| `fonts/JetBrainsMono-Bold.ttf` | JetBrains Mono Bold | 2.304 | SIL OFL 1.1 | https://github.com/JetBrains/JetBrainsMono | idem | 277828 | `5590990c82e097397517f275f430af4546e1c45cff408bde4255dad142479dcb` |
| `fonts/OFL.txt` | OFL text | 2.304 | SIL OFL 1.1 | https://github.com/JetBrains/JetBrainsMono/blob/master/OFL.txt | dari arsip rilis | 4399 | `30f0c136e3c88e422d0791acd97238870f9054a9729bc34cf2ff0d4ed8cac4ad` |
| `js/uplot.iife.min.js` | uPlot IIFE min | 1.6.32 | MIT | https://github.com/leeoniya/uPlot | curl https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.iife.min.js | 51081 | `19c8d4c6ad88929a79f4ae49d6f7161566dfd0ba3d15cc495e974f787eb78f1f` |
| `css/uplot.min.css` | uPlot CSS | 1.6.32 | MIT | https://github.com/leeoniya/uPlot | curl https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.min.css | 1857 | `df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04` |
| `fonts/InstrumentSans-Variable.woff2` | Instrument Sans variable | v4 latin subset | SIL OFL 1.1 | https://fonts.google.com/specimen/Instrument+Sans | Google Fonts CSS API, woff2 latin subset | 30092 | `2ee17598a98d8a59e4df8152d015bec9ab8e4d5672cc0ab42bef806b568e3971` |

Ada dua grafik yang tersimpan: Chart.js untuk halaman lama, uPlot untuk kurva cahaya. Halaman baru memuat uPlot (51081 byte) dan Instrument Sans variable (30092 byte), bukan Chart.js, karena deret waktu kita hanya butuh garis dan uPlot seperempat ukurannya. Tidak ada aset gambar, tekstur, atau pola dari sumber pihak ketiga di folder ini.

## Kandidat yang ditolak

| Kandidat | Lisensi | Alasan tidak dipakai |
|---|---|---|
| DaisyUI 5 | MIT | Jalur resminya membutuhkan Tailwind CSS dan langkah build. FigCraft mengisi frame statis, jadi rantai build itu tidak memberi keuntungan dan menambah dependensi saat demo. |
| Radix Primitives | MIT | Memerlukan React sebagai runtime. Syarat tugas melarang dependensi framework berat. |
| shadcn/ui | MIT | Bukan paket, melainkan kode yang disalin ke proyek React. Sama seperti Radix: butuh React. |
| Observable Plot | ISC | Butuh D3 sebagai peer dan berorientasi SVG sumbu kartesius. Tidak ada keunggulan untuk satu dial melingkar dibanding Chart.js, dan menambah satu dependensi lagi. |
| D3 | ISC | 280 KB lebih, dan untuk satu dial cukup memakai primitif SVG. Ditolak karena ukuran, bukan lisensi. |
| uPlot | MIT | Cepat, tetapi tidak punya dukungan polar atau radial. Kebutuhannya justru radial. |

Tidak ada kandidat yang ditolak karena lisensi tidak jelas atau tidak kompatibel dengan Apache 2.0. MIT dan SIL OFL 1.1 keduanya kompatibel.

## Pemetaan mekanisme ke aset

| Mekanisme | Referensi | Aset | Bagaimana terwujud |
|---|---|---|---|
| Tiga zona tetap, panel angka di kanan | R1 | Pico CSS 2.1.1 | Primitif `fieldset` dan `article` memberi panel berlabel tanpa runtime. Di FigCraft, tata letak tiga zona digambar mengikuti disiplin grid Pico (satu satuan jarak, tanpa bingkai dekoratif). |
| Angka besar, satuan menempel, dua tingkat bobot | R2 | JetBrains Mono 2.304 | Monospace tabular untuk setiap angka, pasangan bobot 600 judul angka dan 400 keterangan di bawahnya. |
| Panel berketerangan sendiri, kotak parameter | R3 | Pico CSS 2.1.1 | `fieldset` dengan `legend` berisi judul, `small` berisi satuan dan sumber di dalam kotak. |
| Dial melingkar memetakan waktu ke sudut | R4 | Chart.js 4.6.1 | `polarArea` dan radial linear scale memberi pemetaan sudut ke nilai. Di FigCraft jalur digambar sebagai garis tunggal tanpa isi karena FigCraft bukan runtime web. |
