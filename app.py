import os
import re
import io
import csv
import json
import hashlib
import markdown
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = 'ваш-секретный-ключ-поменяйте-его'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///notes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DEFAULT_TOPIC = 'Общее'
UPLOAD_MAX_WIDTH = 1920
UPLOAD_QUALITY = 80
UPLOAD_ALLOWED = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff'}

# --- Модели ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    children = db.relationship(
        'Category',
        backref=db.backref('parent', remote_side=[id]),
        cascade='all, delete-orphan'
    )
    notes = db.relationship('Note', backref='category', cascade='all, delete-orphan')

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class GlossaryTerm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(200), nullable=False)
    definition = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(100), default=DEFAULT_TOPIC)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Snippet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    command = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    topic = db.Column(db.String(100), default=DEFAULT_TOPIC)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Link(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    topic = db.Column(db.String(100), default=DEFAULT_TOPIC)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Phone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    number = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    topic = db.Column(db.String(100), default=DEFAULT_TOPIC)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Хелперы ---
def slugify(text):
    text = text.strip().lower()
    text = re.sub(r'[^\w\s\-]', '', text, flags=re.UNICODE)
    text = re.sub(r'\s+', '_', text)
    return text or 'note'

def read_import_source():
    raw = ''
    if 'file' in request.files:
        f = request.files['file']
        if f and f.filename:
            try:
                raw = f.read().decode('utf-8')
            except UnicodeDecodeError:
                raw = f.read().decode('cp1251', errors='replace')
    if not raw.strip():
        raw = request.form.get('json_data', '').strip()
    default_topic = request.form.get('default_topic', '').strip() or DEFAULT_TOPIC
    return raw, default_topic

def filter_ci(items, q, fields):
    if not q:
        return items
    q_lower = q.lower()
    result = []
    for item in items:
        for f in fields:
            val = getattr(item, f, None)
            if val and q_lower in str(val).lower():
                result.append(item)
                break
    return result

def get_root_categories(user_id):
    return Category.query.filter_by(user_id=user_id, parent_id=None).order_by(Category.name).all()

def get_category_path(cat):
    path = []
    current = cat
    while current is not None:
        path.insert(0, current)
        current = current.parent
    return path

def get_category_full_path(cat):
    if not cat:
        return '—'
    return ' / '.join([p.name for p in get_category_path(cat)])

def collect_descendants(cat):
    result = []
    for child in cat.children:
        result.append(child)
        result.extend(collect_descendants(child))
    return result

def collect_descendant_ids(cat):
    return [c.id for c in collect_descendants(cat)]

def get_glossary_topics(user_id):
    rows = db.session.query(GlossaryTerm.topic).filter_by(user_id=user_id).distinct().all()
    return sorted({r[0] for r in rows if r[0]})

def get_snippet_topics(user_id):
    rows = db.session.query(Snippet.topic).filter_by(user_id=user_id).distinct().all()
    return sorted({r[0] for r in rows if r[0]})

def get_link_topics(user_id):
    rows = db.session.query(Link.topic).filter_by(user_id=user_id).distinct().all()
    return sorted({r[0] for r in rows if r[0]})

def get_phone_topics(user_id):
    rows = db.session.query(Phone.topic).filter_by(user_id=user_id).distinct().all()
    return sorted({r[0] for r in rows if r[0]})

@app.context_processor
def inject_categories():
    if current_user.is_authenticated:
        return dict(
            root_categories=get_root_categories(current_user.id),
            get_path=get_category_path
        )
    return dict(root_categories=[], get_path=lambda x: [])

# --- Рендер Markdown ---
WIKI_LINK_RE = re.compile(r'\[\[([^\]]+)\]\]')
GLOSSARY_RE = re.compile(r'\{\{([^}]+)\}\}')

def render_note_html(content, user_id):
    placeholders = {}
    counter = [0]

    def replace_wiki(match):
        title = match.group(1).strip()
        counter[0] += 1
        key = f"WIKILINKPLACEHOLDER{counter[0]}X"
        target = Note.query.filter(
            Note.user_id == user_id,
            db.func.lower(Note.title) == title.lower()
        ).first()
        if target:
            html = f'<a href="/note/{target.id}" class="wikilink">{title}</a>'
        else:
            html = f'<a href="/add?title={title}" class="wikilink-missing" title="Создать заметку «{title}»">{title}</a>'
        placeholders[key] = html
        return key

    content = WIKI_LINK_RE.sub(replace_wiki, content)

    used_terms = []
    def replace_glossary(match):
        name = match.group(1).strip()
        counter[0] += 1
        key = f"GLOSSARYPLACEHOLDER{counter[0]}X"
        term = GlossaryTerm.query.filter(
            GlossaryTerm.user_id == user_id,
            db.func.lower(GlossaryTerm.term) == name.lower()
        ).first()
        if term:
            safe_def = (term.definition
                        .replace('&', '&amp;')
                        .replace('<', '&lt;')
                        .replace('>', '&gt;')
                        .replace('"', '&quot;'))
            html = (f'<span class="glossary-term" data-tooltip="{safe_def}">'
                    f'{term.term}</span>')
            if term.term not in used_terms:
                used_terms.append(term.term)
        else:
            html = f'<span class="glossary-missing" title="Термин «{name}» не найден">{name}</span>'
        placeholders[key] = html
        return key

    content = GLOSSARY_RE.sub(replace_glossary, content)

    md = markdown.Markdown(extensions=['fenced_code', 'tables', 'md_in_html', 'toc'])
    html = md.convert(content)
    toc_html = md.toc

    for key, val in placeholders.items():
        html = html.replace(key, val)

    return html, toc_html, used_terms

# --- Загрузка картинок ---
def save_uploaded_image(file_storage, user_id):
    if not file_storage or not file_storage.filename:
        raise ValueError('Файл не выбран')
    mime = file_storage.mimetype or ''
    if mime not in UPLOAD_ALLOWED:
        raise ValueError(f'Недопустимый тип файла: {mime}')
    data = file_storage.read()
    if not data:
        raise ValueError('Пустой файл')
    if len(data) > 10 * 1024 * 1024:
        raise ValueError('Файл больше 10 МБ')
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise ValueError(f'Не удалось открыть картинку: {e}')
    if img.mode in ('P', 'LA'):
        img = img.convert('RGBA')
    if img.mode == 'CMYK':
        img = img.convert('RGB')
    if img.width > UPLOAD_MAX_WIDTH:
        ratio = UPLOAD_MAX_WIDTH / img.width
        new_size = (UPLOAD_MAX_WIDTH, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    save_kwargs = {'format': 'WEBP', 'quality': UPLOAD_QUALITY, 'method': 6}
    if img.mode == 'RGBA':
        save_kwargs['lossless'] = False
    img.save(buf, **save_kwargs)
    buf.seek(0)
    file_hash = hashlib.sha256(buf.getvalue()).hexdigest()[:16]
    now = datetime.utcnow()
    rel_dir = f"uploads/{now.year}/{now.month:02d}"
    abs_dir = os.path.join(app.static_folder, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    filename = f"{file_hash}.webp"
    abs_path = os.path.join(abs_dir, filename)
    with open(abs_path, 'wb') as f:
        f.write(buf.getvalue())
    return f"/static/{rel_dir}/{filename}"

# ============================================================
# --- ПАРСЕРЫ ---
# ============================================================
def parse_glossary_payload(raw, default_topic=DEFAULT_TOPIC):
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith('[') or raw.startswith('{'):
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError('JSON должен быть массивом или объектом')
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            result.append({
                'term': str(item.get('term', '')).strip(),
                'definition': str(item.get('definition', '')).strip(),
                'topic': str(item.get('topic') or default_topic).strip()
            })
        return result
    first_line = raw.split('\n', 1)[0]
    if ',' in first_line and not first_line.startswith('#'):
        reader = csv.DictReader(io.StringIO(raw))
        result = []
        for row in reader:
            term = (row.get('term') or row.get('Термин') or row.get('название') or '').strip()
            defi = (row.get('definition') or row.get('Определение') or row.get('описание') or '').strip()
            top = (row.get('topic') or row.get('Тема') or default_topic).strip()
            if term and defi:
                result.append({'term': term, 'definition': defi, 'topic': top})
        return result
    result = []
    lines = raw.split('\n')
    current_term = None
    current_def = []
    current_topic = default_topic
    for line in lines:
        mt = re.match(r'^##\s+Тема:\s*(.+)$', line)
        if mt:
            current_topic = mt.group(1).strip()
            continue
        m = re.match(r'^###\s+(.+)$', line)
        if m:
            if current_term:
                result.append({'term': current_term, 'definition': '\n'.join(current_def).strip(), 'topic': current_topic})
            current_term = m.group(1).strip()
            current_def = []
        else:
            if current_term is not None:
                current_def.append(line)
    if current_term:
        result.append({'term': current_term, 'definition': '\n'.join(current_def).strip(), 'topic': current_topic})
    return result


def parse_snippets_payload(raw, default_topic=DEFAULT_TOPIC):
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith('[') or raw.startswith('{'):
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError('JSON должен быть массивом или объектом')
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            result.append({
                'name': str(item.get('name', '')).strip(),
                'command': str(item.get('command', '')).strip(),
                'description': str(item.get('description', '')).strip(),
                'topic': str(item.get('topic') or default_topic).strip()
            })
        return result
    first_line = raw.split('\n', 1)[0]
    if ',' in first_line and not first_line.startswith('#'):
        reader = csv.DictReader(io.StringIO(raw))
        result = []
        for row in reader:
            name = (row.get('name') or row.get('Название') or '').strip()
            cmd = (row.get('command') or row.get('Команда') or '').strip()
            desc = (row.get('description') or row.get('Описание') or '').strip()
            top = (row.get('topic') or row.get('Тема') or default_topic).strip()
            if name and cmd:
                result.append({'name': name, 'command': cmd, 'description': desc, 'topic': top})
        return result
    result = []
    lines = raw.split('\n')
    current_name = None
    current_cmd_lines = []
    current_desc_lines = []
    current_topic = default_topic
    in_code = False
    for line in lines:
        mt = re.match(r'^##\s+Тема:\s*(.+)$', line)
        if mt:
            current_topic = mt.group(1).strip()
            continue
        m = re.match(r'^###\s+(.+)$', line)
        if m:
            if current_name:
                result.append({
                    'name': current_name,
                    'command': '\n'.join(current_cmd_lines).strip(),
                    'description': '\n'.join(current_desc_lines).strip(),
                    'topic': current_topic
                })
            current_name = m.group(1).strip()
            current_cmd_lines = []
            current_desc_lines = []
            in_code = False
        elif line.strip().startswith('```'):
            in_code = not in_code
        else:
            if current_name:
                if in_code:
                    current_cmd_lines.append(line)
                else:
                    current_desc_lines.append(line)
    if current_name:
        result.append({
            'name': current_name,
            'command': '\n'.join(current_cmd_lines).strip(),
            'description': '\n'.join(current_desc_lines).strip(),
            'topic': current_topic
        })
    return result


def parse_links_payload(raw, default_topic=DEFAULT_TOPIC):
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith('[') or raw.startswith('{'):
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError('JSON должен быть массивом или объектом')
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            result.append({
                'title': str(item.get('title', '')).strip(),
                'url': str(item.get('url', '')).strip(),
                'description': str(item.get('description', '')).strip(),
                'topic': str(item.get('topic') or default_topic).strip()
            })
        return result
    first_line = raw.split('\n', 1)[0]
    if ',' in first_line and not first_line.startswith('#'):
        reader = csv.DictReader(io.StringIO(raw))
        result = []
        for row in reader:
            title = (row.get('title') or row.get('Название') or '').strip()
            url = (row.get('url') or row.get('URL') or row.get('ссылка') or '').strip()
            desc = (row.get('description') or row.get('Описание') or '').strip()
            top = (row.get('topic') or row.get('Тема') or default_topic).strip()
            if title and url:
                result.append({'title': title, 'url': url, 'description': desc, 'topic': top})
        return result
    result = []
    lines = raw.split('\n')
    current_title = None
    current_url = None
    current_desc = []
    current_topic = default_topic
    for line in lines:
        mt = re.match(r'^##\s+Тема:\s*(.+)$', line)
        if mt:
            current_topic = mt.group(1).strip()
            continue
        m = re.match(r'^###\s+(.+)$', line)
        if m:
            if current_title and current_url:
                result.append({
                    'title': current_title,
                    'url': current_url,
                    'description': '\n'.join(current_desc).strip(),
                    'topic': current_topic
                })
            current_title = m.group(1).strip()
            current_url = None
            current_desc = []
        elif current_title and current_url is None and line.strip().startswith('http'):
            current_url = line.strip()
        else:
            if current_title and current_url:
                current_desc.append(line)
    if current_title and current_url:
        result.append({
            'title': current_title,
            'url': current_url,
            'description': '\n'.join(current_desc).strip(),
            'topic': current_topic
        })
    return result


def parse_phones_payload(raw, default_topic=DEFAULT_TOPIC):
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith('[') or raw.startswith('{'):
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError('JSON должен быть массивом или объектом')
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            result.append({
                'name': str(item.get('name', '')).strip(),
                'number': str(item.get('number', '')).strip(),
                'description': str(item.get('description', '')).strip(),
                'topic': str(item.get('topic') or default_topic).strip()
            })
        return result
    first_line = raw.split('\n', 1)[0]
    if ',' in first_line and not first_line.startswith('#'):
        reader = csv.DictReader(io.StringIO(raw))
        result = []
        for row in reader:
            name = (row.get('name') or row.get('Имя') or row.get('Название') or '').strip()
            num = (row.get('number') or row.get('Номер') or row.get('телефон') or '').strip()
            desc = (row.get('description') or row.get('Описание') or '').strip()
            top = (row.get('topic') or row.get('Тема') or default_topic).strip()
            if name and num:
                result.append({'name': name, 'number': num, 'description': desc, 'topic': top})
        return result
    result = []
    lines = raw.split('\n')
    current_name = None
    current_number = None
    current_desc = []
    current_topic = default_topic
    for line in lines:
        mt = re.match(r'^##\s+Тема:\s*(.+)$', line)
        if mt:
            current_topic = mt.group(1).strip()
            continue
        m = re.match(r'^###\s+(.+)$', line)
        if m:
            if current_name and current_number:
                result.append({
                    'name': current_name,
                    'number': current_number,
                    'description': '\n'.join(current_desc).strip(),
                    'topic': current_topic
                })
            current_name = m.group(1).strip()
            current_number = None
            current_desc = []
        elif current_name and current_number is None and line.strip():
            current_number = line.strip()
        else:
            if current_name and current_number:
                current_desc.append(line)
    if current_name and current_number:
        result.append({
            'name': current_name,
            'number': current_number,
            'description': '\n'.join(current_desc).strip(),
            'topic': current_topic
        })
    return result


def glossary_to_markdown(terms):
    out = ['# Глоссарий\n']
    current_topic = None
    for t in terms:
        topic = t.topic or DEFAULT_TOPIC
        if topic != current_topic:
            out.append(f'## Тема: {topic}\n')
            current_topic = topic
        out.append(f'### {t.term}\n')
        out.append(t.definition.strip())
        out.append('')
    return '\n'.join(out)


def glossary_to_csv(terms):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['topic', 'term', 'definition'])
    for t in terms:
        writer.writerow([t.topic or DEFAULT_TOPIC, t.term, t.definition])
    return buf.getvalue()


def snippets_to_markdown(items):
    out = ['# Сниппеты\n']
    current_topic = None
    for s in items:
        topic = s.topic or DEFAULT_TOPIC
        if topic != current_topic:
            out.append(f'## Тема: {topic}\n')
            current_topic = topic
        out.append(f'### {s.name}\n')
        if s.description:
            out.append(s.description.strip())
            out.append('')
        out.append('```')
        out.append(s.command.strip())
        out.append('```')
        out.append('')
    return '\n'.join(out)


def snippets_to_csv(items):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['topic', 'name', 'command', 'description'])
    for s in items:
        writer.writerow([s.topic or DEFAULT_TOPIC, s.name, s.command, s.description or ''])
    return buf.getvalue()


def links_to_markdown(items):
    out = ['# Ссылки\n']
    current_topic = None
    for l in items:
        topic = l.topic or DEFAULT_TOPIC
        if topic != current_topic:
            out.append(f'## Тема: {topic}\n')
            current_topic = topic
        out.append(f'### {l.title}\n')
        out.append(l.url)
        out.append('')
        if l.description:
            out.append(l.description.strip())
            out.append('')
    return '\n'.join(out)


def links_to_csv(items):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['topic', 'title', 'url', 'description'])
    for l in items:
        writer.writerow([l.topic or DEFAULT_TOPIC, l.title, l.url, l.description or ''])
    return buf.getvalue()


def phones_to_markdown(items):
    out = ['# Телефоны\n']
    current_topic = None
    for p in items:
        topic = p.topic or DEFAULT_TOPIC
        if topic != current_topic:
            out.append(f'## Тема: {topic}\n')
            current_topic = topic
        out.append(f'### {p.name}\n')
        out.append(p.number)
        out.append('')
        if p.description:
            out.append(p.description.strip())
            out.append('')
    return '\n'.join(out)


def phones_to_csv(items):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['topic', 'name', 'number', 'description'])
    for p in items:
        writer.writerow([p.topic or DEFAULT_TOPIC, p.name, p.number, p.description or ''])
    return buf.getvalue()


# --- Маршруты ---
@app.route('/')
@login_required
def index():
    roots = get_root_categories(current_user.id)
    uncategorized = Note.query.filter_by(user_id=current_user.id, category_id=None).order_by(Note.is_pinned.desc(), Note.id.desc()).all()
    pinned = Note.query.filter_by(user_id=current_user.id, is_pinned=True).order_by(Note.id.desc()).all()
    recent = Note.query.filter_by(user_id=current_user.id).order_by(Note.updated_at.desc()).limit(10).all()
    total_notes = Note.query.filter_by(user_id=current_user.id).count()

    counts = {}
    for cat in roots:
        desc_ids = [cat.id] + collect_descendant_ids(cat)
        notes_count = Note.query.filter(
            Note.user_id == current_user.id,
            Note.category_id.in_(desc_ids)
        ).count()
        counts[cat.id] = {'notes': notes_count, 'subcats': len(desc_ids) - 1}

    return render_template('index.html', categories=roots, uncategorized=uncategorized,
                           pinned=pinned, recent=recent, total_notes=total_notes,
                           counts=counts)

@app.route('/upload/image', methods=['POST'])
@login_required
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'Файл не передан'}), 400
    try:
        url = save_uploaded_image(request.files['image'], current_user.id)
        return jsonify({'url': url})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Ошибка: {e}'}), 500

@app.route('/notes')
@login_required
def all_notes():
    sort = request.args.get('sort', 'updated')
    cat_filter = request.args.get('cat', '')
    q = request.args.get('q', '').strip()

    notes = Note.query.filter_by(user_id=current_user.id).all()

    if cat_filter == 'none':
        notes = [n for n in notes if n.category_id is None]
    elif cat_filter:
        try:
            cat_id = int(cat_filter)
            notes = [n for n in notes if n.category_id == cat_id]
        except ValueError:
            pass

    notes = filter_ci(notes, q, ['title'])

    if sort == 'created':
        notes.sort(key=lambda n: (not n.is_pinned, -(n.created_at.timestamp() if n.created_at else 0)))
    elif sort == 'title':
        notes.sort(key=lambda n: (not n.is_pinned, n.title.lower()))
    elif sort == 'category':
        notes.sort(key=lambda n: (not n.is_pinned, n.category_id or 0, n.title.lower()))
    else:
        notes.sort(key=lambda n: (not n.is_pinned, -(n.updated_at.timestamp() if n.updated_at else 0)))

    all_cats = Category.query.filter_by(user_id=current_user.id).all()
    cat_list = [{'id': c.id, 'path': get_category_full_path(c)} for c in all_cats]
    cat_list.sort(key=lambda x: x['path'])

    return render_template('all_notes.html', notes=notes, cat_list=cat_list,
                           sort=sort, cat_filter=cat_filter, q=q)

@app.route('/notes/import.md', methods=['GET', 'POST'])
@login_required
def import_notes_md():
    if request.method == 'POST':
        category_id = request.form.get('category_id') or None
        files = request.files.getlist('files')
        files = [f for f in files if f and f.filename]
        if not files:
            flash('Файлы не выбраны.')
            return redirect(url_for('import_notes_md'))

        added = 0
        skipped = 0
        now = datetime.utcnow()
        for f in files:
            try:
                content = f.read().decode('utf-8')
            except UnicodeDecodeError:
                content = f.read().decode('cp1251', errors='replace')
            title = re.sub(r'\.md$', '', f.filename, flags=re.IGNORECASE).strip()
            if not title:
                skipped += 1
                continue
            existing = Note.query.filter(
                Note.user_id == current_user.id,
                db.func.lower(Note.title) == title.lower()
            ).first()
            if existing:
                skipped += 1
                continue
            new_note = Note(title=title, content=content, user_id=current_user.id,
                            category_id=category_id, is_pinned=False,
                            created_at=now, updated_at=now)
            db.session.add(new_note)
            added += 1
        db.session.commit()
        flash(f'Импорт завершён. Добавлено: {added}, пропущено: {skipped}.')
        return redirect(url_for('all_notes'))

    all_cats = Category.query.filter_by(user_id=current_user.id).all()
    cat_list = [{'id': c.id, 'path': get_category_full_path(c)} for c in all_cats]
    cat_list.sort(key=lambda x: x['path'])
    return render_template('notes_import_md.html', cat_list=cat_list)

@app.route('/note/<int:note_id>/export.md')
@login_required
def export_note_md(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        flash('Нет доступа')
        return redirect(url_for('index'))
    filename = slugify(note.title) + '.md'
    return Response(note.content, mimetype='text/markdown; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})

@app.route('/search')
@login_required
def search():
    q = request.args.get('q', '').strip()
    results = []
    if q:
        all_notes = Note.query.filter_by(user_id=current_user.id).all()
        results = filter_ci(all_notes, q, ['title', 'content'])
        results.sort(key=lambda n: (not n.is_pinned, -(n.updated_at.timestamp() if n.updated_at else 0)))
    return render_template('search.html', q=q, results=results)

@app.route('/api/glossary/search')
@login_required
def api_glossary_search():
    q = request.args.get('q', '').strip()
    topic = request.args.get('topic', '').strip()
    if not q:
        return jsonify([])
    terms = GlossaryTerm.query.filter_by(user_id=current_user.id).all()
    if topic:
        terms = [t for t in terms if (t.topic or DEFAULT_TOPIC) == topic]
    q_lower = q.lower()
    matched = [t for t in terms if t.term.lower().startswith(q_lower)]
    matched.sort(key=lambda t: t.term.lower())
    matched = matched[:15]
    result = []
    for t in matched:
        html_def = markdown.markdown(t.definition, extensions=['fenced_code', 'tables'])
        result.append({'id': t.id, 'term': t.term, 'topic': t.topic or DEFAULT_TOPIC, 'definition_html': html_def})
    return jsonify(result)

@app.route('/api/categories/search')
@login_required
def api_categories_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    cats = Category.query.filter_by(user_id=current_user.id).all()
    matched = filter_ci(cats, q, ['name'])
    matched = matched[:20]
    result = []
    for c in matched:
        path = get_category_path(c)
        result.append({
            'id': c.id,
            'name': c.name,
            'path': ' / '.join([p.name for p in path])
        })
    return jsonify(result)

def build_tree_json(cats):
    result = []
    for c in cats:
        children = sorted(c.children, key=lambda x: x.name)
        result.append({
            'id': c.id,
            'name': c.name,
            'children': build_tree_json(children) if children else []
        })
    return result

@app.route('/api/categories/tree')
@login_required
def api_categories_tree():
    roots = get_root_categories(current_user.id)
    return jsonify(build_tree_json(roots))

@app.route('/api/notes/search')
@login_required
def api_notes_search():
    q = request.args.get('q', '').strip()
    notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.updated_at.desc()).all()
    notes = filter_ci(notes, q, ['title'])
    notes = notes[:20]
    result = []
    for n in notes:
        result.append({
            'id': n.id,
            'title': n.title,
            'category': get_category_full_path(n.category) if n.category else '—'
        })
    return jsonify(result)

@app.route('/api/links/search')
@login_required
def api_links_search():
    q = request.args.get('q', '').strip()
    topic = request.args.get('topic', '').strip()
    items = Link.query.filter_by(user_id=current_user.id).all()
    if topic:
        items = [l for l in items if (l.topic or DEFAULT_TOPIC) == topic]
    if q:
        items = filter_ci(items, q, ['title', 'url', 'description'])
    items = items[:30]
    return jsonify([{
        'id': l.id,
        'title': l.title,
        'url': l.url,
        'description': l.description or '',
        'topic': l.topic or DEFAULT_TOPIC
    } for l in items])

# --- Категории ---
@app.route('/categories')
@login_required
def categories():
    roots = get_root_categories(current_user.id)
    total_notes = Note.query.filter_by(user_id=current_user.id).count()
    total_cats = Category.query.filter_by(user_id=current_user.id).count()
    total_snips = Snippet.query.filter_by(user_id=current_user.id).count()
    total_terms = GlossaryTerm.query.filter_by(user_id=current_user.id).count()
    total_links = Link.query.filter_by(user_id=current_user.id).count()
    total_phones = Phone.query.filter_by(user_id=current_user.id).count()
    recent = Note.query.filter_by(user_id=current_user.id).order_by(Note.updated_at.desc()).limit(8).all()
    return render_template('categories.html', categories=roots,
                           total_notes=total_notes, total_cats=total_cats,
                           total_snips=total_snips, total_terms=total_terms,
                           total_links=total_links, total_phones=total_phones,
                           recent=recent)

@app.route('/categories/import', methods=['GET', 'POST'])
@login_required
def import_categories():
    if request.method == 'POST':
        raw, _ = read_import_source()
        if not raw:
            flash('Пусто.')
            return redirect(url_for('import_categories'))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            flash(f'Ошибка JSON: {e}')
            return redirect(url_for('import_categories'))
        if not isinstance(data, list):
            flash('Ожидался JSON-массив объектов.')
            return redirect(url_for('import_categories'))

        added, skipped = 0, 0

        def create_tree(items, parent_id):
            nonlocal added, skipped
            for item in items:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                name = str(item.get('name', '')).strip()
                if not name:
                    skipped += 1
                    continue
                existing = Category.query.filter(
                    Category.user_id == current_user.id,
                    Category.parent_id == parent_id,
                    db.func.lower(Category.name) == name.lower()
                ).first()
                if existing:
                    skipped += 1
                    cat = existing
                else:
                    cat = Category(name=name, user_id=current_user.id, parent_id=parent_id)
                    db.session.add(cat)
                    db.session.flush()
                    added += 1
                children = item.get('children', [])
                if isinstance(children, list) and children:
                    create_tree(children, cat.id)

        create_tree(data, None)
        db.session.commit()
        flash(f'Импорт завершён. Добавлено: {added}, пропущено: {skipped}.')
        return redirect(url_for('categories'))
    return render_template('categories_import.html')

@app.route('/category/add', methods=['POST'])
@login_required
def add_category():
    name = request.form['name'].strip()
    parent_id = request.form.get('parent_id') or None
    if not name:
        return redirect(url_for('categories'))
    parent_id_int = int(parent_id) if parent_id else None
    existing = Category.query.filter(
        Category.user_id == current_user.id,
        Category.parent_id == parent_id_int,
        db.func.lower(Category.name) == name.lower()
    ).first()
    if existing:
        flash(f'Категория «{name}» уже существует')
        return redirect(url_for('categories'))
    db.session.add(Category(name=name, user_id=current_user.id, parent_id=parent_id_int))
    db.session.commit()
    flash(f'Категория «{name}» создана')
    return redirect(url_for('categories'))

@app.route('/category/rename/<int:cat_id>', methods=['POST'])
@login_required
def rename_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    if cat.user_id != current_user.id:
        return redirect(url_for('categories'))
    new_name = request.form['name'].strip()
    if new_name:
        existing = Category.query.filter(
            Category.user_id == current_user.id,
            Category.parent_id == cat.parent_id,
            db.func.lower(Category.name) == new_name.lower(),
            Category.id != cat.id
        ).first()
        if existing:
            flash(f'Категория «{new_name}» уже существует')
        else:
            cat.name = new_name
            db.session.commit()
            flash('Переименовано')
    else:
        flash('Имя не может быть пустым')
    return redirect(url_for('categories'))

@app.route('/category/delete/<int:cat_id>')
@login_required
def delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    if cat.user_id == current_user.id:
        db.session.delete(cat)
        db.session.commit()
        flash('Категория и все вложенные удалены')
    return redirect(url_for('categories'))

@app.route('/category/<int:cat_id>')
@login_required
def view_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    if cat.user_id != current_user.id:
        flash('Нет доступа')
        return redirect(url_for('index'))
    notes = Note.query.filter_by(category_id=cat.id, user_id=current_user.id).order_by(Note.is_pinned.desc(), Note.id.desc()).all()
    breadcrumb = get_category_path(cat)
    children = sorted(cat.children, key=lambda c: c.name)

    descendant_ids = collect_descendant_ids(cat)
    all_ids = [cat.id] + descendant_ids
    recent_in_cat = Note.query.filter(
        Note.user_id == current_user.id,
        Note.category_id.in_(all_ids)
    ).order_by(Note.updated_at.desc()).limit(8).all()

    parent = cat.parent
    if parent:
        siblings_cats = [c for c in parent.children if c.id != cat.id]
        siblings_cats.sort(key=lambda c: c.name)
    else:
        siblings_cats = [c for c in get_root_categories(current_user.id) if c.id != cat.id]

    return render_template('category.html', category=cat, notes=notes, breadcrumb=breadcrumb,
                           children=children, recent_in_cat=recent_in_cat,
                           parent_cat=parent, siblings_cats=siblings_cats)

# --- Глоссарий ---
@app.route('/glossary')
@login_required
def glossary():
    topic_filter = request.args.get('topic', '').strip()
    terms = GlossaryTerm.query.filter_by(user_id=current_user.id).all()
    if topic_filter:
        terms = [t for t in terms if (t.topic or DEFAULT_TOPIC) == topic_filter]
    terms.sort(key=lambda t: ((t.topic or DEFAULT_TOPIC).lower(), t.term.lower()))
    topics = get_glossary_topics(current_user.id)
    return render_template('glossary.html', terms=terms, topics=topics, topic_filter=topic_filter)

@app.route('/glossary/add', methods=['POST'])
@login_required
def add_term():
    term = request.form['term'].strip()
    definition = request.form['definition'].strip()
    topic = request.form.get('topic', '').strip() or DEFAULT_TOPIC
    if term and definition:
        existing = GlossaryTerm.query.filter(
            GlossaryTerm.user_id == current_user.id,
            db.func.lower(GlossaryTerm.term) == term.lower(),
            GlossaryTerm.topic == topic
        ).first()
        if existing:
            flash(f'Термин «{term}» уже есть в теме «{topic}»')
        else:
            db.session.add(GlossaryTerm(term=term, definition=definition, topic=topic, user_id=current_user.id))
            db.session.commit()
            flash(f'Термин «{term}» добавлен в «{topic}»')
    return redirect(url_for('glossary', topic=topic))

@app.route('/glossary/edit/<int:term_id>', methods=['POST'])
@login_required
def edit_term(term_id):
    t = GlossaryTerm.query.get_or_404(term_id)
    if t.user_id != current_user.id:
        return redirect(url_for('glossary'))
    new_term = request.form['term'].strip()
    new_def = request.form['definition'].strip()
    new_topic = request.form.get('topic', '').strip() or DEFAULT_TOPIC
    if new_term and new_def:
        existing = GlossaryTerm.query.filter(
            GlossaryTerm.user_id == current_user.id,
            db.func.lower(GlossaryTerm.term) == new_term.lower(),
            GlossaryTerm.topic == new_topic,
            GlossaryTerm.id != t.id
        ).first()
        if existing:
            flash(f'Термин «{new_term}» уже есть в теме «{new_topic}»')
        else:
            t.term = new_term
            t.definition = new_def
            t.topic = new_topic
            db.session.commit()
            flash('Термин обновлён')
    return redirect(url_for('glossary'))

@app.route('/glossary/delete/<int:term_id>')
@login_required
def delete_term(term_id):
    t = GlossaryTerm.query.get_or_404(term_id)
    if t.user_id == current_user.id:
        db.session.delete(t)
        db.session.commit()
    return redirect(url_for('glossary'))

@app.route('/glossary/import', methods=['GET', 'POST'])
@login_required
def import_glossary():
    if request.method == 'POST':
        raw, default_topic = read_import_source()
        if not raw:
            flash('Пусто.')
            return redirect(url_for('import_glossary'))
        try:
            data = parse_glossary_payload(raw, default_topic)
        except Exception as e:
            flash(f'Ошибка парсинга: {e}')
            return redirect(url_for('import_glossary'))

        added, updated, skipped = 0, 0, 0
        for item in data:
            term = item.get('term', '').strip()
            definition = item.get('definition', '').strip()
            topic = item.get('topic', '').strip() or default_topic
            if not term or not definition:
                skipped += 1
                continue
            existing = GlossaryTerm.query.filter(
                GlossaryTerm.user_id == current_user.id,
                db.func.lower(GlossaryTerm.term) == term.lower(),
                GlossaryTerm.topic == topic
            ).first()
            if existing:
                if existing.definition != definition:
                    existing.definition = definition
                    updated += 1
                else:
                    skipped += 1
            else:
                db.session.add(GlossaryTerm(term=term, definition=definition, topic=topic, user_id=current_user.id))
                added += 1
        db.session.commit()
        flash(f'Импорт завершён. Добавлено: {added}, обновлено: {updated}, пропущено: {skipped}.')
        return redirect(url_for('glossary'))
    topics = get_glossary_topics(current_user.id)
    return render_template('glossary_import.html', topics=topics)

@app.route('/glossary/export.<fmt>')
@login_required
def export_glossary(fmt):
    terms = GlossaryTerm.query.filter_by(user_id=current_user.id).order_by(GlossaryTerm.topic, GlossaryTerm.term).all()
    if fmt == 'json':
        data = [{'topic': t.topic or DEFAULT_TOPIC, 'term': t.term, 'definition': t.definition} for t in terms]
        return Response(json.dumps(data, ensure_ascii=False, indent=2),
                        mimetype='application/json',
                        headers={'Content-Disposition': 'attachment; filename=glossary.json'})
    if fmt == 'md':
        content = glossary_to_markdown(terms)
        return Response(content, mimetype='text/markdown; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=glossary.md'})
    if fmt == 'csv':
        content = glossary_to_csv(terms)
        return Response(content, mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=glossary.csv'})
    flash('Неизвестный формат')
    return redirect(url_for('glossary'))

# --- Сниппеты ---
@app.route('/snippets')
@login_required
def snippets():
    q = request.args.get('q', '').strip()
    topic_filter = request.args.get('topic', '').strip()
    items = Snippet.query.filter_by(user_id=current_user.id).all()
    if topic_filter:
        items = [s for s in items if (s.topic or DEFAULT_TOPIC) == topic_filter]
    items = filter_ci(items, q, ['name', 'command', 'description'])
    items.sort(key=lambda s: ((s.topic or DEFAULT_TOPIC).lower(), s.name.lower()))
    topics = get_snippet_topics(current_user.id)
    return render_template('snippets.html', snippets=items, q=q, topics=topics, topic_filter=topic_filter)

@app.route('/snippets/add', methods=['GET', 'POST'])
@login_required
def add_snippet():
    if request.method == 'POST':
        name = request.form['name'].strip()
        command = request.form['command'].strip()
        description = request.form.get('description', '').strip()
        topic = request.form.get('topic', '').strip() or DEFAULT_TOPIC
        if name and command:
            existing = Snippet.query.filter(
                Snippet.user_id == current_user.id,
                db.func.lower(Snippet.name) == name.lower(),
                Snippet.topic == topic
            ).first()
            if existing:
                flash(f'Сниппет «{name}» уже есть в теме «{topic}»')
            else:
                now = datetime.utcnow()
                db.session.add(Snippet(name=name, command=command, description=description,
                                       topic=topic, user_id=current_user.id,
                                       created_at=now, updated_at=now))
                db.session.commit()
                flash(f'Сниппет «{name}» добавлен в «{topic}»')
                return redirect(url_for('snippets', topic=topic))
    topics = get_snippet_topics(current_user.id)
    return render_template('snippet_edit.html', snippet=None, topics=topics)

@app.route('/snippets/edit/<int:snippet_id>', methods=['GET', 'POST'])
@login_required
def edit_snippet(snippet_id):
    s = Snippet.query.get_or_404(snippet_id)
    if s.user_id != current_user.id:
        return redirect(url_for('snippets'))
    if request.method == 'POST':
        s.name = request.form['name'].strip()
        s.command = request.form['command'].strip()
        s.description = request.form.get('description', '').strip()
        s.topic = request.form.get('topic', '').strip() or DEFAULT_TOPIC
        s.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Сниппет обновлён')
        return redirect(url_for('snippets'))
    topics = get_snippet_topics(current_user.id)
    return render_template('snippet_edit.html', snippet=s, topics=topics)

@app.route('/snippets/delete/<int:snippet_id>')
@login_required
def delete_snippet(snippet_id):
    s = Snippet.query.get_or_404(snippet_id)
    if s.user_id == current_user.id:
        db.session.delete(s)
        db.session.commit()
        flash('Сниппет удалён')
    return redirect(url_for('snippets'))

@app.route('/snippets/import', methods=['GET', 'POST'])
@login_required
def import_snippets():
    if request.method == 'POST':
        raw, default_topic = read_import_source()
        if not raw:
            flash('Пусто.')
            return redirect(url_for('import_snippets'))
        try:
            data = parse_snippets_payload(raw, default_topic)
        except Exception as e:
            flash(f'Ошибка парсинга: {e}')
            return redirect(url_for('import_snippets'))

        added, updated, skipped = 0, 0, 0
        now = datetime.utcnow()
        for item in data:
            name = item.get('name', '').strip()
            command = item.get('command', '').strip()
            description = item.get('description', '').strip()
            topic = item.get('topic', '').strip() or default_topic
            if not name or not command:
                skipped += 1
                continue
            existing = Snippet.query.filter(
                Snippet.user_id == current_user.id,
                db.func.lower(Snippet.name) == name.lower(),
                Snippet.topic == topic
            ).first()
            if existing:
                if existing.command != command or (existing.description or '') != description:
                    existing.command = command
                    existing.description = description
                    existing.updated_at = now
                    updated += 1
                else:
                    skipped += 1
            else:
                db.session.add(Snippet(name=name, command=command, description=description,
                                       topic=topic, user_id=current_user.id,
                                       created_at=now, updated_at=now))
                added += 1
        db.session.commit()
        flash(f'Импорт завершён. Добавлено: {added}, обновлено: {updated}, пропущено: {skipped}.')
        return redirect(url_for('snippets'))
    topics = get_snippet_topics(current_user.id)
    return render_template('snippets_import.html', topics=topics)

@app.route('/snippets/export.<fmt>')
@login_required
def export_snippets(fmt):
    items = Snippet.query.filter_by(user_id=current_user.id).order_by(Snippet.topic, Snippet.name).all()
    if fmt == 'json':
        data = [{'topic': s.topic or DEFAULT_TOPIC, 'name': s.name, 'command': s.command, 'description': s.description or ''} for s in items]
        return Response(json.dumps(data, ensure_ascii=False, indent=2),
                        mimetype='application/json',
                        headers={'Content-Disposition': 'attachment; filename=snippets.json'})
    if fmt == 'md':
        content = snippets_to_markdown(items)
        return Response(content, mimetype='text/markdown; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=snippets.md'})
    if fmt == 'csv':
        content = snippets_to_csv(items)
        return Response(content, mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=snippets.csv'})
    flash('Неизвестный формат')
    return redirect(url_for('snippets'))

# --- Ссылки ---
@app.route('/links')
@login_required
def links():
    q = request.args.get('q', '').strip()
    topic_filter = request.args.get('topic', '').strip()
    items = Link.query.filter_by(user_id=current_user.id).all()
    if topic_filter:
        items = [l for l in items if (l.topic or DEFAULT_TOPIC) == topic_filter]
    items = filter_ci(items, q, ['title', 'url', 'description'])
    items.sort(key=lambda l: ((l.topic or DEFAULT_TOPIC).lower(), l.title.lower()))
    topics = get_link_topics(current_user.id)
    return render_template('links.html', links=items, q=q, topics=topics, topic_filter=topic_filter)

@app.route('/links/add', methods=['GET', 'POST'])
@login_required
def add_link():
    if request.method == 'POST':
        title = request.form['title'].strip()
        url = request.form['url'].strip()
        description = request.form.get('description', '').strip()
        topic = request.form.get('topic', '').strip() or DEFAULT_TOPIC
        if title and url:
            existing = Link.query.filter(
                Link.user_id == current_user.id,
                db.func.lower(Link.title) == title.lower(),
                Link.topic == topic
            ).first()
            if existing:
                flash(f'Ссылка «{title}» уже есть в теме «{topic}»')
            else:
                now = datetime.utcnow()
                db.session.add(Link(title=title, url=url, description=description,
                                    topic=topic, user_id=current_user.id,
                                    created_at=now, updated_at=now))
                db.session.commit()
                flash(f'Ссылка «{title}» добавлена в «{topic}»')
                return redirect(url_for('links', topic=topic))
    topics = get_link_topics(current_user.id)
    return render_template('link_edit.html', link=None, topics=topics)

@app.route('/links/edit/<int:link_id>', methods=['GET', 'POST'])
@login_required
def edit_link(link_id):
    l = Link.query.get_or_404(link_id)
    if l.user_id != current_user.id:
        return redirect(url_for('links'))
    if request.method == 'POST':
        l.title = request.form['title'].strip()
        l.url = request.form['url'].strip()
        l.description = request.form.get('description', '').strip()
        l.topic = request.form.get('topic', '').strip() or DEFAULT_TOPIC
        l.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Ссылка обновлена')
        return redirect(url_for('links'))
    topics = get_link_topics(current_user.id)
    return render_template('link_edit.html', link=l, topics=topics)

@app.route('/links/delete/<int:link_id>')
@login_required
def delete_link(link_id):
    l = Link.query.get_or_404(link_id)
    if l.user_id == current_user.id:
        db.session.delete(l)
        db.session.commit()
        flash('Ссылка удалена')
    return redirect(url_for('links'))

@app.route('/links/import', methods=['GET', 'POST'])
@login_required
def import_links():
    if request.method == 'POST':
        raw, default_topic = read_import_source()
        if not raw:
            flash('Пусто.')
            return redirect(url_for('import_links'))
        try:
            data = parse_links_payload(raw, default_topic)
        except Exception as e:
            flash(f'Ошибка парсинга: {e}')
            return redirect(url_for('import_links'))

        added, updated, skipped = 0, 0, 0
        now = datetime.utcnow()
        for item in data:
            title = item.get('title', '').strip()
            url = item.get('url', '').strip()
            description = item.get('description', '').strip()
            topic = item.get('topic', '').strip() or default_topic
            if not title or not url:
                skipped += 1
                continue
            existing = Link.query.filter(
                Link.user_id == current_user.id,
                db.func.lower(Link.title) == title.lower(),
                Link.topic == topic
            ).first()
            if existing:
                if existing.url != url or (existing.description or '') != description:
                    existing.url = url
                    existing.description = description
                    existing.updated_at = now
                    updated += 1
                else:
                    skipped += 1
            else:
                db.session.add(Link(title=title, url=url, description=description,
                                    topic=topic, user_id=current_user.id,
                                    created_at=now, updated_at=now))
                added += 1
        db.session.commit()
        flash(f'Импорт завершён. Добавлено: {added}, обновлено: {updated}, пропущено: {skipped}.')
        return redirect(url_for('links'))
    topics = get_link_topics(current_user.id)
    return render_template('links_import.html', topics=topics)

@app.route('/links/export.<fmt>')
@login_required
def export_links(fmt):
    items = Link.query.filter_by(user_id=current_user.id).order_by(Link.topic, Link.title).all()
    if fmt == 'json':
        data = [{'topic': l.topic or DEFAULT_TOPIC, 'title': l.title, 'url': l.url, 'description': l.description or ''} for l in items]
        return Response(json.dumps(data, ensure_ascii=False, indent=2),
                        mimetype='application/json',
                        headers={'Content-Disposition': 'attachment; filename=links.json'})
    if fmt == 'md':
        content = links_to_markdown(items)
        return Response(content, mimetype='text/markdown; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=links.md'})
    if fmt == 'csv':
        content = links_to_csv(items)
        return Response(content, mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=links.csv'})
    flash('Неизвестный формат')
    return redirect(url_for('links'))

# --- Телефоны ---
@app.route('/phones')
@login_required
def phones():
    q = request.args.get('q', '').strip()
    topic_filter = request.args.get('topic', '').strip()
    items = Phone.query.filter_by(user_id=current_user.id).all()
    if topic_filter:
        items = [p for p in items if (p.topic or DEFAULT_TOPIC) == topic_filter]
    items = filter_ci(items, q, ['name', 'number', 'description'])
    items.sort(key=lambda p: ((p.topic or DEFAULT_TOPIC).lower(), p.name.lower()))
    topics = get_phone_topics(current_user.id)
    return render_template('phones.html', phones=items, q=q, topics=topics, topic_filter=topic_filter)

@app.route('/phones/add', methods=['GET', 'POST'])
@login_required
def add_phone():
    if request.method == 'POST':
        name = request.form['name'].strip()
        number = request.form['number'].strip()
        description = request.form.get('description', '').strip()
        topic = request.form.get('topic', '').strip() or DEFAULT_TOPIC
        if name and number:
            existing = Phone.query.filter(
                Phone.user_id == current_user.id,
                db.func.lower(Phone.name) == name.lower(),
                Phone.topic == topic
            ).first()
            if existing:
                flash(f'Контакт «{name}» уже есть в теме «{topic}»')
            else:
                now = datetime.utcnow()
                db.session.add(Phone(name=name, number=number, description=description,
                                     topic=topic, user_id=current_user.id,
                                     created_at=now, updated_at=now))
                db.session.commit()
                flash(f'Контакт «{name}» добавлен в «{topic}»')
                return redirect(url_for('phones', topic=topic))
    topics = get_phone_topics(current_user.id)
    return render_template('phone_edit.html', phone=None, topics=topics)

@app.route('/phones/edit/<int:phone_id>', methods=['GET', 'POST'])
@login_required
def edit_phone(phone_id):
    p = Phone.query.get_or_404(phone_id)
    if p.user_id != current_user.id:
        return redirect(url_for('phones'))
    if request.method == 'POST':
        p.name = request.form['name'].strip()
        p.number = request.form['number'].strip()
        p.description = request.form.get('description', '').strip()
        p.topic = request.form.get('topic', '').strip() or DEFAULT_TOPIC
        p.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Контакт обновлён')
        return redirect(url_for('phones'))
    topics = get_phone_topics(current_user.id)
    return render_template('phone_edit.html', phone=p, topics=topics)

@app.route('/phones/delete/<int:phone_id>')
@login_required
def delete_phone(phone_id):
    p = Phone.query.get_or_404(phone_id)
    if p.user_id == current_user.id:
        db.session.delete(p)
        db.session.commit()
        flash('Контакт удалён')
    return redirect(url_for('phones'))

@app.route('/phones/import', methods=['GET', 'POST'])
@login_required
def import_phones():
    if request.method == 'POST':
        raw, default_topic = read_import_source()
        if not raw:
            flash('Пусто.')
            return redirect(url_for('import_phones'))
        try:
            data = parse_phones_payload(raw, default_topic)
        except Exception as e:
            flash(f'Ошибка парсинга: {e}')
            return redirect(url_for('import_phones'))

        added, updated, skipped = 0, 0, 0
        now = datetime.utcnow()
        for item in data:
            name = item.get('name', '').strip()
            number = item.get('number', '').strip()
            description = item.get('description', '').strip()
            topic = item.get('topic', '').strip() or default_topic
            if not name or not number:
                skipped += 1
                continue
            existing = Phone.query.filter(
                Phone.user_id == current_user.id,
                db.func.lower(Phone.name) == name.lower(),
                Phone.topic == topic
            ).first()
            if existing:
                if existing.number != number or (existing.description or '') != description:
                    existing.number = number
                    existing.description = description
                    existing.updated_at = now
                    updated += 1
                else:
                    skipped += 1
            else:
                db.session.add(Phone(name=name, number=number, description=description,
                                     topic=topic, user_id=current_user.id,
                                     created_at=now, updated_at=now))
                added += 1
        db.session.commit()
        flash(f'Импорт завершён. Добавлено: {added}, обновлено: {updated}, пропущено: {skipped}.')
        return redirect(url_for('phones'))
    topics = get_phone_topics(current_user.id)
    return render_template('phones_import.html', topics=topics)

@app.route('/phones/export.<fmt>')
@login_required
def export_phones(fmt):
    items = Phone.query.filter_by(user_id=current_user.id).order_by(Phone.topic, Phone.name).all()
    if fmt == 'json':
        data = [{'topic': p.topic or DEFAULT_TOPIC, 'name': p.name, 'number': p.number, 'description': p.description or ''} for p in items]
        return Response(json.dumps(data, ensure_ascii=False, indent=2),
                        mimetype='application/json',
                        headers={'Content-Disposition': 'attachment; filename=phones.json'})
    if fmt == 'md':
        content = phones_to_markdown(items)
        return Response(content, mimetype='text/markdown; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=phones.md'})
    if fmt == 'csv':
        content = phones_to_csv(items)
        return Response(content, mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename=phones.csv'})
    flash('Неизвестный формат')
    return redirect(url_for('phones'))

# --- О проекте ---
@app.route('/help/markdown')
@login_required
def help_markdown():
    return render_template('help_markdown.html')

@app.route('/about')
@login_required
def about():
    try:
        with open('/root/myservice/PROJECT.md', 'r', encoding='utf-8') as f:
            md_text = f.read()
        html = markdown.markdown(md_text, extensions=['fenced_code', 'tables', 'toc'])
    except FileNotFoundError:
        html = '<p class="text-danger">Файл PROJECT.md не найден на сервере.</p>'
    return render_template('about.html', content=html)

# --- Логин ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Заметки ---
@app.route('/note/<int:note_id>')
@login_required
def view_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        flash('У вас нет доступа к этой заметке')
        return redirect(url_for('index'))

    html_content, toc_html, used_terms = render_note_html(note.content, current_user.id)

    siblings = []
    if note.category_id:
        siblings = Note.query.filter(
            Note.user_id == current_user.id,
            Note.category_id == note.category_id,
            Note.id != note.id
        ).order_by(Note.is_pinned.desc(), Note.id.desc()).all()

    breadcrumb = get_category_path(note.category) if note.category else []
    all_snippets = Snippet.query.filter_by(user_id=current_user.id).order_by(Snippet.topic, Snippet.name).all()
    all_links = Link.query.filter_by(user_id=current_user.id).order_by(Link.topic, Link.title).limit(30).all()
    all_phones = Phone.query.filter_by(user_id=current_user.id).order_by(Phone.topic, Phone.name).limit(30).all()
    glossary_topics = get_glossary_topics(current_user.id)
    snippet_topics = get_snippet_topics(current_user.id)
    link_topics = get_link_topics(current_user.id)
    phone_topics = get_phone_topics(current_user.id)

    return render_template('note.html', note=note, content=html_content,
                           toc_html=toc_html, siblings=siblings, used_terms=used_terms,
                           breadcrumb=breadcrumb, all_snippets=all_snippets,
                           all_links=all_links, all_phones=all_phones,
                           glossary_topics=glossary_topics, snippet_topics=snippet_topics,
                           link_topics=link_topics, phone_topics=phone_topics)

@app.route('/add', methods=['GET', 'POST'])
@app.route('/add/<int:cat_id>', methods=['GET', 'POST'])
@login_required
def add_note(cat_id=None):
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category_id = request.form.get('category_id') or None
        is_pinned = bool(request.form.get('is_pinned'))
        now = datetime.utcnow()
        new_note = Note(title=title, content=content, user_id=current_user.id,
                        category_id=category_id, is_pinned=is_pinned,
                        created_at=now, updated_at=now)
        db.session.add(new_note)
        db.session.commit()
        if category_id:
            return redirect(url_for('view_category', cat_id=category_id))
        return redirect(url_for('index'))
    prefill_title = request.args.get('title', '')
    return render_template('edit.html', note=None, preselected_cat=cat_id, prefill_title=prefill_title)

@app.route('/edit/<int:note_id>', methods=['GET', 'POST'])
@login_required
def edit_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        return redirect(url_for('index'))
    if request.method == 'POST':
        note.title = request.form['title']
        note.content = request.form['content']
        note.category_id = request.form.get('category_id') or None
        note.is_pinned = bool(request.form.get('is_pinned'))
        note.updated_at = datetime.utcnow()
        db.session.commit()
        return redirect(url_for('view_note', note_id=note.id))
    return render_template('edit.html', note=note, preselected_cat=note.category_id, prefill_title='')

@app.route('/move/<int:note_id>', methods=['POST'])
@login_required
def move_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        return redirect(url_for('index'))
    note.category_id = request.form.get('category_id') or None
    note.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Заметка перемещена')
    return redirect(url_for('view_note', note_id=note.id))

@app.route('/pin/<int:note_id>')
@login_required
def toggle_pin(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id == current_user.id:
        note.is_pinned = not note.is_pinned
        db.session.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/delete/<int:note_id>')
@login_required
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id == current_user.id:
        db.session.delete(note)
        db.session.commit()
    return redirect(url_for('index'))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        initial_pw = os.environ.get('ADMIN_PASSWORD')
        if not initial_pw:
            initial_pw = 'admin123'
            print("ВНИМАНИЕ: ADMIN_PASSWORD не задан.")
        hashed_pw = generate_password_hash(initial_pw)
        admin = User(username='admin', password_hash=hashed_pw)
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
