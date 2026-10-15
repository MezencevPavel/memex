# Memex

**Personal knowledge base** — личный сервис для хранения заметок, глоссария, сниппетов, ссылок и контактов.

Название — отсылка к концепции **Memex** Ванневара Буша (1945): «устройство для расширения памяти».

## Что умеет

- 📝 **Заметки** — Markdown, категории неограниченной вложенности, TOC, избранное, ссылки `[[...]]`
- 📖 **Глоссарий** — термины с темами и всплывающими подсказками `{{...}}`
- 💻 **Сниппеты** — команды для копирования в один клик
- 🔗 **Ссылки** — полезные URL с описанием
- 📞 **Телефоны** — контакты с кнопкой «Позвонить»
- 🖼 **Картинки** — загрузка с автосжатием в WebP
- 🔒 **Инфраструктура** — HTTPS, Fail2ban, systemd, автобэкап

## Стек

Python 3.12 · Flask · SQLite · Gunicorn · Nginx · Bootstrap 5 · Pillow

## Установка

```bash
git clone https://github.com/MezencevPavel/memex.git /opt/memex
cd /opt/memex
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
