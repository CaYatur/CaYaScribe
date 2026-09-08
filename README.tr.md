# CaYaScribe

Windows için yerel, çevrimdışı konuşmacı etiketli transkripsiyon. Ses ve video **bilgisayarınızdan çıkmaz**.

**Diller:** [English](README.md) (varsayılan) · [Türkçe](README.tr.md)

**Uygulama arayüzü** İngilizce veya Türkçe. İlk açılışta sistem diline bakılır; Türkçe değilse **İngilizce** kullanılır. Başlıktan değiştirebilirsiniz. Transkripsiyon 99+ dili kapsar (Whisper); bilinmeyen bir dil kodu İngilizce kabul edilir.

## Ne yapar

- MP3, MP4 ve diğer medyadan ses çıkarır (LGPL FFmpeg)
- 99+ dilde transkripsiyon (Whisper; Türkçe ve İngilizce birinci sınıf)
- İsteğe bağlı konuşmacı ayrımı: sayı boş = otomatik, `1` = tek kişi
- Konuşmacılar A, B, C… — tek seferde yeniden adlandırılır
- TXT / SRT / VTT / JSON dışa aktarma; zaman damgası isteğe bağlı
- İlk açılışta eksik modelleri **sorarak** indirir; sonra da Modeller’den indirilebilir

## Sürümler

Windows kurucuları [GitHub Releases](https://github.com/CaYatur/CaYaScribe/releases) sayfasında yayımlanır.

- `vX.Y.Z` etiketi basınca NSIS (`.exe`) üretilir ve sürüme eklenir
- Modeller kurucunun içinde **yoktur**; onayınızdan sonra indirilir
- v0.1 transkripsiyon için hâlâ Python sidecar bekler (geliştirme kurulumuna bakın)

Ayrıntı: [docs/releasing.md](docs/releasing.md) (İngilizce).

## Geliştirme kurulumu

Gerekenler: Windows 10+, Python 3.12+, Node 20+, Rust (Tauri).

```powershell
cd sidecar/python
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\pip install -e ".[dev]"

cd ..\..\apps\desktop
npm install
npm run tauri dev
```

İlk çalıştırmada FFmpeg, Whisper turbo (günlük), Qwen3-ASR 0.6B/1.7B (Türkçe ve gürültülü ses) ve konuşmacı modelleri önerilir. İstemediğini işaretten çıkar.

## Kalite profilleri

| Profil | Motor (v0.1) |
| --- | --- |
| Hızlı | Whisper `small` |
| Dengeli (varsayılan) | Whisper `large-v3-turbo` |
| Yüksek | İndirildiyse Qwen3-ASR 0.6B (CPU ONNX); yoksa turbo |
| Maksimum | İndirildiyse Qwen3-ASR 1.7B; yoksa 0.6B veya Whisper `large-v3` |

## Gizlilik

- STT buluta gitmez
- İndirmeler yalnızca onaydan sonra Hugging Face / GitHub’dan gelir
- Telemetri yok

Tasarım: [`docs/design.md`](docs/design.md)

## Lisans

Uygulama kodu: [MIT](LICENSE). Üçüncü taraf: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
