# تقرير المشروع — Sky Scraper
**آخر تحديث:** مايو 2026

---

## أولاً — ما تم إنجازه ✅

### 1. النورمالايزر (Normalizer)
- يقرأ من `car_models_FULL.json` (75 ماركة — نفس قوائم سيارتي أون لاين)
- خريطة aliases للأسماء الإنكليزية → العربية (100+ موديل)
- تصحيح نوع الهيكل: `إس يو في` → `SUV`، `فان` → `ڤان`
- توحيد مرسيدس: `مرسيدس` → `مرسيدس بنز`
- تجريد البادئة: `Toyota Rav4` → `راف 4`
- تجريد متغيرات لكزس: `IS 300` → `IS`
- خريطة BMW: `330i` → `الفئة 3`

### 2. توحيد الأعمدة بين السكريبرات الثلاثة
جميع السكريبرات تستخدم نفس أسماء الحقول تماماً:

| الحقل الموحّد | كان في دامازل/سيريا كارز |
|---|---|
| `make` | `brand` |
| `engine_size` | `engine` |
| `exterior_color` | `color` |
| `city` | `location` |
| `chassis_number` | `vin` |
| `description_original` | `description` |
| `phone` | `contact` |
| `images_drive_links` | `images` |
| `car_url` | `url` |

### 3. ميزة --repair-data
متوفرة في الثلاثة سكريبرات:
```
python bazaralsham_scraper.py --repair-data
python damazzle_standalone.py --repair-data
python syriacars_standalone.py --repair-data
```

### 4. الرفع على sayartionline.com (WP All Import)
- الـ CSV يُولَّد بـ `generate_sayarti_csv.py`
- الصور من `images_original_links` (روابط مباشرة)
- Separator الصور: فاصلة `,`
- الحالة عند الاستيراد: **Draft** أو **Set with XPath** للـ pending
- Unique Identifier: عمود `id` (لمنع التكرار)
- الكاتب: TasnaimTest (ID 733)

### 5. مكافحة التكرار
- كل سكريبر يقرأ الـ IDs الموجودة عند البداية
- IDs فريدة per-source: `bazar_X`، `damazzle_X`، `syriacars_X`
- إيقاف السكريبر وإعادة تشغيله لا يسبب تكراراً

---

## ثانياً — نقاط قيد البحث 🔄

### 6. قاعدة الـ Model Fallback ✅
**المشكلة:** الموديلات قصيرة (أقل من 3 أحرف أو أرقام) تُكتب عربي أحياناً وهي يجب أن تبقى إنكليزي.

**القاعدة المطبّقة في `normalizer.py`:**
- أكثر من 3 أحرف → عربي (fuzzy match)
- 3 أحرف أو أقل، أو يحتوي على رقم → **ENGLISH CAPITALS** (مثال: `C63`، `X5`، `GLE`، `IS`، `K5`)
- الدالة: `_is_short_or_numeric(text)` — تُفحص بعد lookup الـ aliases وقبل الـ fuzzy match

**الحالة:** ✅ مُطبَّق في `normalizer.py`

---

### 7. ملف القيم غير المعروفة (unknown_values.json) ✅
**الفكرة:** كل مرة النورمالايزر ما يلاقي تطابق لقيمة، يحفظها في ملف JSON تلقائياً:
```json
{
  "make": ["ماهيندرا", "جيلي"],
  "model": ["كريتا", "ماكس كروز"],
  "city": ["تل كلخ", "مضايا"],
  "body_type": ["كوبيه رياضي"]
}
```
**الهدف:** مراجعة دورية وإضافة القيم الجديدة للـ aliases.

**الحقول المُتتبَّعة:** `make`, `model`, `city`, `body_type`, `exterior_color`, `interior_color`, `condition`, `fuel_type`, `transmission`, `origin`, `drive_system`

**الحالة:** ✅ مُطبَّق — الملف يُنشأ تلقائياً في `skyscraper/unknown_values.json`

---

### 8. استخراج أقسام المواصفات ✅
**الفكرة:** بعض المواقع تعطي مواصفات مفصّلة في أقسام:
- المواصفات الخارجية
- مواصفات الأمان
- مواصفات الراحة
- المواصفات التقنية

**الهدف:** حفظها في أعمدتَي `features` و`safety_features` في الشيت.

**التطبيق في `bazaralsham_scraper.py`:**
- دالة `_extract_features(soup)` — تبحث عن أقسام accordion إضافية وتفصل ميزات السلامة عن الباقي
- القيم مفصولة بـ `|`
- الأعمدة الجديدة أُضيفت لـ COLUMNS
- `_ensure_header()` صارت non-destructive — تُضيف الأعمدة الجديدة دون مسح البيانات

**الحالة:** ✅ مُطبَّق في `bazaralsham_scraper.py` — سيُملأ إذا كان الموقع يحتوي هذه الأقسام

---

### 9. إزالة العلامات المائية (dewatermark.ai)
- 10 كريدت مجانية للتجربة
- 12,000 كريدت/شهر في الخطة المدفوعة
- معدّل 2 صورة/سيارة = 6,000 سيارة/شهر

**الحالة:** تجربة أولية فقط — لم تُدمج في السكريبر بعد

---

### 10. اكتشاف الإعلانات المحذوفة
**المقترح:** إضافة وضع `--verify`:
- يمشي على كل URL محفوظة في الشيت
- يتحقق إذا الإعلان لا يزال موجوداً
- يحدّث عمود `status`:
  - `active` — لا يزال موجوداً
  - `removed` — تمت إزالته من المصدر
  - `check_later` — خطأ مؤقت

**الحالة:** لم تُطبَّق بعد

---

### 11. منظومة إنشاء المستخدمين على sayartionline.com
**المقترح:**
1. عند رفع إعلان، ابحث عن مستخدم بنفس رقم الهاتف
2. إذا موجود → استخدمه كصاحب الإعلان
3. إذا غير موجود → أنشئ حساباً جديداً تلقائياً

**الحالة:** قيد النقاش — يحتاج WordPress API أو WP All Import Pro

---

### 12. معمارية الـ Microservices
**المقترح للمستقبل:**
```
FastAPI (API Gateway)
    └── Celery (Task Queue)
            └── Redis (Broker)
            └── Scrapers (Workers)
Docker Compose (كل شي في containers)
```
**الحالة:** للمستقبل — بعد اكتمال السكريبرات الحالية

---

## ثالثاً — مواقع لم تُضَف بعد 📋

### مواقع سيارات إضافية
| الموقع | الحالة |
|---|---|
| `syriacars.net` | ✅ شغّال |
| `damazzle.com` | ✅ شغّال |
| `bazaralsham.com` | ✅ شغّال |
| `carsy.app` | 🔄 موجود كود، يحتاج مراجعة |
| `kilometrage.sy` | 🔄 موجود كود، يحتاج مراجعة |

### مواقع عقارات 🏠
| الموقع | الحالة |
|---|---|
| يحتاج تحديد المواقع المستهدفة | ⏳ لم يبدأ |

**ملاحظات للعقارات:**
- يحتاج تحديد الموقع الوجهة (مثل sayartionline للسيارات)
- الحقول مختلفة: نوع العقار، المساحة، الطابق، عدد الغرف...
- يجب بناء normalizer منفصل للعقارات
- يجب تحديد schema موحّد للأعمدة

---

## رابعاً — البنية الحالية للملفات

```
sky_scraper/
├── requirements.txt
├── skyscraper/
│   ├── bazaralsham_scraper.py      ← سكريبر بازار الشام
│   ├── damazzle_standalone.py      ← سكريبر دامازل
│   ├── syriacars_standalone.py     ← سكريبر سيريا كارز
│   ├── normalizer.py               ← توحيد القيم
│   ├── generate_sayarti_csv.py     ← توليد CSV للاستيراد
│   ├── sayarti.json                ← قوائم سيارتي (ماركات/موديلات)
│   └── scrapers/
│       ├── carsy_scraper.py
│       ├── damazzle_scraper.py
│       ├── kilometrage_scraper.py
│       ├── syriacar_scraper.py
│       └── parser.py
```

**ملفات خارج GitHub (حساسة — تُنسخ يدوياً):**
- `oauth_token.json`
- `client_secret_*.json`
- `credentials.json`
- `imageuploader-*.json`
- `C:\Users\Tasnaim\Downloads\car_models_FULL.json`
