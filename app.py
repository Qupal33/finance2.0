import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, Response
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer

from models import db, User, Category, Transaction


# ================== APP ==================
app = Flask(__name__)

app.config['SECRET_KEY'] = 'secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

db.init_app(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# ================== LOGIN ==================
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ================== INIT ==================
def create_categories():
    if Category.query.first():
        return

    categories = [
        Category(name='Зарплата', type='income'),
        Category(name='Фриланс', type='income'),
        Category(name='Еда', type='expense', limit=0),
        Category(name='Транспорт', type='expense', limit=0),
        Category(name='Развлечения', type='expense', limit=0)
    ]
    db.session.add_all(categories)
    db.session.commit()


# ================== ROUTES ==================

@app.route('/')
def index():
    return redirect(url_for('dashboard'))


# ---------- REGISTER ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    message = None
    message_type = 'danger'

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        password2 = request.form['password2']

        if len(password) < 6:
            message = 'Пароль должен содержать минимум 6 символов'

        elif password != password2:
            message = 'Пароли не совпадают'

        elif User.query.filter_by(email=email).first():
            message = 'Пользователь с такой почтой уже существует'

        else:
            user = User(
                name=name,
                email=email,
                password=generate_password_hash(password),
                confirmed=False
            )
            db.session.add(user)
            db.session.commit()

            # учебное подтверждение
            token = serializer.dumps(email, salt='email-confirm')
            print('ССЫЛКА ПОДТВЕРЖДЕНИЯ:',
                  url_for('confirm_email', token=token, _external=True))

            message = 'Регистрация успешна. Подтвердите почту'
            message_type = 'success'

    return render_template(
        'auth/register.html',
        message=message,
        message_type=message_type
    )



# ---------- CONFIRM EMAIL ----------
@app.route('/confirm/<token>')
def confirm_email(token):
    email = serializer.loads(token, salt='email-confirm', max_age=3600)
    user = User.query.filter_by(email=email).first_or_404()
    user.confirmed = True
    db.session.commit()
    return redirect(url_for('login'))


# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    message = None
    message_type = 'danger'

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            message = 'Неверная почта или пароль'

        elif not user.confirmed:
            message = 'Пожалуйста, подтвердите почту перед входом'

        else:
            login_user(user)
            return redirect(url_for('dashboard'))

    return render_template(
        'auth/login.html',
        message=message,
        message_type=message_type
    )



# ---------- LOGOUT ----------
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------- DASHBOARD ----------
@app.route('/dashboard')
@login_required
def dashboard():
    start = datetime.now().replace(day=1, hour=0, minute=0, second=0)

    # доходы
    income = (
        db.session.query(func.sum(Transaction.amount))
        .join(Category)
        .filter(
            Transaction.user_id == current_user.id,
            Category.type == 'income',
            Transaction.date >= start
        ).scalar() or 0
    )

    # расходы
    expense = (
        db.session.query(func.sum(Transaction.amount))
        .join(Category)
        .filter(
            Transaction.user_id == current_user.id,
            Category.type == 'expense',
            Transaction.date >= start
        ).scalar() or 0
    )

    # 🔥 ПРОВЕРКА ЛИМИТОВ
    exceeded = []

    limits = (
        db.session.query(
            Category.name,
            Category.limit,
            func.sum(Transaction.amount)
        )
        .join(Transaction)
        .filter(
            Transaction.user_id == current_user.id,
            Category.type == 'expense',
            Category.limit > 0,
            Transaction.date >= start
        )
        .group_by(Category.id)
        .all()
    )

    for name, limit, total in limits:
        if total > limit:
            exceeded.append({
                'name': name,
                'limit': limit,
                'total': total
            })

    return render_template(
        'dashboard.html',
        income=income,
        expense=expense,
        balance=income - expense,
        exceeded=exceeded
    )



# ---------- PROFILE ----------
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        file = request.files.get('avatar')
        if file:
            filename = secure_filename(f'{current_user.id}.png')
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(path)
            current_user.avatar = filename
            db.session.commit()
    return render_template('profile.html')



# ---------- DELETE AVATAR ----------
@app.route('/profile/avatar/delete', methods=['POST'])
@login_required
def delete_avatar():
    if current_user.avatar:
        path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.avatar)
        if os.path.exists(path):
            os.remove(path)
        current_user.avatar = None
        db.session.commit()

    return redirect(url_for('profile'))


# ---------- ADD TRANSACTION ----------
@app.route('/transaction/add', methods=['GET', 'POST'])
@login_required
def add_transaction():
    categories = Category.query.all()

    if request.method == 'POST':
        date_str = request.form.get('date')
        date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.now()

        transaction = Transaction(
            amount=float(request.form['amount']),
            category_id=int(request.form['category_id']),
            user_id=current_user.id,
            comment=request.form.get('comment'),
            date=date
        )

        db.session.add(transaction)
        db.session.commit()
        return redirect(url_for('transactions'))

    return render_template(
        'finance/add.html',
        categories=categories,
        today=datetime.now().strftime('%Y-%m-%d')
    )


# ---------- LIST ----------
@app.route('/transactions')
@login_required
def transactions():
    transactions = (
        Transaction.query
        .filter_by(user_id=current_user.id)
        .order_by(Transaction.date.desc())
        .all()
    )
    return render_template('finance/list.html', transactions=transactions)


# ---------- EDIT ----------
@app.route('/transaction/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    t = Transaction.query.get_or_404(id)
    categories = Category.query.all()

    if request.method == 'POST':
        t.amount = request.form['amount']
        t.category_id = request.form['category_id']
        t.comment = request.form['comment']
        t.date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        db.session.commit()
        return redirect(url_for('transactions'))

    return render_template(
        'finance/edit.html',
        transaction=t,
        categories=categories
    )


# ---------- DELETE ----------
@app.route('/transaction/delete/<int:id>')
@login_required
def delete_transaction(id):
    t = Transaction.query.get_or_404(id)
    db.session.delete(t)
    db.session.commit()
    return redirect(url_for('transactions'))


# ---------- LIMITS ----------
@app.route('/limits', methods=['GET', 'POST'])
@login_required
def limits():
    categories = Category.query.filter_by(type='expense').all()
    if request.method == 'POST':
        for c in categories:
            c.limit = float(request.form.get(str(c.id)) or 0)
        db.session.commit()
    return render_template('finance/limits.html', categories=categories)


# ---------- STATS (CUSTOM PERIOD) ----------
@app.route('/stats')
@login_required
def stats():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    if not date_from or not date_to:
        start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
        end = datetime.now()
        label = 'Текущий месяц'
    else:
        start = datetime.strptime(date_from, '%Y-%m-%d')
        end = datetime.strptime(date_to, '%Y-%m-%d')
        label = f'{date_from} — {date_to}'

    data = (
        db.session.query(Category.name, func.sum(Transaction.amount))
        .join(Transaction)
        .filter(
            Transaction.user_id == current_user.id,
            Category.type == 'expense',
            Transaction.date >= start,
            Transaction.date <= end
        )
        .group_by(Category.name)
        .all()
    )

    return render_template(
        'finance/stats.html',
        labels=[x[0] for x in data],
        values=[float(x[1]) for x in data],
        period_label=label,
        date_from=date_from,
        date_to=date_to
    )


# ---------- EXPORT CSV ----------
@app.route('/export/csv')
@login_required
def export_csv():
    import io, csv

    transactions = Transaction.query.filter_by(
        user_id=current_user.id
    ).order_by(Transaction.date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    writer.writerow(['Дата', 'Категория', 'Тип', 'Комментарий', 'Сумма'])

    for t in transactions:
        writer.writerow([
            t.date.strftime('%d.%m.%Y'),
            t.category.name,
            'Доход' if t.category.type == 'income' else 'Расход',
            t.comment or '',
            t.amount
        ])

    return Response(
        '\ufeff' + output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=transactions.csv'}
    )


# ================== RUN ==================
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
        create_categories()
    app.run(debug=True)
