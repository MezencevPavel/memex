# PROJECT.md — Личная база знаний «Мои заметки»

> Техническая документация проекта: архитектура, стек, структура, эксплуатация.

---

## 1. Что это

**«Мои заметки»** — персональный веб-сервис для хранения учебных и рабочих заметок с авторизацией, деревом категорий неограниченной вложенности, глоссарием терминов, сниппетами и быстрым поиском. Однопользовательский. Регистрация отключена.

**Ключевые сущности:**

| Сущность | Для чего | Раздел |
|---|---|---|
| **Заметка** | Длинные статьи, шпаргалки, инструкции | `/notes` |
| **Категория** | Дерево для структуры заметок | `/categories` |
| **Термин** | Глоссарий: слова, определения | `/glossary` |
| **Сниппет** | Короткие команды для копирования в один клик | `/snippets` |

**Ключевые возможности:**

- **Дерево категорий неограниченной вложенности.**
- **Заметки в Markdown** с живым предпросмотром, датами и сортировкой.
- **Страница «Все заметки»** с фильтрами (категория, поиск, сортировка).
- **Импорт/экспорт заметок в `.md`** — пишешь локально, загружаешь в приложение.
- **Глоссарий и сниппеты с темами** (Python, PowerShell, Docker...). Свободный ввод темы + автодополнение.
- **Импорт/экспорт глоссария и сниппетов** в JSON, Markdown, CSV — и вставкой, и файлом.
- **Ссылки между заметками** `[[Название]]` и терминами `{{термин}}`.
- **Быстрый поиск по глоссарию** прямо из заметки (с фильтром по теме).
- **Быстрый поиск по сниппетам** из заметки (с фильтром по теме).
- **Быстрый переключатель заметок** сверху (← назад, поле поиска, ▼ список).
- **TOC (оглавление)** из заголовков, «Рядом в категории», «Недавние».
- **Избранное** (закреплённые заметки).
- **Кнопка «Копировать»** на блоках кода и сниппетах.
- **Импорт категорий из JSON.**
- **HTTPS + systemd + Fail2ban + автобэкап.**

---

## 2. Где хостится

| Параметр | Значение |
|---|---|
| Провайдер | VDSina |
| IP | 84.54.47.135 |
| Домен | v3270506.hosted-by-vdsina.ru |
| Тариф | 1 ядро, 1 ГБ RAM, 10 ГБ NVMe |
| ОС | Ubuntu 24.04 |
| HTTPS | Let's Encrypt через Certbot |
| SSH | порт 22, root |
| Панель | https://vdsina.ru |

**Пароли — храню локально. В этом документе их нет.**

---

## 3. Стек

| Слой | Технология |
|---|---|
| Язык | Python 3.12 |
| Веб-фреймворк | Flask |
| ORM | Flask-SQLAlchemy |
| Аутентификация | Flask-Login + Werkzeug |
| БД | SQLite (`instance/notes.db`) |
| WSGI | Gunicorn |
| Reverse proxy | Nginx |
| Markdown (сервер) | Python-Markdown |
| Markdown (клиент) | marked.js (локально) |
| CSS | Bootstrap 5 + Icons (CDN) |
| JS (dropdown и др.) | Bootstrap 5 bundle (CDN) |
| Процесс-менеджер | systemd |
| Защита SSH | Fail2ban |
| Бэкап | bash + cron |

---

## 4. Структура файлов

```
/root/myservice/
├── app.py
├── PROJECT.md
├── instance/notes.db
├── static/js/marked.min.js
├── templates/
│   ├── base.html                    ← сайдбар + Bootstrap JS
│   ├── login.html
│   ├── index.html                   ← Недавние + Избранное + Категории
│   ├── all_notes.html               ← Все заметки + кнопка «Импорт .md»
│   ├── notes_import_md.html         ← форма импорта .md
│   ├── category.html                ← дерево-аккордеон + правая колонка
│   ├── note.html                    ← просмотр + поиск по глоссарию/сниппетам
│   ├── edit.html                    ← редактор + кнопки .md
│   ├── search.html
│   ├── categories.html              ← дерево с замочком + правая колонка
│   ├── categories_import.html       ← импорт JSON (файл/текст)
│   ├── glossary.html                ← табы тем + термины
│   ├── glossary_import.html         ← импорт (файл/текст)
│   ├── snippets.html                ← табы тем + карточки
│   ├── snippet_edit.html            ← форма с темой
│   ├── snippets_import.html         ← импорт (файл/текст)
│   └── about.html                   ← рендер PROJECT.md
└── venv/
```

**Бэкапы:** `/root/backups/notes-backup-YYYY-MM-DD_HH-MM.tar.gz` (7 последних).

---

## 5. Модели БД

### User
- `id`, `username` (unique), `password_hash`

### Category
- `id`, `name`, `user_id` (FK User), `parent_id` (FK Category, NULL = корневая)
- Вложенность неограниченная.
- `cascade='all, delete-orphan'` — удаление сносит детей и заметки.

### Note
- `id`, `title`, `content` (Markdown), `user_id`, `category_id`, `is_pinned`
- `created_at`, `updated_at` (UTC)

### GlossaryTerm
- `id`, `term`, `definition` (Markdown), **`topic`** (Python, Docker...), `user_id`

### Snippet
- `id`, `name`, `command`, `description`, **`topic`**, `user_id`
- `created_at`, `updated_at`

---

## 6. Маршруты

| URL | Метод | Что делает |
|---|---|---|
| `/` | GET | Главная: Недавние + Избранное + Категории |
| `/notes` | GET | Все заметки (фильтры: `q`, `cat`, `sort`) |
| `/notes/import.md` | GET/POST | Импорт заметок из `.md` |
| `/note/<id>` | GET | Просмотр заметки |
| `/note/<id>/export.md` | GET | Скачать заметку как `.md` |
| `/add`, `/add/<cat_id>` | GET/POST | Новая заметка |
| `/edit/<id>` | GET/POST | Редактировать |
| `/move/<id>` | POST | Переместить заметку |
| `/pin/<id>` | GET | Избранное |
| `/delete/<id>` | GET | Удалить |
| `/search` | GET | Поиск по заметкам |
| `/categories` | GET | Управление категориями |
| `/categories/import` | GET/POST | Импорт дерева из JSON |
| `/category/add` | POST | Создать категорию |
| `/category/rename/<id>` | POST | Переименовать |
| `/category/delete/<id>` | GET | Удалить |
| `/category/<id>` | GET | Заметки + дерево категории |
| `/glossary` | GET | Глоссарий |
| `/glossary/add` / `edit` / `delete` | POST/GET | CRUD терминов |
| `/glossary/import` | GET/POST | Импорт (JSON/MD/CSV) |
| `/glossary/export.<fmt>` | GET | Экспорт JSON/MD/CSV |
| `/snippets` | GET | Сниппеты |
| `/snippets/add` / `edit` / `delete` | GET/POST | CRUD сниппетов |
| `/snippets/import` | GET/POST | Импорт (JSON/MD/CSV) |
| `/snippets/export.<fmt>` | GET | Экспорт JSON/MD/CSV |
| `/about` | GET | Рендер PROJECT.md |
| `/login` / `/logout` | GET/POST | Вход/выход |
| `/api/glossary/search` | GET | JSON-поиск (по началу термина, фильтр `topic`) |
| `/api/categories/search` | GET | JSON-поиск категорий |
| `/api/notes/search` | GET | JSON-поиск заметок |

---

## 7. Синтаксис в заметках

### Ссылки между заметками: `[[Название]]`
- Есть → синяя ссылка.
- Нет → красная, клик создаёт новую с предзаполненным заголовком.

### Термины глоссария: `{{термин}}`
- Есть → пурпурный пунктир + tooltip.
- Нет → красный пунктир.

---

## 8. Импорт / экспорт

### Заметки
- **Экспорт одной заметки:** кнопка «📥 .md» на странице просмотра и в редакторе. Имя файла = `заголовок.md` (slug).
- **Импорт `.md` → новая заметка:** кнопка «📤 .md» в редакторе (без выбора категории).
- **Пакетный импорт `.md`:** страница `/notes/import.md` (со страницы «Все заметки»). Заголовок = имя файла. Можно выбрать категорию.

### Глоссарий / Сниппеты
- **Экспорт:** JSON / Markdown / CSV (dropdown «Экспорт»).
- **Импорт:** через `input type="file"` или вставкой текста. Формат определяется автоматически.
- **Тема:** указывается у каждого элемента или берётся «Тема по умолчанию».
- **Дубликаты** (по названию + теме) обновляются, если данные отличаются.

### Категории
- **Только JSON.** Вложенность через `children`. Дубликаты по имени+родителю пропускаются.

---

## 9. Управление сервисом

```bash
systemctl status myservice
systemctl restart myservice    # после правок app.py или шаблонов
systemctl stop myservice
systemctl start myservice
journalctl -u myservice -n 50
```

### Конфиги
```
/etc/nginx/sites-available/myservice
/etc/systemd/system/myservice.service
/etc/fail2ban/jail.local
/root/backup-notes.sh
/var/log/notes-backup.log
```

### Nginx / сертификат
```bash
nginx -t
systemctl reload nginx
certbot renew --dry-run
```

### Fail2ban
```bash
fail2ban-client status sshd
fail2ban-client set sshd unbanip 1.2.3.4
```

---

## 10. Развёртывание с нуля

1. **VPS** (Ubuntu 24.04, 1 ГБ RAM).
2. **SSH:**
   ```bash
   ssh root@IP
   ```
3. **Пакеты:**
   ```bash
   apt update && apt upgrade -y
   apt install -y python3 python3-pip python3-venv nginx fail2ban certbot python3-certbot-nginx sqlite3
   ```
4. **Проект:**
   ```bash
   mkdir -p ~/myservice/static/js ~/myservice/templates
   cd ~/myservice
   python3 -m venv venv
   source venv/bin/activate
   pip install flask flask-sqlalchemy flask-login werkzeug markdown gunicorn
   curl -o static/js/marked.min.js https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js
   ```
5. **Восстановить `app.py`, `PROJECT.md`, шаблоны.**
6. **systemd** — `/etc/systemd/system/myservice.service`:
   ```ini
   [Unit]
   Description=My Flask Notes Service
   After=network.target

   [Service]
   User=root
   WorkingDirectory=/root/myservice
   Environment="ADMIN_PASSWORD=ваш-пароль"
   ExecStart=/root/myservice/venv/bin/gunicorn --bind 127.0.0.1:8000 app:app
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=multi-user.target
   ```
   ```bash
   systemctl daemon-reload
   systemctl enable --now myservice
   ```
7. **Nginx:**
   ```nginx
   server {
       listen 80;
       server_name v3270506.hosted-by-vdsina.ru;
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```
   ```bash
   ln -s /etc/nginx/sites-available/myservice /etc/nginx/sites-enabled/
   rm /etc/nginx/sites-enabled/default
   nginx -t && systemctl restart nginx
   ```
8. **HTTPS:**
   ```bash
   certbot --nginx -d v3270506.hosted-by-vdsina.ru
   ```
9. **Fail2ban** (см. раздел 11).
10. **Бэкап** (см. раздел 12).

### Миграции БД
```bash
sqlite3 ~/myservice/instance/notes.db "ALTER TABLE note ADD COLUMN created_at DATETIME;"
sqlite3 ~/myservice/instance/notes.db "ALTER TABLE note ADD COLUMN updated_at DATETIME;"
sqlite3 ~/myservice/instance/notes.db "ALTER TABLE glossary_term ADD COLUMN topic VARCHAR(100);"
sqlite3 ~/myservice/instance/notes.db "ALTER TABLE snippet ADD COLUMN topic VARCHAR(100);"
```

---

## 11. Безопасность

### SSH
- Порт 22, root по паролю.
- **Fail2ban** в `/etc/fail2ban/jail.local`:
  ```ini
  [DEFAULT]
  bantime = 1h
  findtime = 10m
  maxretry = 5

  [sshd]
  enabled = true
  port = ssh
  logpath = /var/log/auth.log
  maxretry = 5
  bantime = 1h
  ```

### HTTPS
- Let's Encrypt, автопродление systemd-таймером.
- Проверка: `certbot renew --dry-run`.

### Приложение
- Один пользователь `admin`.
- Пароль — **из переменной `ADMIN_PASSWORD`** в systemd-юните (при создании новой базы).
- Существующая база не пересоздаётся.

### Смена пароля admin
```bash
cd ~/myservice && source venv/bin/activate && python3
```
```python
from app import app, db, User
from werkzeug.security import generate_password_hash
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    admin.password_hash = generate_password_hash('НОВЫЙ_ПАРОЛЬ')
    db.session.commit()
    print("OK")
exit()
```

---

## 12. Бэкап

Скрипт `/root/backup-notes.sh`:
- Архивирует `instance/notes.db` + `static/`.
- Складывает в `/root/backups/notes-backup-YYYY-MM-DD_HH-MM.tar.gz`.
- Удаляет архивы старше 7 дней.
- Лог: `/var/log/notes-backup.log`.

**Cron:** `crontab -e` → `0 3 * * * /root/backup-notes.sh`.

**Восстановление:**
```bash
systemctl stop myservice
cd ~/myservice
tar -xzf /root/backups/notes-backup-XXXX.tar.gz
systemctl start myservice
```

**Скачать на комп:**
```powershell
scp root@84.54.47.135:/root/backups/notes-backup-XXXX.tar.gz C:\Users\Ты\Desktop\
```

---

## 13. Сделано ✅ и в планах 📋

### Сделано
- [x] Авторизация
- [x] Дерево категорий неограниченной вложенности
- [x] Переименование с замочком (readonly + кнопка ✏️)
- [x] Заметки в Markdown + живой предпросмотр
- [x] Даты создания/изменения + сортировка
- [x] Страница «Все заметки» с фильтрами
- [x] Импорт заметок из `.md` (одна / пакетно)
- [x] Экспорт заметки в `.md` (просмотр + редактор)
- [x] Ссылки между заметками `[[...]]`
- [x] Глоссарий с темами (Python, Docker...) + `{{...}}` tooltip
- [x] Сниппеты с темами + копирование в один клик
- [x] Быстрый поиск по глоссарию из заметки (с фильтром темы)
- [x] Быстрый поиск по сниппетам из заметки (с фильтром темы)
- [x] Быстрый переключатель заметок (← / поле / ▼)
- [x] TOC + «Рядом в категории» + «Недавние»
- [x] Импорт/экспорт глоссария: JSON / MD / CSV (файл + текст)
- [x] Импорт/экспорт сниппетов: JSON / MD / CSV (файл + текст)
- [x] Импорт категорий из JSON
- [x] HTTPS + systemd + Fail2ban + автобэкап

### В планах
- [ ] Массовый экспорт всех заметок в `.zip`
- [ ] Прикреплённые файлы
- [ ] Тёмная тема
- [ ] История версий заметок
- [ ] Теги (в дополнение к категориям)

---

## 14. Известные грабли

1. **Jinja-макросы объявлять ДО вызова.**
2. **`position: sticky` не работает внутри flex с overflow.**
3. **SQLite `LIKE`/`ILIKE` регистрозависим для кириллицы.** Поиск делаем **в Python** (`filter_ci`).
4. **SQLite не мигрирует автоматически** — `ALTER TABLE`.
5. **Flask + Gunicorn не подхватывает правки на лету** — `systemctl restart myservice`.
6. **Bootstrap JS обязателен** для dropdown'ов. Подключён в `base.html` через `bootstrap.bundle.min.js`.
7. **`marked.js` локально** — иначе предпросмотр может отвалиться.
8. **VS Code Remote SSH жрёт 300–500 МБ RAM.** При 1 ГБ лучше PuTTY.
9. **`ADMIN_PASSWORD` в systemd** — только для новых баз. Существующая не перезаписывается.
10. **Дерево категорий в сайдбаре — только корневые** (специально).

---

## 15. Как пользоваться этим документом

**Ты:** открой `~/myservice/PROJECT.md` или локальную копию.

**Обновление документации:** при значительных изменениях архитектуры дополняй этот файл, чтобы документация оставалась актуальной.

**Если сервер сдох:**
1. Локальная копия `PROJECT.md`.
2. Локальная копия `app.py` и шаблонов.
3. Бэкапы в `/root/backups/` — **качай иногда на комп**.

---

*Обновление: добавлены темы, сниппеты, .md-импорт/экспорт, замочек категорий, файловый импорт.*
