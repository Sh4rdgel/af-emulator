# Assault Fire Server Emulator

**Bahasa:** [English](README.md) | **Bahasa Indonesia** | [Bahasa lain](README-LANGUAGES.md)

Proyek tidak resmi untuk preservasi dan emulasi server **Assault Fire PH**.

Tujuannya adalah membuat klien PH yang sudah berhenti beroperasi dapat digunakan kembali di lingkungan lokal/terisolasi untuk preservasi, riset interoperabilitas, pengujian, dan nostalgia.

> **Klien yang didukung: hanya Assault Fire PH v1.0.0.24.**
>
> Versi lain mungkin memiliki binary, hash, packet layout, perilaku TCLS, atau offset yang berbeda dan saat ini belum didukung.

---

# Mulai dari sini

Jika ini pertama kali Anda menggunakan proyek ini, ikuti langkah di bawah **secara berurutan**.

Jika suatu langkah menunjukkan **FAILED**, perbaiki masalah tersebut terlebih dahulu. Jangan lanjut sebelum langkah itu berhasil.

## Yang Anda perlukan

- Windows 10/11
- Python 3.12
- Git
- instalasi Assault Fire PH **v1.0.0.24** milik Anda sendiri
- repository ini

Repository ini **tidak menyertakan** klien game asli, map, package, executable, atau file game proprietary lainnya.

## Kenali dua folder penting

### Folder repository

Jalankan command repository dari folder yang berisi:

```text
af-emulator
├─ server
├─ tools
├─ docs
├─ tests
└─ README.md
```

Prompt PowerShell seharusnya mirip:

```text
PS D:\Something\af-emulator>
```

**Jangan jalankan command dari dalam folder `server\`.**

### Game root

`<game-root>` berarti folder instalasi Assault Fire PH Anda.

Contoh:

```text
D:\AssaultFirePH
├─ TCLS
│  ├─ Tenio
│  │  └─ TCLS.dll
│  └─ config
│     └─ APClient.dat
└─ Binaries
   └─ Win32
```

Jadi:

```text
<game-root> = D:\AssaultFirePH
```

**Jangan mengetik `<game-root>` secara literal. Ganti dengan folder game Anda yang sebenarnya.**

---

# Quick start

## 1. Download emulator

```powershell
git clone https://github.com/armangido/af-emulator.git
cd af-emulator
```

## 2. Buat environment Python

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

File berikut harus ada:

```text
.venv\Scripts\python.exe
```

Jika PowerShell mengatakan file tersebut tidak dikenali, biasanya Anda berada di folder yang salah.

## 3. Buat pasangan RSA lokal

```powershell
.\.venv\Scripts\python.exe .\tools\setup\generate_local_rsa_keypair.py --client-config-dir "<game-root>\TCLS\config"
```

Contoh:

```powershell
.\.venv\Scripts\python.exe .\tools\setup\generate_local_rsa_keypair.py --client-config-dir "D:\AssaultFirePH\TCLS\config"
```

Ini membuat:

```text
server\PRIVATE.PEM
<game-root>\TCLS\config\APClient.dat
```

> **Jangan pernah upload atau commit `server\PRIVATE.PEM`.**

## 4. Verifikasi TCLS dan APClient.dat

```powershell
.\.venv\Scripts\python.exe .\tools\patches\diagnose_tcls_apclient.py --client-root "<game-root>"
```

Anda ingin melihat:

```text
class              : validated raw-PEM-compatible PH TCLS build
exact byte match   : YES
same RSA key       : YES
```

Jika TCLS asli terdeteksi dengan SHA256:

```text
13EAD403452E0F25CF00658369BF4BF5FF34ED1B16027F7833FB27D398386CD1
```

tutup penuh `client.exe` dan TCLS, lalu jalankan:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tcls_apclient_raw_pem.py "<game-root>\TCLS\Tenio\TCLS.dll" --apply
```

Hash patched yang telah diverifikasi:

```text
3FF351E0ADB594D7544E28DB2E966A6D6EB548E9DF70DAAF4DAF58F2EE438D56
```

Jalankan diagnostic lagi. Jangan lanjut sebelum:

```text
exact byte match   : YES
same RSA key       : YES
```

## 5. Arahkan service PH lama ke localhost

Buka **PowerShell as Administrator**:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\setup\setup_assaultfire_hosts.ps1
```

Mapping yang diperlukan:

```text
127.0.0.1 tversion.levelupgames.ph
127.0.0.1 tauthproxy.levelupgames.ph
127.0.0.1 tdir.levelupgames.ph
```

## 6. Jalankan emulator

```powershell
$env:AF_CLIENT_ROOT = "<game-root>"
.\.venv\Scripts\python.exe .\server\assaultfire_server_v143b.py
```

Startup sehat harus menampilkan:

```text
[PREFLIGHT] TCLS validated build    : YES
[PREFLIGHT] APClient exact bytes    : YES
[PREFLIGHT] same RSA key            : YES
[PREFLIGHT] hosts tversion.levelupgames.ph    : YES
[PREFLIGHT] hosts tauthproxy.levelupgames.ph  : YES
[PREFLIGHT] hosts tdir.levelupgames.ph        : YES
[PREFLIGHT] PASS - all required checks succeeded.
```

Jika preflight **FAILED**, jangan terus meluncurkan client. Perbaiki baris yang gagal terlebih dahulu.

---

# PvE

Sebelum menjalankan v143b:

```powershell
$env:AF_CLIENT_ROOT = "<game-root>"
$env:AF_GAME_DIR = "<game-root>\Binaries\Win32"
$env:AF_DS_SPAWNER_ENABLED = "1"

.\.venv\Scripts\python.exe .\server\assaultfire_server_v143b.py
```

Arahkan `AF_GAME_DIR` ke folder `Binaries\Win32` yang benar milik Anda.

---

# Menjalankan Assault Fire PH

Gunakan **satu** metode saja.

## Opsi A — normal TCLS

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tgame_datetime.py
```

Kemudian jalankan melalui `client.exe` / TCLS.

## Opsi B — suspended TCLS handoff

Login ke TCLS dan berhenti di layar **START**, lalu:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tcls_suspended_launch.py
```

**Jangan gunakan kedua helper untuk launch yang sama.**

---

# Kesalahan umum

- `.venv python is not recognized` → kembali ke root repository.
- `AP client initialization failed.` → ulangi diagnostic TCLS/APClient.
- Tidak mencapai AUTH → pastikan TCLS, exact byte match, RSA key, dan hosts semuanya **YES**.
- Jangan menyalin `<game-root>` secara literal.
- Versi selain **v1.0.0.24** belum didukung.

---

# Catatan security driver lama

Klien PH asli memiliki komponen security/anti-cheat kernel lama yang dibuat untuk Windows versi lama.

Pada Windows modern, komponen tersebut dapat gagal sebelum emulator dihubungi.

Proyek ini tidak menyediakan instruksi bypass, disable, modifikasi kernel, atau pengelakan security aktif.

Lihat [Vital Setup Notes](docs/VITAL_SETUP_NOTES.md).

---

# Dokumentasi

- [Getting Started](docs/GETTING_STARTED.md)
- [Project Status](docs/STATUS.md)
- [PvE Runtime](docs/PVE_RUNTIME.md)
- [Launch Requirements](docs/LAUNCH_REQUIREMENTS.md)
- [Launcher Errors](docs/LAUNCHER_ERRORS.md)
- [FAQ](docs/FAQ.md)

Jangan upload `PRIVATE.PEM`, password, credential akun, atau binary game proprietary.

# License

Kode dan dokumentasi original repository ini menggunakan [MIT License](LICENSE).
