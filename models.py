from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

# ИНИЦИАЛИЗАЦИЯ БД
db = SQLAlchemy()


# ================== USER ==================
class User(db.Model, UserMixin):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    avatar = db.Column(db.String(255), nullable=True)



    confirmed = db.Column(db.Boolean, default=False)

    # связь с транзакциями
    transactions = db.relationship('Transaction', backref='user', lazy=True)


# ================== CATEGORY ==================
class Category(db.Model):
    __tablename__ = 'category'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # income / expense

    # 🔥 ЛИМИТ НА МЕСЯЦ
    limit = db.Column(db.Float, default=0)

    transactions = db.relationship('Transaction', backref='category', lazy=True)



# ================== TRANSACTION ==================
class Transaction(db.Model):
    __tablename__ = 'transaction'

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    comment = db.Column(db.String(255))

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey('category.id'),
        nullable=False
    )
