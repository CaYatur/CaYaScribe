# CaYaScribe

Yerel, çevrimdışı konuşmacı etiketli transkripsiyon. Ses ve video **bilgisayarınızdan çıkmaz**.

Local, offline speaker-aware transcription. Audio and video **never leave your machine**.

## Ne yapar / What it does

- MP3, MP4 ve diğer medya dosyalarından ses çıkarır (LGPL FFmpeg)
- 99+ dilde transkripsiyon (Whisper; Türkçe ve İngilizce birinci sınıf)
- İsteğe bağlı konuşmacı ayrımı: sayı girilmezse otomatik, `1` ise tek kişi
- Konuşmacılar A, B, C… — tek seferde yeniden adlandırılır
- TXT / SRT / VTT / JSON dışa aktarma; zaman damgası isteğe bağlı
- İlk açılışta eksik modelleri **sorarak** indirir; sonra da Ayarlar’dan indirilebilir

## Hızlı başlangıç (geliştirme)

Gerekenler: Windows 10+, Python 3.12+, Node 20+, Rust (Tauri).

```powershell
# 1) Sidecar sanal ortamı
cd sidecar/python
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\pip install -e ".[dev]"

# 2) Masaüstü
cd ..\..\apps\desktop
npm install
npm run tauri dev
```

İlk çalıştırmada uygulama **Dengeli** profil için FFmpeg + Whisper turbo + konuşmacı modellerini indirmek ister (~2 GB). İsterseniz sadece **Hızlı** (small) işaretleyip daha küçük bir indirmeyle deneyebilirsiniz.

## Kalite profilleri

| Profil | Motor (v0.1) |
| --- | --- |
| Hızlı | Whisper `small` |
| Dengeli (varsayılan) | Whisper `large-v3-turbo` |
| Yüksek | Turbo; Qwen3-ASR sonra eklenecek |
| Maksimum | Whisper `large-v3` |

Konuşmacı ayrımı dil bağımsızdır (sherpa-onnx + TitaNet). Hugging Face jetonu gerekmez.

## Gizlilik

- STT buluta gitmez
- İndirmeler yalnızca siz onayladıktan sonra Hugging Face / GitHub’dan gelir
- Telemetri yok

Tasarım belgesi: [`docs/design.md`](docs/design.md)

## Lisans

Uygulama kodu: [MIT](LICENSE). Üçüncü taraf: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
