import os
import secrets
import time
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path

import click
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from PIL import Image, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder='assets')
Path(app.instance_path).mkdir(exist_ok=True)
secret_file = Path(app.instance_path) / 'secret.key'
if not secret_file.exists():
    secret_file.write_text(secrets.token_hex(32))

_db_url = os.environ.get('DATABASE_URL', 'sqlite:///onlyflan.db')
# Normalizar a postgresql+psycopg:// para SQLAlchemy
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif _db_url.startswith('postgresql://'):
    _db_url = _db_url.replace('postgresql://', 'postgresql+psycopg://', 1)

app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY') or secret_file.read_text().strip(),
    SQLALCHEMY_DATABASE_URI=_db_url,
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('HTTPS_ONLY') == '1',
)
db = SQLAlchemy(app)
CSRFProtect(app)
login = LoginManager(app)
login.login_view = 'sign_in'
login.login_message = 'Inicia sesión para continuar.'
login.session_protection = 'strong'
attempts = defaultdict(deque)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='seller')
    active = db.Column(db.Boolean, default=True, nullable=False)

    @property
    def is_active(self):
        return self.active


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(600), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    decoration_price = db.Column(db.Numeric(10, 2), nullable=True)
    image = db.Column(db.String(200), nullable=False)
    available = db.Column(db.Boolean, default=True, nullable=False)


class Setting(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(200), nullable=False)


@login.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    return user if user and user.active else None


def admin_only(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != 'admin':
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def phone():
    value = db.session.get(Setting, 'whatsapp')
    return value.value if value else '59157002285'


@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; form-action 'self'; base-uri 'self'; frame-ancestors 'none'"
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if os.environ.get('HTTPS_ONLY') == '1':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    if request.path.startswith(('/panel', '/ingresar')):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/')
def home():
    products = db.session.scalars(db.select(Product).where(Product.available.is_(True)).order_by(Product.id)).all()
    prices = {p.price for p in products}
    return render_template('home.html', products=products, starting_price=min(prices) if prices else None, same_price=len(prices) == 1)


@app.route('/api/catalogo')
def catalog():
    products = db.session.scalars(db.select(Product).where(Product.available.is_(True)).order_by(Product.id)).all()
    return jsonify(whatsapp=phone(), products=[dict(id=p.id, name=p.name, price=str(p.price), decoration_price=str(p.decoration_price) if p.decoration_price is not None else None, image=url_for('static', filename=p.image)) for p in products])


@app.route('/ingresar', methods=['GET', 'POST'])
def sign_in():
    if current_user.is_authenticated:
        return redirect(url_for('panel'))
    if request.method == 'POST':
        key = request.remote_addr
        queue = attempts[key]
        now = time.monotonic()
        while queue and now - queue[0] > 300:
            queue.popleft()
        if not queue:
            del attempts[key]
        if len(queue) >= 10:
            flash('Demasiados intentos. Espera cinco minutos.', 'error')
            return render_template('login.html'), 429
        attempts[key].append(now)
        user = db.session.scalar(db.select(User).where(User.username == request.form.get('username', '').strip().lower()))
        valid = check_password_hash(user.password_hash if user else generate_password_hash('dummy'), request.form.get('password', ''))
        if user and user.active and valid:
            queue.clear()
            login_user(user)
            return redirect(url_for('panel'))
        flash('Usuario o contraseña incorrectos.', 'error')
    return render_template('login.html')


@app.post('/salir')
@login_required
def sign_out():
    logout_user()
    return redirect(url_for('home'))


@app.route('/panel')
@login_required
def panel():
    return render_template('panel.html', products=db.session.scalars(db.select(Product).order_by(Product.id)).all(), users=db.session.scalars(db.select(User).where(User.role == 'seller')).all() if current_user.role == 'admin' else [], admins=db.session.scalars(db.select(User).where(User.role == 'admin')).all() if current_user.role == 'admin' else [], whatsapp=phone())


@app.post('/panel/productos/<int:pid>/estado')
@login_required
def availability(pid):
    p = db.get_or_404(Product, pid)
    if request.form.get('available') not in ('0', '1'):
        abort(400)
    p.available = request.form['available'] == '1'
    db.session.commit()
    flash('Disponibilidad actualizada.', 'success')
    return redirect(url_for('panel'))


def save_image(upload):
    try:
        with Image.open(upload.stream) as img:
            if img.width * img.height > 30_000_000:
                raise ValueError('La imagen es demasiado grande.')
            img.load()
            img = img.convert('RGB')
            img.thumbnail((1800, 1800))
            folder = ROOT / 'assets' / 'uploads'
            folder.mkdir(exist_ok=True)
            name = secrets.token_hex(16) + '.webp'
            img.save(folder / name, 'WEBP', quality=90)
        return 'uploads/' + name
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError('Selecciona una imagen JPG, PNG o WebP válida.')


@app.route('/panel/productos/nuevo', methods=['GET', 'POST'])
@app.route('/panel/productos/<int:pid>/editar', methods=['GET', 'POST'])
@admin_only
def edit_product(pid=None):
    p = db.get_or_404(Product, pid) if pid else None
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            price = Decimal(request.form.get('price', ''))
            decoration_price = None
            if request.form.get('decoration_enabled') == 'on':
                decoration_price = Decimal(request.form.get('decoration_price', ''))
                if not decoration_price.is_finite() or decoration_price < 0 or decoration_price > 999999 or decoration_price != decoration_price.quantize(Decimal('.01')):
                    raise ValueError('Ingresa un adicional válido para Más decorado, con máximo dos decimales.')
            if not name or len(name) > 120 or not description or len(description) > 600:
                raise ValueError('Completa el nombre y la descripción dentro de los límites indicados.')
            if not price.is_finite() or price <= 0 or price > 999999 or price != price.quantize(Decimal('.01')):
                raise ValueError('Ingresa un precio válido, con un máximo de dos decimales.')
            upload = request.files.get('image')
            if not p and (not upload or not upload.filename):
                raise ValueError('Agrega una fotografía al producto.')
            image = save_image(upload) if upload and upload.filename else p.image
            if not p:
                p = Product()
                db.session.add(p)
            p.name, p.description, p.price, p.image = name, description, price, image
            p.decoration_price = decoration_price
            p.available = request.form.get('available') == 'on'
            db.session.commit()
            flash('Producto guardado.', 'success')
            return redirect(url_for('panel'))
        except (ValueError, InvalidOperation) as exc:
            flash(str(exc) if isinstance(exc, ValueError) else 'Precio inválido.', 'error')
    return render_template('product.html', product=p)


@app.post('/panel/productos/<int:pid>/eliminar')
@admin_only
def delete_product(pid):
    p = db.get_or_404(Product, pid)
    image_path = p.image
    db.session.delete(p)
    db.session.commit()
    if image_path.startswith('uploads/'):
        try:
            (ROOT / 'assets' / image_path).unlink(missing_ok=True)
        except OSError:
            pass
    flash('Producto eliminado.', 'success')
    return redirect(url_for('panel'))


@app.post('/panel/vendedores')
@admin_only
def create_seller():
    name = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')
    if not name or len(name) > 80 or len(password) < 10:
        flash('Indica un usuario y una contraseña de al menos 10 caracteres.', 'error')
    elif db.session.scalar(db.select(User).where(User.username == name)):
        flash('Ese usuario ya existe.', 'error')
    else:
        db.session.add(User(username=name, password_hash=generate_password_hash(password), role='seller'))
        db.session.commit()
        flash('Vendedor creado.', 'success')
    return redirect(url_for('panel'))


@app.post('/panel/admins')
@admin_only
def create_admin_user():
    name = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')
    if not name or len(name) > 80 or len(password) < 10:
        flash('Indica un usuario y una contraseña de al menos 10 caracteres.', 'error')
    elif db.session.scalar(db.select(User).where(User.username == name)):
        flash('Ese usuario ya existe.', 'error')
    else:
        db.session.add(User(username=name, password_hash=generate_password_hash(password), role='admin'))
        db.session.commit()
        flash('Administrador creado.', 'success')
    return redirect(url_for('panel'))


@app.post('/panel/vendedores/<int:uid>/estado')
@admin_only
def seller_status(uid):
    user = db.get_or_404(User, uid)
    if user.role != 'seller':
        abort(403)
    user.active = not user.active
    db.session.commit()
    return redirect(url_for('panel'))


@app.post('/panel/configuracion')
@admin_only
def settings():
    number = request.form.get('whatsapp', '').replace('+', '').replace(' ', '')
    if not number.isascii() or not number.isdigit() or not 8 <= len(number) <= 15:
        flash('Ingresa el número con código de país, solo dígitos.', 'error')
    else:
        value = db.session.get(Setting, 'whatsapp') or Setting(key='whatsapp')
        value.value = number
        db.session.add(value)
        db.session.commit()
        flash('WhatsApp actualizado.', 'success')
    return redirect(url_for('panel'))


@app.cli.command('init-db')
def init_db():
    db.create_all()
    migrate_schema()
    if not db.session.scalar(db.select(Product.id).limit(1)):
        entries = [
            ('Clásico de vainilla', 'El clásico que enamora: suave vainilla bañada en caramelo.', 'clasico-vainilla'),
            ('Vainilla y café', 'La suavidad de la vainilla con el carácter del café.', 'vainilla-cafe'),
            ('Vainilla y chocolate', 'Dos favoritos juntos: vainilla cremosa y una base de chocolate.', 'vainilla-chocolate'),
            ('Clásico con almendra', 'Nuestro clásico de vainilla con el delicado toque de la almendra.', 'clasico-almendra'),
            ('Clásico con nuez', 'Vainilla y caramelo acompañados de nuez.', 'clasico-nuez'),
            ('Flan whiskero', 'Vainilla, café y un toque de whisky.', 'flan-whiskero'),
            ('Flan añejo', 'Vainilla y un toque de ron para un sabor especial.', 'flan-anejo'),
        ]
        for name, description, image in entries:
            db.session.add(Product(name=name, description=description, price=70, image='productos/' + image + '-v1.png', available=True))
        db.session.commit()
    click.echo('Base de datos lista; catálogo inicial cargado.')


def migrate_schema():
    inspector = inspect(db.engine)
    if inspector.has_table('product') and 'decoration_price' not in {column['name'] for column in inspector.get_columns('product')}:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE product ADD COLUMN decoration_price NUMERIC(10, 2)'))


@app.cli.command('upgrade-db')
def upgrade_db():
    """Actualiza el esquema sin modificar productos ni usuarios."""
    migrate_schema()
    click.echo('Esquema actualizado.')


@app.cli.command('create-admin')
@click.option('--username', prompt='Usuario administrador')
@click.password_option(confirmation_prompt=True)
def create_admin(username, password):
    username = username.strip().lower()
    if not username or len(username) > 80 or len(password) < 10:
        raise click.ClickException('Usuario inválido o contraseña menor a 10 caracteres.')
    if db.session.scalar(db.select(User).where(User.username == username)):
        raise click.ClickException('El usuario ya existe.')
    db.session.add(User(username=username, password_hash=generate_password_hash(password), role='admin'))
    db.session.commit()
    click.echo('Administrador creado.')



with app.app_context():
    db.create_all()
    migrate_schema()

if __name__ == '__main__':
    from waitress import serve
    serve(app, host=os.environ.get('HOST', '0.0.0.0'), port=int(os.environ.get('PORT', '5000')))
