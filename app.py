# -*- coding: utf-8 -*-
"""
ONNI_MONNI — динамический сайт-портфолио на Flask + SQLite.

Модули:
- Работы, лайки, комментарии, просмотры (как раньше).
- Динамические вкладки/категории — управляются админом из /admin, а не зашиты в код.
- Полноэкранный лайтбокс — /api/work/<id> отдаёт JSON без перезагрузки страницы.
- Живой статус автора — одна строка в БД, редактируется из /admin, видна в шапке сайта.
- Поддержка и уведомления — пользователь пишет через /support, админ одобряет
  (галочка) -> пользователю приходит уведомление.
- Личный чат с админом — /chat для пользователя, /admin/chat/<user_id> для админа,
  с возможностью прикладывать картинки. Работает без веб-сокетов (обновление по
  запросу страницы), без "живого" пуша сообщений.
"""

import os
from datetime import datetime

from flask import (
    Flask, render_template, redirect, url_for, request,
    flash, abort, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --------------------------------------------------------------------------
# НАСТРОЙКИ
# --------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'onni-monni-secret-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'onni.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024  # 12 МБ на файл

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите, чтобы продолжить.'
login_manager.login_message_category = 'error'

DEFAULT_ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
DEFAULT_ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'monioni60@gmail.com')
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

DEFAULT_TAGS = [
    ('Цифровой арт', 'digital'),
    ('Традиционный арт', 'traditional'),
    ('Фото', 'photo'),
]

DEFAULT_STATUS_TEXT = '🟢 Свободен для заказов'


# --------------------------------------------------------------------------
# МОДЕЛИ БАЗЫ ДАННЫХ
# --------------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    comments = db.relationship('Comment', backref='author', lazy=True)
    likes = db.relationship('Like', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Tag(db.Model):
    """Динамическая вкладка/категория — управляется из /admin."""
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Work(db.Model):
    __tablename__ = 'works'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True, default='')
    image_url = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(80), nullable=False, default='digital')  # хранит slug тега
    views = db.Column(db.Integer, default=0, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    comments = db.relationship('Comment', backref='work', lazy=True,
                                cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='work', lazy=True,
                             cascade='all, delete-orphan')

    @property
    def category_label(self):
        tag = Tag.query.filter_by(slug=self.category).first()
        return tag.name if tag else self.category

    @property
    def like_count(self):
        return len(self.likes)

    @property
    def comment_count(self):
        return len(self.comments)

    def is_liked_by(self, user):
        if not user or not user.is_authenticated:
            return False
        return any(l.user_id == user.id for l in self.likes)

    @property
    def image_src(self):
        if self.image_url.startswith('http://') or self.image_url.startswith('https://'):
            return self.image_url
        return url_for('static', filename='uploads/' + self.image_url)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description or '',
            'image_src': self.image_src,
            'category_label': self.category_label,
            'views': self.views,
            'like_count': self.like_count,
            'comment_count': self.comment_count,
            'is_liked': self.is_liked_by(current_user),
            'date': self.date.strftime('%d.%m.%Y'),
            'comments': [
                {
                    'id': c.id,
                    'author': c.author.username,
                    'text': c.text,
                    'date': c.date.strftime('%d.%m.%Y %H:%M'),
                    'can_delete': current_user.is_authenticated and current_user.is_admin,
                }
                for c in sorted(self.comments, key=lambda c: c.date, reverse=True)
            ],
        }


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('works.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)


class Like(db.Model):
    __tablename__ = 'likes'
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey('works.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('work_id', 'user_id', name='uq_like_work_user'),
    )


class SiteStatus(db.Model):
    """Единственная строка — текущий 'живой' статус автора."""
    __tablename__ = 'site_status'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False, default=DEFAULT_STATUS_TEXT)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class SupportMessage(db.Model):
    """Обращения через форму поддержки (СОП — сообщения от поддержки)."""
    __tablename__ = 'support_messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending | approved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False, nullable=False)


class ChatMessage(db.Model):
    """Личный чат пользователя с администратором (СОЛ — сообщения от людей)."""
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # с кем беседа
    sender_is_admin = db.Column(db.Boolean, default=False, nullable=False)
    text = db.Column(db.Text, nullable=True, default='')
    image_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# --------------------------------------------------------------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def admin_required(view_func):
    from functools import wraps

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def slugify(name):
    import re
    s = name.strip().lower()
    s = re.sub(r'[^a-zа-я0-9]+', '-', s, flags=re.IGNORECASE | re.UNICODE)
    s = s.strip('-')
    return s or 'tag'


def get_site_status():
    status = SiteStatus.query.get(1)
    if not status:
        status = SiteStatus(id=1, text=DEFAULT_STATUS_TEXT)
        db.session.add(status)
        db.session.commit()
    return status


def is_ajax():
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )


@app.context_processor
def inject_globals():
    unread_count = 0
    if current_user.is_authenticated:
        unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return {
        'site_status_text': get_site_status().text,
        'unread_notifications': unread_count,
        'all_tags': Tag.query.order_by(Tag.name).all(),
    }


# --------------------------------------------------------------------------
# ПУБЛИЧНЫЕ СТРАНИЦЫ
# --------------------------------------------------------------------------

@app.route('/')
def index():
    category = request.args.get('cat', 'all')
    query = Work.query.order_by(Work.date.desc())
    if category != 'all':
        query = query.filter_by(category=category)
    works = query.all()
    return render_template('index.html', works=works, active_filter=category)


@app.route('/work/<int:work_id>')
def work_detail(work_id):
    work = Work.query.get_or_404(work_id)
    work.views += 1
    db.session.commit()
    comments = Comment.query.filter_by(work_id=work.id).order_by(Comment.date.desc()).all()
    return render_template('work.html', work=work, comments=comments)


@app.route('/api/work/<int:work_id>')
def api_work_detail(work_id):
    """Отдаёт данные работы для полноэкранного лайтбокса без перезагрузки страницы."""
    work = Work.query.get_or_404(work_id)
    work.views += 1
    db.session.commit()
    return jsonify({'ok': True, 'work': work.to_dict()})


@app.route('/work/<int:work_id>/like', methods=['POST'])
@login_required
def toggle_like(work_id):
    work = Work.query.get_or_404(work_id)
    existing = Like.query.filter_by(work_id=work.id, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(Like(work_id=work.id, user_id=current_user.id))
        liked = True
    db.session.commit()
    return jsonify({'ok': True, 'liked': liked, 'like_count': work.like_count})


@app.route('/work/<int:work_id>/comment', methods=['POST'])
@login_required
def add_comment(work_id):
    work = Work.query.get_or_404(work_id)
    text = (request.form.get('text') or '').strip()

    if not text:
        message = 'Комментарий не может быть пустым.'
        if is_ajax():
            return jsonify({'ok': False, 'error': message}), 400
        flash(message, 'error')
    elif len(text) > 1000:
        message = 'Комментарий слишком длинный (максимум 1000 символов).'
        if is_ajax():
            return jsonify({'ok': False, 'error': message}), 400
        flash(message, 'error')
    else:
        c = Comment(work_id=work.id, user_id=current_user.id, text=text)
        db.session.add(c)
        db.session.commit()
        if is_ajax():
            return jsonify({
                'ok': True,
                'comment': {
                    'id': c.id,
                    'author': current_user.username,
                    'text': c.text,
                    'date': c.date.strftime('%d.%m.%Y %H:%M'),
                    'can_delete': current_user.is_admin,
                },
                'comment_count': work.comment_count,
            })
        flash('Комментарий добавлен!', 'success')

    if is_ajax():
        return jsonify({'ok': False, 'error': 'Не удалось отправить комментарий.'}), 400
    return redirect(url_for('work_detail', work_id=work.id) + '#comments')


# --------------------------------------------------------------------------
# РЕГИСТРАЦИЯ / ВХОД / ВЫХОД
# --------------------------------------------------------------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        password = request.form.get('password') or ''
        password2 = request.form.get('password2') or ''

        error = None
        if len(username) < 3:
            error = 'Имя пользователя должно быть не короче 3 символов.'
        elif len(password) < 6:
            error = 'Пароль должен быть не короче 6 символов.'
        elif password != password2:
            error = 'Пароли не совпадают.'
        elif User.query.filter_by(username=username).first():
            error = 'Такое имя пользователя уже занято.'
        elif email and User.query.filter_by(email=email).first():
            error = 'Этот email уже используется.'

        if error:
            flash(error, 'error')
            return render_template('register.html', username=username, email=email)

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Добро пожаловать! Регистрация прошла успешно.', 'success')
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Вы вошли в аккаунт.', 'success')
            next_url = request.args.get('next')
            return redirect(next_url or url_for('index'))
        flash('Неверное имя пользователя или пароль.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из аккаунта.', 'success')
    return redirect(url_for('index'))


# --------------------------------------------------------------------------
# ПОДДЕРЖКА И УВЕДОМЛЕНИЯ (для обычных пользователей)
# --------------------------------------------------------------------------

@app.route('/support', methods=['GET', 'POST'])
@login_required
def support():
    if request.method == 'POST':
        text = (request.form.get('text') or '').strip()
        if not text:
            flash('Опишите вопрос или проблему перед отправкой.', 'error')
        else:
            db.session.add(SupportMessage(user_id=current_user.id, text=text))
            db.session.commit()
            flash('Обращение отправлено! Мы ответим, как только рассмотрим его.', 'success')
            return redirect(url_for('support'))
    my_messages = SupportMessage.query.filter_by(user_id=current_user.id) \
        .order_by(SupportMessage.created_at.desc()).all()
    return render_template('support.html', my_messages=my_messages)


@app.route('/notifications')
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id) \
        .order_by(Notification.created_at.desc()).all()
    unread_ids = [n.id for n in items if not n.is_read]
    if unread_ids:
        Notification.query.filter(Notification.id.in_(unread_ids)).update(
            {'is_read': True}, synchronize_session=False)
        db.session.commit()
    return render_template('notifications.html', items=items)


@app.route('/api/notifications/unread_count')
@login_required
def api_notifications_unread_count():
    """Опрашивается раз в несколько секунд с фронта — счётчик непрочитанных
    уведомлений без пометки 'прочитано' (в отличие от страницы /notifications)."""
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'ok': True, 'unread': count})


def _chat_message_to_dict(m):
    return {
        'id': m.id,
        'text': m.text or '',
        'image_url': url_for('static', filename='uploads/' + m.image_filename) if m.image_filename else None,
        'sender_is_admin': m.sender_is_admin,
        'created_at': m.created_at.strftime('%d.%m.%Y %H:%M'),
    }


@app.route('/api/chat/messages')
@login_required
def api_chat_messages():
    """Опрос новых сообщений в личном чате пользователя с админом.
    ?after_id=N — вернуть только сообщения с id > N."""
    after_id = request.args.get('after_id', type=int, default=0)
    messages = ChatMessage.query.filter(
        ChatMessage.user_id == current_user.id,
        ChatMessage.id > after_id,
    ).order_by(ChatMessage.created_at.asc()).all()
    return jsonify({'ok': True, 'messages': [_chat_message_to_dict(m) for m in messages]})


@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if request.method == 'POST':
        text = (request.form.get('text') or '').strip()
        file = request.files.get('image')
        image_name = None
        if file and file.filename:
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                image_name = f"chat_{int(datetime.utcnow().timestamp())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_name))
            else:
                flash('Недопустимый формат файла.', 'error')
        if text or image_name:
            db.session.add(ChatMessage(
                user_id=current_user.id, sender_is_admin=False,
                text=text, image_filename=image_name,
            ))
            db.session.commit()
        return redirect(url_for('chat'))

    messages = ChatMessage.query.filter_by(user_id=current_user.id) \
        .order_by(ChatMessage.created_at.asc()).all()
    return render_template('chat.html', messages=messages, other_name='Администратор',
                            send_url=url_for('chat'))


# --------------------------------------------------------------------------
# АДМИН-ПАНЕЛЬ
# --------------------------------------------------------------------------

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    works = Work.query.order_by(Work.date.desc()).all()
    comments = Comment.query.order_by(Comment.date.desc()).limit(50).all()
    tags = Tag.query.order_by(Tag.name).all()
    pending_support = SupportMessage.query.filter_by(status='pending') \
        .order_by(SupportMessage.created_at.desc()).all()
    approved_support = SupportMessage.query.filter_by(status='approved') \
        .order_by(SupportMessage.created_at.desc()).limit(20).all()

    # список бесед: уникальные пользователи, которые писали в чат
    chat_user_ids = [row[0] for row in db.session.query(ChatMessage.user_id).distinct().all()]
    chats = []
    for uid in chat_user_ids:
        u = User.query.get(uid)
        if not u:
            continue
        last = ChatMessage.query.filter_by(user_id=uid).order_by(ChatMessage.created_at.desc()).first()
        unread = ChatMessage.query.filter_by(user_id=uid, sender_is_admin=False).count()
        chats.append({'user': u, 'last': last})
    chats.sort(key=lambda c: c['last'].created_at if c['last'] else datetime.min, reverse=True)

    stats = {
        'works': Work.query.count(),
        'users': User.query.count(),
        'comments': Comment.query.count(),
        'likes': Like.query.count(),
        'views': db.session.query(db.func.sum(Work.views)).scalar() or 0,
    }
    return render_template(
        'admin/dashboard.html', works=works, comments=comments, stats=stats,
        tags=tags, pending_support=pending_support, approved_support=approved_support,
        chats=chats, site_status=get_site_status(),
    )


@app.route('/admin/status', methods=['POST'])
@login_required
@admin_required
def admin_update_status():
    text = (request.form.get('status_text') or '').strip()
    if text:
        status = get_site_status()
        status.text = text[:200]
        status.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Статус обновлён.', 'success')
    return redirect(url_for('admin_dashboard') + '#status')


@app.route('/admin/tags/new', methods=['POST'])
@login_required
@admin_required
def admin_new_tag():
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Введите название вкладки.', 'error')
        return redirect(url_for('admin_dashboard') + '#tags')
    slug = slugify(name)
    base_slug, i = slug, 2
    while Tag.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{i}"
        i += 1
    db.session.add(Tag(name=name, slug=slug))
    db.session.commit()
    flash(f'Вкладка «{name}» создана и уже доступна в фильтрах.', 'success')
    return redirect(url_for('admin_dashboard') + '#tags')


@app.route('/admin/tags/<int:tag_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    db.session.delete(tag)
    db.session.commit()
    flash('Вкладка удалена. Работы с этой категорией остаются на сайте, но метка больше не отображается.', 'success')
    return redirect(url_for('admin_dashboard') + '#tags')


@app.route('/admin/work/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_new_work():
    tags = Tag.query.order_by(Tag.name).all()
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        category = request.form.get('category') or (tags[0].slug if tags else 'digital')
        external_url = (request.form.get('image_url') or '').strip()
        file = request.files.get('image_file')

        image_value = None
        if file and file.filename:
            if not allowed_file(file.filename):
                flash('Недопустимый формат файла. Разрешены: png, jpg, jpeg, gif, webp.', 'error')
                return render_template('admin/work_form.html', work=None, tags=tags)
            filename = secure_filename(file.filename)
            unique_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            image_value = unique_name
        elif external_url:
            image_value = external_url

        if not title or not image_value:
            flash('Укажите название и загрузите фото (или вставьте ссылку на изображение).', 'error')
            return render_template('admin/work_form.html', work=None, tags=tags)

        work = Work(title=title, description=description, category=category, image_url=image_value)
        db.session.add(work)
        db.session.commit()
        flash('Работа добавлена!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/work_form.html', work=None, tags=tags)


@app.route('/admin/work/<int:work_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_work(work_id):
    work = Work.query.get_or_404(work_id)
    tags = Tag.query.order_by(Tag.name).all()
    if request.method == 'POST':
        work.title = (request.form.get('title') or work.title).strip()
        work.description = (request.form.get('description') or '').strip()
        work.category = request.form.get('category') or work.category
        external_url = (request.form.get('image_url') or '').strip()
        file = request.files.get('image_file')

        if file and file.filename:
            if not allowed_file(file.filename):
                flash('Недопустимый формат файла.', 'error')
                return render_template('admin/work_form.html', work=work, tags=tags)
            filename = secure_filename(file.filename)
            unique_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            work.image_url = unique_name
        elif external_url:
            work.image_url = external_url

        db.session.commit()
        flash('Работа обновлена.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/work_form.html', work=work, tags=tags)


@app.route('/admin/work/<int:work_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_work(work_id):
    work = Work.query.get_or_404(work_id)
    db.session.delete(work)
    db.session.commit()
    flash('Работа удалена.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    flash('Комментарий удалён.', 'success')
    next_url = request.form.get('next') or url_for('admin_dashboard')
    return redirect(next_url)


@app.route('/admin/support/<int:message_id>/approve', methods=['POST'])
@login_required
@admin_required
def admin_approve_support(message_id):
    """Галочка одобрения: пользователю уходит уведомление."""
    msg = SupportMessage.query.get_or_404(message_id)
    if msg.status != 'approved':
        msg.status = 'approved'
        db.session.add(Notification(
            user_id=msg.user_id,
            text='Ваш отзыв был одобрен',
        ))
        db.session.commit()
        flash('Обращение одобрено, пользователь получил уведомление.', 'success')
    return redirect(url_for('admin_dashboard') + '#support')


@app.route('/admin/support/<int:message_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_support(message_id):
    msg = SupportMessage.query.get_or_404(message_id)
    db.session.delete(msg)
    db.session.commit()
    flash('Обращение удалено.', 'success')
    return redirect(url_for('admin_dashboard') + '#support')


@app.route('/admin/api/chat/<int:user_id>/messages')
@login_required
@admin_required
def admin_api_chat_messages(user_id):
    """То же самое, но для админа — опрос конкретной беседы."""
    after_id = request.args.get('after_id', type=int, default=0)
    messages = ChatMessage.query.filter(
        ChatMessage.user_id == user_id,
        ChatMessage.id > after_id,
    ).order_by(ChatMessage.created_at.asc()).all()
    return jsonify({'ok': True, 'messages': [_chat_message_to_dict(m) for m in messages]})


@app.route('/admin/api/chats/summary')
@login_required
@admin_required
def admin_api_chats_summary():
    """Опрос списка бесед в дашборде: есть ли новые непрочитанные сообщения
    от пользователей и какое сообщение последнее."""
    chat_user_ids = [row[0] for row in db.session.query(ChatMessage.user_id).distinct().all()]
    result = []
    for uid in chat_user_ids:
        u = User.query.get(uid)
        if not u:
            continue
        last = ChatMessage.query.filter_by(user_id=uid).order_by(ChatMessage.created_at.desc()).first()
        unread = ChatMessage.query.filter_by(user_id=uid, sender_is_admin=False).count()
        result.append({
            'user_id': uid,
            'username': u.username,
            'last_text': (last.text or ('[фото]' if last.image_filename else '')) if last else '',
            'last_at': last.created_at.strftime('%d.%m.%Y %H:%M') if last else '',
            'last_id': last.id if last else 0,
        })
    result.sort(key=lambda c: c['last_id'], reverse=True)
    return jsonify({'ok': True, 'chats': result})


@app.route('/admin/chat/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_chat(user_id):
    target_user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        text = (request.form.get('text') or '').strip()
        file = request.files.get('image')
        image_name = None
        if file and file.filename:
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                image_name = f"chat_{int(datetime.utcnow().timestamp())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_name))
            else:
                flash('Недопустимый формат файла.', 'error')
        if text or image_name:
            db.session.add(ChatMessage(
                user_id=target_user.id, sender_is_admin=True,
                text=text, image_filename=image_name,
            ))
            db.session.commit()
        return redirect(url_for('admin_chat', user_id=user_id))

    messages = ChatMessage.query.filter_by(user_id=target_user.id) \
        .order_by(ChatMessage.created_at.asc()).all()
    return render_template('chat.html', messages=messages, other_name=target_user.username,
                            send_url=url_for('admin_chat', user_id=user_id), is_admin_view=True,
                            target_user=target_user)


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


# --------------------------------------------------------------------------
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ + ДЕМО-ДАННЫЕ
# --------------------------------------------------------------------------

SEED_WORKS = [
    ('Арт для конкурса', 'digital', 'https://i.postimg.cc/8khMJ4n8/photo-2026-03-28-11-47-21.jpg'),
    ('Первый традиционный арт', 'traditional', 'https://i.postimg.cc/bJf0WBFg/photo-2026-05-26-08-05-19.jpg'),
    ('Исполнил мечту детства', 'photo', 'https://i.postimg.cc/sgZhzJWm/photo-2026-07-03-16-22-45.jpg'),
    ('Новая покупка!!!', 'photo', 'https://i.postimg.cc/X71zmnKD/photo-2026-05-29-13-55-28.jpg'),
    ('Качок', 'digital', 'https://i.postimg.cc/qRbK4BJr/photo-2026-05-14-21-34-06.jpg'),
    ('картина гуашью за 30 минут', 'traditional', 'https://i.postimg.cc/PrHL4FmX/photo-2026-07-23-16-05-49.jpg'),
    ('Скетчбук', 'traditional', 'https://i.postimg.cc/4dMGXpV0/photo-2026-05-30-20-38-22.jpg'),
    ('Трагг из неуязвимый', 'digital', 'https://i.postimg.cc/xCdjf07f/photo-2026-04-08-07-40-35.jpg'),
    ('Пейзаж', 'traditional', 'https://i.postimg.cc/mrk2RLKM/photo-2026-05-27-12-04-53.jpg'),
    ('Что-то по аватару', 'digital', 'https://i.postimg.cc/rwP21SYT/photo-2026-04-29-15-10-50.jpg'),
    ('Незаконченный скетч', 'digital', 'https://i.postimg.cc/SNWWzhVv/photo-2026-06-06-22-51-16.jpg'),
    ('Супер мен)))', 'digital', 'https://i.postimg.cc/hv51ytF9/photo-2026-04-11-15-43-05.jpg'),
    ('В честь легенды', 'traditional', 'https://i.postimg.cc/NMYD50v6/photo-2026-06-15-18-11-14.jpg'),
    ('Помни из УЦЦ', 'digital', 'https://i.postimg.cc/Qd3J6tH8/photo-2026-06-20-14-23-56-(2).jpg'),
]


def init_db():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(username=DEFAULT_ADMIN_USERNAME).first():
            admin = User(
                username=DEFAULT_ADMIN_USERNAME,
                email=DEFAULT_ADMIN_EMAIL,
                is_admin=True,
            )
            admin.set_password(DEFAULT_ADMIN_PASSWORD)
            db.session.add(admin)
            db.session.commit()
            print(f"[i] Создан администратор: логин '{DEFAULT_ADMIN_USERNAME}', "
                  f"пароль '{DEFAULT_ADMIN_PASSWORD}' — ОБЯЗАТЕЛЬНО смените после входа!")

        if Tag.query.count() == 0:
            for name, slug in DEFAULT_TAGS:
                db.session.add(Tag(name=name, slug=slug))
            db.session.commit()
            print(f"[i] Созданы стандартные вкладки: {', '.join(n for n, _ in DEFAULT_TAGS)}")

        if Work.query.count() == 0:
            for title, category, img in SEED_WORKS:
                db.session.add(Work(title=title, description='', category=category, image_url=img))
            db.session.commit()
            print(f"[i] Загружено {len(SEED_WORKS)} демо-работ из старого сайта.")

        if not SiteStatus.query.get(1):
            db.session.add(SiteStatus(id=1, text=DEFAULT_STATUS_TEXT))
            db.session.commit()


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='127.0.0.1', port=5000)
