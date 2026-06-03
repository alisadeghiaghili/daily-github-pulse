<div dir="rtl">

# daily-github-pulse

> هر روز بدونید روی GitHub چه داره می‌جوشه.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![Tests](https://github.com/alisadeghiaghili/daily-github-pulse/actions/workflows/tests.yml/badge.svg)](https://github.com/alisadeghiaghili/daily-github-pulse/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Contributing](https://img.shields.io/badge/contributions-welcome-brightgreen)](CONTRIBUTING.md)

[English](README.en.md) | [Deutsch](README.de.md)

---

GitHub هر روز هزاران repo جدید داره. پیدا کردن اون‌هایی که **واقعاً** دارن رشد می‌کنن — نه فقط ستاره‌های تاریخی — وقت‌گیره.

`daily-github-pulse` این کار رو به یه دستور ساده تبدیل می‌کنه:

```bash
python github_repo_of_the_day.py
```

خروجی: repo‌هایی که **امروز** بیشترین سرعت ستاره‌گیری داشتن، به همراه نرخ رشد روزانه — نه فقط تعداد کل ستاره.

```
======================================================================
#1  openai/openai-python
    Stars: 24,312  Forks: 3,201  Lang: Python
  Δ +418 ⭐ total  |  ~418.0 ⭐/day
    https://github.com/openai/openai-python
```

---

## شروع سریع

```bash
git clone https://github.com/alisadeghiaghili/daily-github-pulse.git
cd daily-github-pulse
pip install -r requirements.txt

# توصیه می‌شه: توکن GitHub اضافه کن (۵۰۰۰ درخواست/ساعت)
cp .env.example .env
# GITHUB_TOKEN=ghp_... را در .env ست کن

python github_repo_of_the_day.py
```

همین. نیازی به تنظیمات پیچیده‌ای نیست.

---

## چند مثال واقعی

```bash
# repo‌های Python این هفته
python github_repo_of_the_day.py -l python -p week

# دنبال ابزارهای LLM و agent می‌گردی؟
python github_repo_of_the_day.py --bool-query '(LLM OR GPT) AND agent AND NOT benchmark'

# wildcard: analy?e → analyse OR analyze
python github_repo_of_the_day.py --keywords "analy?e" --wildcard

# توسعه‌دهنده‌های در حال رشد
python github_repo_of_the_day.py --developers -l python

# خروجی CSV
python github_repo_of_the_day.py -l go -o csv -f results.csv

# فیلتر هوشمند با هوش مصنوعی
python github_repo_of_the_day.py --keywords LLM --ai-filter --ai-filter-query "inference server آماده production"
```

---

## چرا این ابزار؟

| مشکل | راه‌حل |
|---|---|
| GitHub trending فقط تعداد کل ستاره نشون می‌ده | **Star velocity** — نرخ واقعی رشد امروز (`⭐/day`) |
| جستجو یا هست یا نیست، بدون منطق | **Boolean search** کامل: `(LLM OR GPT) AND agent AND NOT survey` |
| `analyz*` رو باید دستی expand کنی | **Wildcard expansion** با NLTK: `analy?e` → `analyse OR analyze` |
| نتایج پر از paper و survey هست | **AI filter** — به زبان طبیعی بگو دنبال چی هستی |
| هر بار از صفر شروع می‌کنی | **Snapshot** — delta ستاره نسبت به آخرین اجرا |

---

## امکانات

<details>
<summary>همه فلگ‌ها</summary>

| دسته | فلگ | توضیح |
|---|---|---|
| حالت | `--developers` | توسعه‌دهنده‌های trending به جای repo |
| فیلتر | `-l python` | زبان برنامه‌نویسی |
| فیلتر | `-p week` | بازه زمانی: `day` / `week` / `month` |
| فیلتر | `-n 20` | تعداد نتایج (پیش‌فرض: ۱۰) |
| جستجو | `--keyword TERM` | یک کلیدواژه (legacy) |
| جستجو | `--keywords A B` | چند کلیدواژه با عملگر |
| جستجو | `--keyword-op AND\|OR` | عملگر ترکیب کلیدواژه‌ها |
| جستجو | `--keyword-not A B` | حذف کلیدواژه‌ها |
| جستجو | `--bool-query 'EXPR'` | عبارت boolean کامل |
| جستجو | `--search-in name,description,readme` | محدوده جستجو |
| جستجو | `--wildcard` | wildcard با NLTK |
| خروجی | `-o json\|csv` | فرمت خروجی |
| خروجی | `-f results.csv` | ذخیره در فایل |
| snapshot | `--no-snapshot` | غیرفعال کردن velocity |
| snapshot | `--clear-snapshots` | پاک کردن تاریخچه |
| AI | `--ai-filter` | فعال‌سازی فیلتر LLM |
| AI | `--ai-filter-query "QUERY"` | توضیح هدف به زبان طبیعی |
| AI | `--ai-filter-fallback passthrough` | رفتار وقتی LLM در دسترس نیست |
| احراز هویت | `--token TOKEN` | توکن GitHub (جایگزین .env) |

</details>

---

## Star Velocity چطور کار می‌کنه؟

هر بار که ابزار اجرا می‌شه، تعداد ستاره‌ها در `~/.daily-github-pulse/snapshots.json` ذخیره می‌شه. دفعه بعد دو عدد نشون داده می‌شه:

- **Δ raw** — کل ستاره‌های گرفته‌شده از آخرین snapshot
- **~N ⭐/day** — نرخ روزانه time-normalized (حتی بعد از چند هفته هم معنادار می‌مونه)

```bash
# snapshot این اجرا رو ذخیره نکن
python github_repo_of_the_day.py --no-snapshot

# همه snapshot‌ها رو پاک کن
python github_repo_of_the_day.py --clear-snapshots
```

---

## AI Filter — تنظیم backend

از هر LLM سازگار با OpenAI API پشتیبانی می‌کنه:

```env
# OpenAI (پیش‌فرض)
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
AI_API_KEY=sk-...

# Ollama محلی
AI_BASE_URL=http://localhost:11434/v1
AI_MODEL=llama3.2
AI_API_KEY=ollama

# Claude (Anthropic)
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5
```

| `--ai-filter-fallback` | رفتار وقتی LLM در دسترس نیست |
|---|---|
| `fail` (پیش‌فرض) | خروج با خطا |
| `passthrough` | هشدار + نمایش همه نتایج بدون فیلتر |

---

## محدودیت نرخ GitHub

| حالت | محدودیت |
|---|---|
| بدون توکن | ۶۰ درخواست/ساعت |
| با توکن | ۵۰۰۰ درخواست/ساعت |

دریافت توکن: [github.com/settings/tokens](https://github.com/settings/tokens)

---

## تست‌ها

```bash
pip install pytest
pytest tests/ -v
```

۱۳۶ تست، بدون نیاز به اینترنت (GitHub API کاملاً mock شده).

---

## مشارکت

راهنمای کامل در [CONTRIBUTING.md](CONTRIBUTING.md)

---

## لایسنس

[MIT](LICENSE)

</div>
