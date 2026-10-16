# PROJECT.md — Memex

> Техническая документация проекта: архитектура, стек, структура, эксплуатация.

**Версия:** `v1.0.0`

---

## 1. Что это

**Memex** — персональный веб-сервис для хранения заметок, глоссария, сниппетов, ссылок и контактов. Однопользовательский. Регистрация отключена.

Название — отсылка к концепции Ванневара Буша (1945): «устройство для расширения памяти».

**Ключевые сущности:**

| Сущность | Назначение | Раздел |
|---|---|---|
| Заметка | Длинные статьи, шпаргалки, инструкции | `/notes` |
| Категория | Дерево для структуры заметок | `/categories` |
| Термин | Глоссарий: слова и определения | `/glossary` |
| Сниппет | Короткие команды для копирования | `/snippets` |
| Ссылка | Полезные URL с описанием | `/links` |
| Контакт | Справочник номеров | `/phones` |

**Возможности:**

- Дерево категорий неограниченной вложенности.
- Заметки в Markdown с живым предпросмотром, датами и сортировкой.
- Страница «Все заметки» с фильтрами (категория, поиск, сортировка).
- Импорт и экспорт заметок в `.md`.
- Загрузка картинок с автоматическим сжатием в WebP.
- Глоссарий и сниппеты с темами (Python, PowerShell, Docker...).
- Импорт и экспорт глоссария и сниппетов в JSON, Markdown, CSV — вставкой и файлом.
- Ссылки между заметками `[[Название]]` и терминами `{{термин}}`.
- Быстрый поиск по глоссарию и сниппетам из правой панели заметки.
- Быстрый переключатель заметок (← назад, поле поиска, ▼ список).
- TOC (оглавление), «Рядом в категории», «Недавние».
- Избранное (закреплённые заметки).
- Кнопка «Копировать» на блоках кода и сниппетах.
- Импорт категорий из JSON.
- HTTPS, systemd, Fail2ban, автобэкап.

---

## 2. Стек

| Слой | Технология |
|---|---|
| Язык | Python 3.9+ |
| Веб-фреймворк | Flask |
| ORM | Flask-SQLAlchemy |
| Аутентификация | Flask-Login + Werkzeug |
| База данных | SQLite (`instance/notes.db`) |
| WSGI | Gunicorn |
| Reverse proxy | Nginx |
| Markdown (сервер) | Python-Markdown |
| Markdown (клиент) | marked.js (локально) |
| CSS | Bootstrap 5 + Icons |
| JS | Bootstrap 5 bundle |
| Изображения | Pillow (WebP) |
| Процесс-менеджер | systemd |
| Защита SSH | Fail2ban |
| Бэкап | bash + cron |

---

## 3. Структура проекта

```
/opt/memex/
├── app.py                       # всё приложение (Flask)
├── requirements.txt             # Python-зависимости
├── README.md                    # краткое описание
├── PROJECT.md                   # этот файл
├── ansible/                     # автоматическое развёртывание
│   ├── playbook.yml
│   ├── inventory.ini.example
│   └── README.md
├── instance/
│   └── notes.db                 # база данных SQLite
├── static/
│   ├── img/logo.png
│   ├── js/marked.min.js
│   └── uploads/                 # загруженные картинки (год/месяц)
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── index.html
│   ├── all_notes.html
│   ├── notes_import_md.html
│   ├── category.html
│   ├── categories.html
│   ├── categories_import.html
│   ├── note.html
│   ├── edit.html
│   ├── search.html
│   ├── glossary.html
│   ├── glossary_import.html
│   ├── snippets.html
│   ├── snippet_edit.html
│   ├── snippets_import.html
│   ├── links.html
│   ├── link_edit.html
│   ├── links_import.html
│   ├── phones.html
│   ├── phone_edit.html
│   ├── phones_import.html
│   ├── help_markdown.html
│   └── about.html
└── venv/                        # виртуальное окружение
```

---

## 4. Модели БД

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
- `id`, `term`, `definition` (Markdown), `topic`, `user_id`

### Snippet
- `id`, `name`, `command`, `description`, `topic`, `user_id`
- `created_at`, `updated_at`

### Link
- `id`, `title`, `url`, `description`, `topic`, `user_id`
- `created_at`, `updated_at`

### Phone
- `id`, `name`, `number`, `description`, `topic`, `user_id`
- `created_at`, `updated_at`

---

## 5. Маршруты

| URL | Метод | Назначение |
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
| `/links` | GET | Ссылки |
| `/links/add` / `edit` / `delete` | GET/POST | CRUD ссылок |
| `/links/import` | GET/POST | Импорт (JSON/MD/CSV) |
| `/links/export.<fmt>` | GET | Экспорт JSON/MD/CSV |
| `/phones` | GET | Контакты |
| `/phones/add` / `edit` / `delete` | GET/POST | CRUD контактов |
| `/phones/import` | GET/POST | Импорт (JSON/MD/CSV) |
| `/phones/export.<fmt>` | GET | Экспорт JSON/MD/CSV |
| `/upload/image` | POST | Загрузка картинки (сжатие в WebP) |
| `/help/markdown` | GET | Шпаргалка по Markdown |
| `/about` | GET | Рендер PROJECT.md |
| `/login`, `/logout` | GET/POST | Вход / выход |
| `/api/glossary/search` | GET | JSON-поиск терминов |
| `/api/categories/search` | GET | JSON-поиск категорий |
| `/api/notes/search` | GET | JSON-поиск заметок |
| `/api/categories/tree` | GET | Дерево категорий для модалки перемещения |
| `/api/links/search` | GET | JSON-поиск ссылок |

---

## 6. Синтаксис в заметках

### Ссылки между заметками: `[[Название]]`
- Есть — синяя ссылка.
- Нет — красная, клик создаёт новую с предзаполненным заголовком.

### Термины глоссария: `{{термин}}`
- Есть — пурпурный пунктир + tooltip.
- Нет — красный пунктир.

### Картинки
- `![alt](url)` — стандартный Markdown.
- `<img src="..." width="400">` — с явной шириной.
- Кнопка «Картинка» в редакторе или `Ctrl+V` со скриншотом.

---

## 7. Импорт и экспорт

### Заметки
- **Экспорт одной заметки:** кнопка `.md` на странице просмотра и в редакторе.
- **Импорт `.md` → новая заметка:** кнопка `.md` в редакторе.
- **Пакетный импорт `.md`:** страница `/notes/import.md`. Заголовок = имя файла, можно выбрать категорию.

### Глоссарий, сниппеты, ссылки, контакты
- **Экспорт:** JSON / Markdown / CSV.
- **Импорт:** через `input type="file"` или вставкой текста. Формат определяется автоматически.
- **Тема:** указывается у каждого элемента или берётся «Тема по умолчанию».
- **Дубликаты** (по названию и теме) обновляются, если данные отличаются.

### Категории
- **Только JSON.** Вложенность через `children`. Дубликаты по имени и родителю пропускаются.

---

## 8. Управление сервисом

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
/root/backup-memex.sh
/var/log/memex-backup.log
```

### Nginx и сертификат
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

## 9. Развёртывание с нуля

### 1. Требования

- VPS с Ubuntu 22.04 / 24.04 или CentOS Stream 9.
- 1 ГБ RAM, 10 ГБ диска.
- Root-доступ по SSH.

### 2. Системные пакеты (Ubuntu)

```bash
apt update
apt install -y python3 python3-pip python3-venv nginx fail2ban certbot python3-certbot-nginx sqlite3 git
```

### 3. Клонирование и окружение

```bash
mkdir -p /opt/memex
cd /opt/memex
git clone https://github.com/MezencevPavel/memex.git .

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Клиентский Markdown-парсер

```bash
mkdir -p static/js
curl -o static/js/marked.min.js https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js
```

### 5. systemd-юнит

`/etc/systemd/system/myservice.service`:

```ini
[Unit]
Description=Memex — Personal Knowledge Base
After=network.target

[Service]
User=root
WorkingDirectory=/opt/memex
Environment="ADMIN_PASSWORD=CHANGE_ME"
ExecStart=/opt/memex/venv/bin/gunicorn --bind 127.0.0.1:8000 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now myservice
```

### 6. Nginx

`/etc/nginx/sites-available/memex`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/memex /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
```

### 7. HTTPS

```bash
certbot --nginx -d your-domain.com
```

### Автоматическое развёртывание

См. папку `ansible/` — playbook для CentOS Stream 9.

### Миграции БД

```bash
sqlite3 /opt/memex/instance/notes.db "ALTER TABLE note ADD COLUMN created_at DATETIME;"
sqlite3 /opt/memex/instance/notes.db "ALTER TABLE note ADD COLUMN updated_at DATETIME;"
sqlite3 /opt/memex/instance/notes.db "ALTER TABLE glossary_term ADD COLUMN topic VARCHAR(100);"
sqlite3 /opt/memex/instance/notes.db "ALTER TABLE snippet ADD COLUMN topic VARCHAR(100);"
```

---

## 10. Безопасность

### SSH
- Порт 22, root по паролю.
- Fail2ban в `/etc/fail2ban/jail.local`:

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
- Пароль — из переменной `ADMIN_PASSWORD` в systemd-юните (при создании новой базы).
- Существующая база не пересоздаётся.

### Смена пароля admin

```bash
cd /opt/memex
source venv/bin/activate
python3
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

## 11. Бэкап

Скрипт `/root/backup-memex.sh`:

- Архивирует `instance/notes.db` и `static/uploads/`.
- Складывает в `/root/backups/memex-YYYY-MM-DD_HH-MM.tar.gz`.
- Хранит **5 последних** архивов.
- Лог: `/var/log/memex-backup.log`.

**Запуск вручную:**

```bash
/root/backup-memex.sh
```

**Восстановление:**

```bash
systemctl stop myservice
cd /opt/memex
tar -xzf /root/backups/memex-XXXX.tar.gz
systemctl start myservice
```

**Выгрузка на локальный компьютер:**

```powershell
scp -o StrictHostKeyChecking=no root@<SERVER_IP>:/root/backups/memex-*.tar.gz .
```

Хранить 5 последних архивов локально.

---

## 12. Известные грабли

1. **Jinja-макросы объявлять до вызова.**
2. **`position: sticky` не работает внутри flex с overflow.**
3. **SQLite `LIKE`/`ILIKE` регистрозависим для кириллицы** — поиск выполняется в Python (`filter_ci`).
4. **SQLite не мигрирует автоматически** — `ALTER TABLE`.
5. **Flask + Gunicorn не подхватывает правки на лету** — `systemctl restart myservice`.
6. **Bootstrap JS обязателен** для dropdown-меню — подключён в `base.html`.
7. **`marked.js` локально** — иначе предпросмотр может отвалиться.
8. **`ADMIN_PASSWORD` в systemd** — только для новых баз. Существующая не перезаписывается.
9. **Дерево категорий в сайдбаре — только корневые** (по замыслу).
10. **`git clone` в непустую папку падает** — в Ansible-плейбуке `git clone` идёт первым шагом, остальное — после.

---

## 13. Документация

- Краткое описание проекта: `README.md`.
- Автоматическое развёртывание: `ansible/README.md`.
- Шпаргалка по Markdown: страница `/help/markdown`.
