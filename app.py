import os
from datetime import datetime, UTC

from flask import (
    Flask, render_template, redirect, url_for,
    request, flash, send_file, jsonify,
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user,
)
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, extract

from config import Config
from models import db, User, WoodPack, Booking, Shipment
from excel_utils import generate_shipment_excel

# ──────────────────────────────────────────────
#  Инициализация приложения
# ──────────────────────────────────────────────
app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Пожалуйста, войдите в систему."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    """логинит пользователя в сессии"""
    return db.session.get(User, int(user_id))


# ──────────────────────────────────────────────
#  Вспомогательные функции
# ──────────────────────────────────────────────
def calc_volume(width_mm, thickness_mm, length_m, qty):
    """Объём пачки в м³."""
    return round((width_mm / 1000) * (thickness_mm / 1000) * length_m * qty, 4)


def generate_booking_number():
    """генерирует название брони"""
    year = datetime.now(UTC).year
    last = (
        Booking.query
        .filter(extract("year", Booking.created_at) == year)
        .order_by(Booking.id.desc())
        .first()
    )
    next_num = 1
    if last and last.number:
        try:
            next_num = int(last.number.split("-")[-1]) + 1
        except ValueError:
            pass
    return f"БР-{year}-{next_num:04d}"


def admin_required(f):
    """Декоратор — только для администратора."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Доступ запрещён.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)

    return decorated


# ══════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active_user:
                flash("Ваш аккаунт деактивирован.", "danger")
                return redirect(url_for("login"))
            login_user(user)
            flash(f"Добро пожаловать, {user.full_name or user.username}!", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Неверный логин или пароль.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ══════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════
@app.route("/")
@login_required
def dashboard():
    now = datetime.now(UTC)

    stock_packs = WoodPack.query.filter_by(status="на_складе").all()
    total_stock_volume = round(sum(p.volume for p in stock_packs), 2)
    total_stock_packs = len(stock_packs)

    active_bookings = Booking.query.filter_by(status="активная").count()
    total_shipments = Shipment.query.count()

    # выручка за текущий месяц
    month_revenue = (
        db.session.query(func.coalesce(func.sum(Shipment.total_price), 0))
        .filter(
            extract("year", Shipment.shipped_at) == now.year,
            extract("month", Shipment.shipped_at) == now.month,
        )
        .scalar()
    )

    # выручка за год
    year_revenue = (
        db.session.query(func.coalesce(func.sum(Shipment.total_price), 0))
        .filter(extract("year", Shipment.shipped_at) == now.year)
        .scalar()
    )

    # последние 5 отправок
    recent_shipments = (
        Shipment.query.order_by(Shipment.shipped_at.desc()).limit(5).all()
    )

    return render_template(
        "dashboard.html",
        total_stock_volume=total_stock_volume,
        total_stock_packs=total_stock_packs,
        active_bookings=active_bookings,
        total_shipments=total_shipments,
        month_revenue=round(month_revenue, 2),
        year_revenue=round(year_revenue, 2),
        recent_shipments=recent_shipments,
    )


# ── API для графиков ──
@app.route("/api/revenue-chart")
@login_required
def api_revenue_chart():
    """Помесячная выручка за текущий год."""
    year = datetime.now(UTC).year
    data = (
        db.session.query(
            extract("month", Shipment.shipped_at).label("m"),
            func.coalesce(func.sum(Shipment.total_price), 0).label("total"),
        )
        .filter(extract("year", Shipment.shipped_at) == year)
        .group_by("m")
        .all()
    )
    months = [
        "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
        "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
    ]
    values = [0] * 12
    for row in data:
        values[int(row.m) - 1] = round(float(row.total), 2)
    return jsonify(labels=months, values=values)


@app.route("/api/stock-by-width")
@login_required
def api_stock_by_width():
    """Объём на складе по ширинам."""
    data = (
        db.session.query(
            WoodPack.width,
            func.sum(WoodPack.volume).label("vol"),
        )
        .filter(WoodPack.status == "на_складе")
        .group_by(WoodPack.width)
        .order_by(WoodPack.width)
        .all()
    )
    labels = [f"{int(r.width)} мм" for r in data]
    values = [round(float(r.vol), 4) for r in data]
    return jsonify(labels=labels, values=values)


@app.route("/api/stock-by-species")
@login_required
def api_stock_by_species():
    """Объём на складе по породам."""
    data = (
        db.session.query(
            WoodPack.species,
            func.sum(WoodPack.volume).label("vol"),
        )
        .filter(WoodPack.status == "на_складе")
        .group_by(WoodPack.species)
        .all()
    )
    labels = [r.species for r in data]
    values = [round(float(r.vol), 4) for r in data]
    return jsonify(labels=labels, values=values)


# ══════════════════════════════════════════════
#  STOCK (СКЛАД)
# ══════════════════════════════════════════════
@app.route("/stock")
@login_required
def stock():
    q = WoodPack.query

    # фильтры
    f_species = request.args.get("species", "")
    f_width = request.args.get("width", "")
    f_status = request.args.get("status", "")
    if f_species:
        q = q.filter(WoodPack.species == f_species)
    if f_width:
        q = q.filter(WoodPack.width == float(f_width))
    if f_status:
        q = q.filter(WoodPack.status == f_status)
    else:
        q = q.filter(WoodPack.status.in_(["на_складе", "забронирована"]))

    sort = request.args.get("sort", "date_desc")
    if sort == "width":
        q = q.order_by(WoodPack.width)
    elif sort == "volume":
        q = q.order_by(WoodPack.volume.desc())
    elif sort == "species":
        q = q.order_by(WoodPack.species)
    else:
        q = q.order_by(WoodPack.created_at.desc())

    page = request.args.get("page", 1, type=int)
    packs = q.paginate(page=page, per_page=25, error_out=False)

    # данные для фильтров
    all_species = (
        db.session.query(WoodPack.species)
        .distinct()
        .order_by(WoodPack.species)
        .all()
    )
    all_widths = (
        db.session.query(WoodPack.width)
        .distinct()
        .order_by(WoodPack.width)
        .all()
    )

    # суммы
    displayed_packs = q.all()
    sum_volume = round(sum(p.volume for p in displayed_packs), 4)
    sum_price = round(sum(p.volume * p.price_per_m3 for p in displayed_packs), 2)

    return render_template(
        "stock.html",
        packs=packs,
        all_species=[s[0] for s in all_species],
        all_widths=[w[0] for w in all_widths],
        f_species=f_species,
        f_width=f_width,
        f_status=f_status,
        sort=sort,
        sum_volume=sum_volume,
        sum_price=sum_price,
    )


@app.route("/stock/add", methods=["GET", "POST"])
@login_required
def add_pack():
    if request.method == "POST":
        try:
            width = float(request.form["width"])
            thickness = float(request.form["thickness"])
            length = float(request.form["length"])
            quantity = int(request.form["quantity"])
            price = float(request.form.get("price_per_m3") or 0)
            volume = calc_volume(width, thickness, length, quantity)

            pack = WoodPack(
                species=request.form["species"].strip(),
                wood_type=request.form.get("wood_type", "").strip(),
                grade=request.form.get("grade", "").strip(),
                width=width,
                thickness=thickness,
                length=length,
                quantity=quantity,
                volume=volume,
                price_per_m3=price,
                notes=request.form.get("notes", "").strip(),
                created_by=current_user.id,
            )
            db.session.add(pack)
            db.session.commit()
            flash(f"Пачка #{pack.id} добавлена на склад ({volume} м³).", "success")
            return redirect(url_for("stock"))
        except (ValueError, KeyError) as e:
            flash(f"Ошибка ввода: {e}", "danger")

    return render_template("add_pack.html")


@app.route("/stock/<int:pack_id>/edit", methods=["GET", "POST"])
@login_required
def edit_pack(pack_id):
    pack = db.session.get(WoodPack, pack_id)
    if not pack:
        flash("Пачка не найдена.", "danger")
        return redirect(url_for("stock"))
    if pack.status != "на_складе":
        flash("Редактировать можно только пачки со статусом «на складе».", "warning")
        return redirect(url_for("stock"))

    if request.method == "POST":
        try:
            pack.species = request.form["species"].strip()
            pack.wood_type = request.form.get("wood_type", "").strip()
            pack.grade = request.form.get("grade", "").strip()
            pack.width = float(request.form["width"])
            pack.thickness = float(request.form["thickness"])
            pack.length = float(request.form["length"])
            pack.quantity = int(request.form["quantity"])
            pack.price_per_m3 = float(request.form.get("price_per_m3") or 0)
            pack.volume = calc_volume(
                pack.width, pack.thickness, pack.length, pack.quantity
            )
            pack.notes = request.form.get("notes", "").strip()
            db.session.commit()
            flash("Пачка обновлена.", "success")
            return redirect(url_for("stock"))
        except (ValueError, KeyError) as e:
            flash(f"Ошибка ввода: {e}", "danger")

    return render_template("edit_pack.html", pack=pack)


@app.route("/stock/<int:pack_id>/delete", methods=["POST"])
@login_required
def delete_pack(pack_id):
    pack = db.session.get(WoodPack, pack_id)
    if not pack:
        flash("Пачка не найдена.", "danger")
    elif pack.status != "на_складе":
        flash("Удалить можно только пачки «на складе».", "warning")
    else:
        db.session.delete(pack)
        db.session.commit()
        flash("Пачка удалена.", "success")
    return redirect(url_for("stock"))


# ══════════════════════════════════════════════
#  BOOKINGS (БРОНИРОВАНИЯ)
# ══════════════════════════════════════════════
@app.route("/bookings")
@login_required
def bookings():
    status_filter = request.args.get("status", "активная")
    q = Booking.query
    if status_filter:
        q = q.filter(Booking.status == status_filter)
    booking_list = q.order_by(Booking.created_at.desc()).all()
    return render_template(
        "bookings.html", bookings=booking_list, status_filter=status_filter
    )


@app.route("/bookings/create", methods=["GET", "POST"])
@login_required
def create_booking():
    if request.method == "POST":
        booking = Booking(
            number=generate_booking_number(),
            customer_name=request.form.get("customer_name", "").strip(),
            destination=request.form.get("destination", "").strip(),
            notes=request.form.get("notes", "").strip(),
            created_by=current_user.id,
        )
        db.session.add(booking)
        db.session.commit()
        flash(f"Бронирование {booking.number} создано.", "success")
        return redirect(url_for("booking_detail", booking_id=booking.id))
    return render_template("create_booking.html")


@app.route("/bookings/<int:booking_id>")
@login_required
def booking_detail(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        flash("Бронирование не найдено.", "danger")
        return redirect(url_for("bookings"))

    available_packs = (
        WoodPack.query.filter_by(status="на_складе")
        .order_by(WoodPack.species, WoodPack.width)
        .all()
    )
    return render_template(
        "booking_detail.html", booking=booking, available_packs=available_packs
    )


@app.route("/bookings/<int:booking_id>/add-packs", methods=["POST"])
@login_required
def add_packs_to_booking(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.status != "активная":
        flash("Нельзя изменить это бронирование.", "warning")
        return redirect(url_for("bookings"))

    pack_ids = request.form.getlist("pack_ids")
    count = 0
    for pid in pack_ids:
        pack = db.session.get(WoodPack, int(pid))
        if pack and pack.status == "на_складе":
            pack.status = "забронирована"
            pack.booking_id = booking.id
            count += 1
    db.session.commit()
    flash(f"Добавлено пачек: {count}.", "success")
    return redirect(url_for("booking_detail", booking_id=booking.id))


@app.route("/bookings/<int:booking_id>/remove-pack/<int:pack_id>", methods=["POST"])
@login_required
def remove_pack_from_booking(booking_id, pack_id):
    booking = db.session.get(Booking, booking_id)
    pack = db.session.get(WoodPack, pack_id)
    if booking and pack and booking.status == "активная" and pack.booking_id == booking.id:
        pack.status = "на_складе"
        pack.booking_id = None
        db.session.commit()
        flash("Пачка убрана из бронирования.", "success")
    else:
        flash("Операция невозможна.", "warning")
    return redirect(url_for("booking_detail", booking_id=booking_id))


@app.route("/bookings/<int:booking_id>/ship", methods=["GET", "POST"])
@login_required
def ship_booking(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.status != "активная":
        flash("Нельзя отправить это бронирование.", "warning")
        return redirect(url_for("bookings"))
    if not booking.packs:
        flash("В бронировании нет пачек.", "warning")
        return redirect(url_for("booking_detail", booking_id=booking.id))

    if request.method == "POST":
        shipment = Shipment(
            booking_id=booking.id,
            driver_name=request.form.get("driver_name", "").strip(),
            truck_number=request.form.get("truck_number", "").strip(),
            destination=booking.destination,
            total_volume=booking.total_volume,
            total_price=booking.total_price,
            notes=request.form.get("notes", "").strip(),
            created_by=current_user.id,
        )
        db.session.add(shipment)

        for pack in booking.packs:
            pack.status = "отправлена"
        booking.status = "отправлена"

        db.session.commit()
        flash(f"Отправка оформлена! Объём: {shipment.total_volume} м³", "success")
        return redirect(url_for("shipment_detail", shipment_id=shipment.id))

    return render_template("ship_booking.html", booking=booking)


@app.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.status != "активная":
        flash("Невозможно отменить.", "warning")
        return redirect(url_for("bookings"))

    for pack in booking.packs:
        pack.status = "на_складе"
        pack.booking_id = None
    booking.status = "отменена"
    db.session.commit()
    flash("Бронирование отменено. Пачки возвращены на склад.", "success")
    return redirect(url_for("bookings"))


@app.route("/bookings/<int:booking_id>/excel")
@login_required
def booking_excel(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or not booking.shipment:
        flash("Нет данных для выгрузки.", "warning")
        return redirect(url_for("bookings"))
    buf = generate_shipment_excel(booking.shipment)
    filename = f"Накладная_{booking.number}.xlsx"
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ══════════════════════════════════════════════
#  ARCHIVE (АРХИВ ОТПРАВОК)
# ══════════════════════════════════════════════
@app.route("/archive")
@login_required
def archive():
    page = request.args.get("page", 1, type=int)
    shipments = (
        Shipment.query
        .order_by(Shipment.shipped_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )
    return render_template("archive.html", shipments=shipments)


@app.route("/archive/<int:shipment_id>")
@login_required
def shipment_detail(shipment_id):
    shipment = db.session.get(Shipment, shipment_id)
    if not shipment:
        flash("Отправка не найдена.", "danger")
        return redirect(url_for("archive"))
    return render_template("shipment_detail.html", shipment=shipment)


@app.route("/archive/<int:shipment_id>/excel")
@login_required
def shipment_excel(shipment_id):
    shipment = db.session.get(Shipment, shipment_id)
    if not shipment:
        flash("Отправка не найдена.", "danger")
        return redirect(url_for("archive"))
    buf = generate_shipment_excel(shipment)
    filename = f"Накладная_{shipment.booking.number}.xlsx"
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ══════════════════════════════════════════════
#  ADMIN (АДМИНИСТРИРОВАНИЕ)
# ══════════════════════════════════════════════
@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin_users.html", users=users)


@app.route("/admin/register", methods=["GET", "POST"])
@login_required
@admin_required
def register_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        is_admin = "is_admin" in request.form

        if not username or not password:
            flash("Логин и пароль обязательны.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("Пользователь с таким логином уже существует.", "danger")
        elif len(password) < 4:
            flash("Пароль должен быть не менее 4 символов.", "danger")
        else:
            user = User(username=username, full_name=full_name, is_admin=is_admin)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Пользователь «{username}» создан.", "success")
            return redirect(url_for("admin_users"))

    return render_template("register_user.html")


@app.route("/admin/toggle-user/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def toggle_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("Пользователь не найден.", "danger")
    elif user.id == current_user.id:
        flash("Нельзя деактивировать себя.", "warning")
    else:
        user.is_active_user = not user.is_active_user
        db.session.commit()
        status = "активирован" if user.is_active_user else "деактивирован"
        flash(f"Пользователь «{user.username}» {status}.", "success")
    return redirect(url_for("admin_users"))


# ══════════════════════════════════════════════
#  ИНИЦИАЛИЗАЦИЯ БД И ЗАПУСК
# ══════════════════════════════════════════════
with app.app_context():
    db.create_all()
    if not User.query.filter_by(is_admin=True).first():
        admin = User(username="admin", full_name="Администратор", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("✅ Администратор создан: admin / admin123")

if __name__ == "__main__":
    os.makedirs(app.config["EXPORT_FOLDER"], exist_ok=True)
    print("🌲 WoodFlow запущен: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)