# -*- coding: utf-8 -*-
"""
ONNI_MONNI — динамический сайт-портфолио на Flask + SQLite.

Как это устроено (коротко):
- Работы (Work) хранятся в базе, у каждой есть просмотры, лайки, комментарии.
- Обычный гость может только смотреть.
- Зарегистрированный пользователь может лайкать и комментировать.
- Администратор (is_admin=True) может добавлять/редактировать/удалять работы
  и удалять чужие комментарии через панель /admin.
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

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'onni-monni-secret-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'onni.db')
# Автоматическое создание папки для загрузок картинок
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024  # 12 МБ на файл

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите, чтобы продолжить.'
login_manager.login_message_category = 'error'

# Данные администратора по умолчанию (при первом запуске).
# ВАЖНО: смените пароль после первого входа! См. инструкцию в README.
DEFAULT_ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
DEFAULT_ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'monioni60@gmail.com')
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'onni_monni_2011')

CATEGORY_LABELS = {
    'digital': 'Цифровой арт',
    'traditional': 'Традиционный арт',
    'photo': 'Фото',
}

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


class Work(db.Model):
    __tablename__ = 'works'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True, default='')
    image_url = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(30), nullable=False, default='digital')
    views = db.Column(db.Integer, default=0, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    comments = db.relationship('Comment', backref='work', lazy=True,
                                cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='work', lazy=True,
                             cascade='all, delete-orphan')

    @property
    def category_label(self):
        return CATEGORY_LABELS.get(self.category, self.category)

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
        """Отдаёт либо внешнюю ссылку (старые работы), либо путь к файлу в /static/uploads."""
        if self.image_url.startswith('http://') or self.image_url.startswith('https://'):
            return self.image_url
        return url_for('static', filename='uploads/' + self.image_url)


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


# --------------------------------------------------------------------------
# ПУБЛИЧНЫЕ СТРАНИЦЫ
# --------------------------------------------------------------------------

@app.route('/')
def index():
    category = request.args.get('cat', 'all')
    query = Work.query.order_by(Work.date.desc())
    if category in ('digital', 'traditional', 'photo'):
        query = query.filter_by(category=category)
    elif category == 'art':
        query = query.filter(Work.category.in_(['digital', 'traditional']))
    works = query.all()
    return render_template('index.html', works=works, active_filter=category)


@app.route('/work/<int:work_id>')
def work_detail(work_id):
    work = Work.query.get_or_404(work_id)
    # засчитываем один просмотр за открытие страницы
    work.views += 1
    db.session.commit()
    comments = Comment.query.filter_by(work_id=work.id).order_by(Comment.date.desc()).all()
    return render_template('work.html', work=work, comments=comments)


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
        flash('Комментарий не может быть пустым.', 'error')
    elif len(text) > 1000:
        flash('Комментарий слишком длинный (максимум 1000 символов).', 'error')
    else:
        db.session.add(Comment(work_id=work.id, user_id=current_user.id, text=text))
        db.session.commit()
        flash('Комментарий добавлен!', 'success')
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
# АДМИН-ПАНЕЛЬ
# --------------------------------------------------------------------------

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    works = Work.query.order_by(Work.date.desc()).all()
    comments = Comment.query.order_by(Comment.date.desc()).limit(50).all()
    stats = {
        'works': Work.query.count(),
        'users': User.query.count(),
        'comments': Comment.query.count(),
        'likes': Like.query.count(),
        'views': db.session.query(db.func.sum(Work.views)).scalar() or 0,
    }
    return render_template('admin/dashboard.html', works=works, comments=comments, stats=stats)


@app.route('/admin/work/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_new_work():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        category = request.form.get('category') or 'digital'
        external_url = (request.form.get('image_url') or '').strip()
        file = request.files.get('image_file')

        image_value = None
        if file and file.filename:
            if not allowed_file(file.filename):
                flash('Недопустимый формат файла. Разрешены: png, jpg, jpeg, gif, webp.', 'error')
                return render_template('admin/work_form.html', work=None)
            filename = secure_filename(file.filename)
            unique_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            image_value = unique_name
        elif external_url:
            image_value = external_url

        if not title or not image_value:
            flash('Укажите название и загрузите фото (или вставьте ссылку на изображение).', 'error')
            return render_template('admin/work_form.html', work=None)

        work = Work(title=title, description=description, category=category, image_url=image_value)
        db.session.add(work)
        db.session.commit()
        flash('Работа добавлена!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/work_form.html', work=None)


@app.route('/admin/work/<int:work_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_work(work_id):
    work = Work.query.get_or_404(work_id)
    if request.method == 'POST':
        work.title = (request.form.get('title') or work.title).strip()
        work.description = (request.form.get('description') or '').strip()
        work.category = request.form.get('category') or work.category
        external_url = (request.form.get('image_url') or '').strip()
        file = request.files.get('image_file')

        if file and file.filename:
            if not allowed_file(file.filename):
                flash('Недопустимый формат файла.', 'error')
                return render_template('admin/work_form.html', work=work)
            filename = secure_filename(file.filename)
            unique_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            work.image_url = unique_name
        elif external_url:
            work.image_url = external_url

        db.session.commit()
        flash('Работа обновлена.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/work_form.html', work=work)


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
    work_id = comment.work_id
    db.session.delete(comment)
    db.session.commit()
    flash('Комментарий удалён.', 'success')
    next_url = request.form.get('next') or url_for('admin_dashboard')
    return redirect(next_url)


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


# --------------------------------------------------------------------------
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ + ДЕМО-ДАННЫЕ (на основе старого сайта)
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

        if Work.query.count() == 0:
            for title, category, img in SEED_WORKS:
                db.session.add(Work(title=title, description='', category=category, image_url=img))
            db.session.commit()
            print(f"[i] Загружено {len(SEED_WORKS)} демо-работ из старого сайта.")


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Автоматическое создание всех таблиц при старте
    app.run(debug=True)

