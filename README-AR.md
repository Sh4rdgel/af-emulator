# Assault Fire Server Emulator

**اللغة:** [English](README.md) | **العربية** | [لغات أخرى](README-LANGUAGES.md)

مشروع غير رسمي لحفظ ومحاكاة خادم **Assault Fire PH**.

الهدف هو جعل عميل PH المتوقف قابلاً للاستخدام مرة أخرى داخل بيئة محلية/معزولة لأغراض الحفظ، وأبحاث التوافق، والاختبار، والحنين.

> **العميل المدعوم: Assault Fire PH v1.0.0.24 فقط.**
>
> قد تستخدم الإصدارات الأخرى ملفات binary أو hashes أو packet layouts أو سلوك TCLS أو offsets مختلفة، وهي غير مدعومة حالياً.

---

# ⚠️ مهم — قبل الضغط على START

للحصول على أكثر عملية تشغيل أولى استقراراً، استخدم أولاً **suspended TCLS launch patcher**.

**لا تضغط START** في مشغل Assault Fire الآن.

بعد إكمال الإعداد أدناه، وتشغيل emulator، وتسجيل الدخول عبر `client.exe` / TCLS، والوصول إلى شاشة **START** العادية، شغّل من repository root:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tcls_suspended_launch.py
```

انتظر حتى يظهر:

```text
TCLS ARMED
Click START in the Assault Fire launcher now.
```

**بعد ذلك فقط اضغط START.**

يقوم الـ helper تلقائياً بتنفيذ تسلسل التشغيل الصحيح:

```text
TCLS creates TGame.exe suspended
        ↓
TCLS finishes the shared-memory handoff
        ↓
required TGame datetime compatibility patch is applied
        ↓
TGame.exe is resumed
```

يساعد ذلك في تجنب crash معروف عند بدء TGame القديم قبل تفعيل compatibility patch.

> عند استخدام `patch_tcls_suspended_launch.py`، **لا تشغّل `patch_tgame_datetime.py` أيضاً في نفس التشغيل**. الـ suspended-launch helper يطبق datetime patch تلقائياً.

إذا ظهر **TGame build/signature mismatch** فتوقف ولا تجبر patch. حالياً يتم دعم/اختبار Assault Fire PH **v1.0.0.24 فقط**.

---

# ابدأ من هنا

إذا كانت هذه أول مرة تستخدم فيها المشروع، فاتبع الخطوات **بالترتيب**.

إذا ظهرت **FAILED** في أي خطوة، أصلح المشكلة أولاً قبل المتابعة.

## المتطلبات

- Windows 10/11
- Python 3.12
- Git
- نسختك الخاصة من Assault Fire PH **v1.0.0.24**
- هذا repository

لا يحتوي repository على عميل اللعبة الأصلي أو الخرائط أو packages أو executables أو ملفات اللعبة proprietary الأخرى.

## اعرف المجلدين المهمين

### مجلد repository

شغّل الأوامر من المجلد الذي يحتوي على:

```text
af-emulator
├─ server
├─ tools
├─ docs
├─ tests
└─ README.md
```

يجب أن يبدو PowerShell تقريباً هكذا:

```text
PS D:\Something\af-emulator>
```

**لا تشغّل الأوامر من داخل `server\`.**

### Game root

`<game-root>` يعني مجلد تثبيت Assault Fire PH.

مثال:

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

**لا تكتب `<game-root>` حرفياً. استبدله بالمسار الحقيقي.**

---

# البدء السريع

## 1. تنزيل emulator

```powershell
git clone https://github.com/armangido/af-emulator.git
cd af-emulator
```

## 2. إنشاء بيئة Python

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. إنشاء زوج RSA محلي

```powershell
.\.venv\Scripts\python.exe .\tools\setup\generate_local_rsa_keypair.py --client-config-dir "<game-root>\TCLS\config"
```

سيتم إنشاء:

```text
server\PRIVATE.PEM
<game-root>\TCLS\config\APClient.dat
```

> **لا ترفع أو تعمل commit لملف `server\PRIVATE.PEM` أبداً.**

## 4. فحص TCLS و APClient.dat

```powershell
.\.venv\Scripts\python.exe .\tools\patches\diagnose_tcls_apclient.py --client-root "<game-root>"
```

يجب أن ترى:

```text
class              : validated raw-PEM-compatible PH TCLS build
exact byte match   : YES
same RSA key       : YES
```

إذا ظهر SHA256 الأصلي:

```text
13EAD403452E0F25CF00658369BF4BF5FF34ED1B16027F7833FB27D398386CD1
```

أغلق `client.exe` و TCLS بالكامل ثم شغّل:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tcls_apclient_raw_pem.py "<game-root>\TCLS\Tenio\TCLS.dll" --apply
```

SHA256 للنسخة patched الموثقة:

```text
3FF351E0ADB594D7544E28DB2E966A6D6EB548E9DF70DAAF4DAF58F2EE438D56
```

ثم أعد تشغيل diagnostic.

## 5. تحويل خدمات PH القديمة إلى localhost

افتح **PowerShell كمسؤول**:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\setup\setup_assaultfire_hosts.ps1
```

المطلوب:

```text
127.0.0.1 tversion.levelupgames.ph
127.0.0.1 tauthproxy.levelupgames.ph
127.0.0.1 tdir.levelupgames.ph
```

## 6. تشغيل emulator

```powershell
$env:AF_CLIENT_ROOT = "<game-root>"
.\.venv\Scripts\python.exe .\server\assaultfire_server_v143b.py
```

يجب أن يحتوي preflight الصحيح على:

```text
[PREFLIGHT] TCLS validated build    : YES
[PREFLIGHT] APClient exact bytes    : YES
[PREFLIGHT] same RSA key            : YES
[PREFLIGHT] hosts tversion.levelupgames.ph    : YES
[PREFLIGHT] hosts tauthproxy.levelupgames.ph  : YES
[PREFLIGHT] hosts tdir.levelupgames.ph        : YES
[PREFLIGHT] PASS - all required checks succeeded.
```

إذا ظهرت **FAILED**، لا تستمر في تشغيل client. أصلح السطر الفاشل أولاً.

---

# PvE

```powershell
$env:AF_CLIENT_ROOT = "<game-root>"
$env:AF_GAME_DIR = "<game-root>\Binaries\Win32"
$env:AF_DS_SPAWNER_ENABLED = "1"

.\.venv\Scripts\python.exe .\server\assaultfire_server_v143b.py
```

يجب أن يشير `AF_GAME_DIR` إلى مجلد `Binaries\Win32` الحقيقي.

---

# تشغيل Assault Fire PH

استخدم **خياراً واحداً فقط**.

## الخيار A — normal TCLS

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tgame_datetime.py
```

## الخيار B — suspended TCLS handoff

سجّل الدخول في TCLS وتوقف عند شاشة **START**، ثم:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tcls_suspended_launch.py
```

**لا تستخدم الـ helperين في نفس التشغيل.**

---

# مشاكل شائعة

- `.venv python is not recognized` → ارجع إلى repository root.
- `AP client initialization failed.` → أعد تشغيل diagnostic.
- لا يصل إلى AUTH → يجب أن تكون فحوص TCLS/RSA/hosts كلها **YES**.
- لا تكتب `<game-root>` حرفياً.
- الإصدارات غير **v1.0.0.24** غير مدعومة.

---

# ملاحظة حول security driver القديم

يحتوي عميل PH الأصلي على مكون kernel security/anti-cheat قديم قد يفشل على Windows الحديث قبل الوصول إلى emulator.

لا يقدم هذا المشروع تعليمات bypass أو تعطيل أو تعديل kernel أو تجاوز أنظمة security الفعالة.

راجع [Vital Setup Notes](docs/VITAL_SETUP_NOTES.md).

# التوثيق

- [Getting Started](docs/GETTING_STARTED.md)
- [Project Status](docs/STATUS.md)
- [PvE Runtime](docs/PVE_RUNTIME.md)
- [Launcher Errors](docs/LAUNCHER_ERRORS.md)
- [FAQ](docs/FAQ.md)

لا ترفع `PRIVATE.PEM` أو كلمات المرور أو بيانات الحساب أو ملفات binary proprietary الخاصة باللعبة.

# License

الكود والتوثيق الأصليان يستخدمان [MIT License](LICENSE).
