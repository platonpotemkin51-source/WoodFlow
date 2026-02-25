from datetime import datetime, UTC
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """описание пользователя"""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(150), default="")
    is_admin = db.Column(db.Boolean, default=False)
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Flask-Login требует
    @property
    def is_active(self):
        return self.is_active_user


class WoodPack(db.Model):
    """описание пачки"""
    __tablename__ = "wood_packs"

    id = db.Column(db.Integer, primary_key=True)
    #---
    # species = db.Column(db.String(50), nullable=False)        # порода
    # wood_type = db.Column(db.String(50), default="")           # доска, брус …
    # grade = db.Column(db.String(20), default="")               # сорт
    # width = db.Column(db.Float, nullable=False)                # мм
    # thickness = db.Column(db.Float, nullable=False)            # мм
    # length = db.Column(db.Float, nullable=False)               # м
    # quantity = db.Column(db.Integer, nullable=False)            # шт в пачке
    # volume = db.Column(db.Float, nullable=False)               # м³
    # price_per_m3 = db.Column(db.Float, default=0)              # руб
    #---
    status = db.Column(db.String(20), default="на_складе")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=True)

    # ---
    number_pac = db.Column(db.String(16), default="")  # номер пачки
    grade = db.Column(db.String(10), default="")  # сорт
    #---
    width_nominal = db.Column(db.Float, nullable=False)  # мм
    width_fact_for_tam = db.Column(db.Float, nullable=False)  # мм
    width_fact_for_pok = db.Column(db.Float, nullable=False)  # мм
    #---
    thickness_nominal = db.Column(db.Float, nullable=False)  # мм
    thickness_fact_for_tam = db.Column(db.Float, nullable=False)  # мм
    thickness_fact_for_pok = db.Column(db.Float, nullable=False)  # мм
    #---
    length_nominal = db.Column(db.Float, nullable=False)  # мм
    length_fact_for_tam = db.Column(db.Float, nullable=False)  # мм
    length_fact_for_pok = db.Column(db.Float, nullable=False)  # мм
    #---
    quantity = db.Column(db.Integer, nullable=False)  # шт в пачке
    quantity_layers = db.Column(db.Integer, nullable=False) # количество слоев
    quantity_in_layer = db.Column(db.Integer, nullable=False) # количество в слою
    #---
    # volume = db.Column(db.Float, nullable=False)  # м³
    # weight = db.Column(db.Float, nullable=False)  # кг
    # ---

    @property
    def volume_nominal(self):
            return self.width_nominal*self.thickness_nominal*self.length_nominal*self.quantity*(10**(-6))*(10**(-6))*(10**(-6))     # м³

    @property
    def volume_fact_for_tam(self):
        return self.width_fact_for_tam * self.thickness_fact_for_tam * self.length_fact_for_tam * self.quantity * (10 ** (-6)) * (10 ** (-6)) * (10 ** (-6))    # м³

    @property
    def volume_fact_for_pok(self):
        return self.width_fact_for_pok*self.thickness_fact_for_pok*self.length_fact_for_pok*self.quantity*(10**(-6))*(10**(-6))*(10**(-6))      # м³

    @property
    def weight_nominal(self):
        return self.volume_nominal()*630    # кг

    @property
    def weight_fact_for_tam(self):
        return self.volume_fact_for_tam() * 630     # кг

    @property
    def weight_fact_for_pok(self):
        return self.volume_fact_for_pok() * 630     # кг


class Booking(db.Model):
    """описание сформированной машины"""
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), unique=True, nullable=False)
    company_name = db.Column(db.String(150), default="")
    adres = db.Column(db.String(250), default="")
    status = db.Column(db.String(20), default="активная")      # активная / отправлена / отменена
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    price_per_m3 = db.Column(db.Float, default=0)  # руб
    contract = db.Column(db.String(50), default="")


    packs = db.relationship("WoodPack", backref="booking", lazy=True)
    shipment = db.relationship("Shipment", backref="booking", uselist=False)

    @property
    def total_volume_nominal(self):
        return round(sum(p.volume_nominal for p in self.packs), 4)

    @property
    def total_volume_fact_for_tam(self):
        return round(sum(p.volume_fact_for_tam for p in self.packs), 4)

    @property
    def total_volume_fact_for_pok(self):
        return round(sum(p.volume_fact_for_pok for p in self.packs), 4)

    @property
    def total_weight_nominal(self):
        return self.total_volume_nominal * 630

    @property
    def total_weight_fact_for_tam(self):
        return self.total_volume_fact_for_tam * 630

    @property
    def total_weight_fact_for_pok(self):
        return self.total_volume_fact_for_pok * 630

    @property
    def total_price(self):
        # return round(sum(p.volume * p.price_per_m3 for p in self.packs), 2)
        return round(self.total_volume_fact_for_pok * self.price_per_m3 , 2)

    @property
    def pack_count(self):
        return len(self.packs)


class Shipment(db.Model):
    """описание машины"""
    __tablename__ = "shipments"

    id = db.Column(db.Integer, primary_key=True)
    # booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False)
    # driver_name = db.Column(db.String(150), default="")
    # truck_number = db.Column(db.String(50), default="")
    # destination = db.Column(db.String(250), default="")
    # total_volume = db.Column(db.Float, default=0)
    # total_price = db.Column(db.Float, default=0)
    # shipped_at = db.Column(db.DateTime, default=datetime.now(UTC))
    # notes = db.Column(db.Text, default="")
    # created_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=False)
    # ---
    car_number = db.Column(db.String(50), default="")
    trailer_number = db.Column(db.String(50), default="")
    plomb_number = db.Column(db.String(50), default="")
    # ---
    shipped_at = db.Column(db.DateTime, default=datetime.now(UTC))
    notes = db.Column(db.Text, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))