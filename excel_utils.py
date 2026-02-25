import os
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill


def generate_shipment_excel(shipment):
    """Генерация накладной в формате Excel."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Накладная"

    # --- стили ---
    title_font = Font(name="Arial", size=14, bold=True)
    header_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    cell_font = Font(name="Arial", size=10)
    header_fill = PatternFill(start_color="2D5F2D", end_color="2D5F2D", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")

    # --- шапка ---
    ws.merge_cells("A1:K1")
    ws["A1"] = "НАКЛАДНАЯ НА ОТГРУЗКУ"
    ws["A1"].font = title_font
    ws["A1"].alignment = center

    info = [
        ("A3", f"Номер бронирования: {shipment.booking.number}"),
        ("A4", f"Дата отгрузки: {shipment.shipped_at.strftime('%d.%m.%Y %H:%M')}"),
        ("A5", f"Заказчик: {shipment.booking.customer_name}"),
        ("A6", f"Пункт назначения: {shipment.destination}"),
        ("A7", f"Водитель: {shipment.driver_name}"),
        ("A8", f"Номер ТС: {shipment.truck_number}"),
    ]
    for cell_ref, value in info:
        ws[cell_ref] = value
        ws[cell_ref].font = cell_font

    # --- таблица ---
    headers = [
        "№", "Порода", "Тип", "Сорт",
        "Ширина\n(мм)", "Толщина\n(мм)", "Длина\n(м)",
        "Кол-во\n(шт)", "Объём\n(м³)", "Цена/м³\n(руб)", "Сумма\n(руб)",
    ]
    header_row = 10
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=header_row, column=col, value=h)
        c.font = header_font
        c.fill = header_fill
        c.border = thin_border
        c.alignment = center

    row = header_row + 1
    for i, pack in enumerate(shipment.booking.packs, 1):
        values = [
            i, pack.species, pack.wood_type, pack.grade,
            pack.width, pack.thickness, pack.length,
            pack.quantity, round(pack.volume, 4),
            pack.price_per_m3, round(pack.volume * pack.price_per_m3, 2),
        ]
        for col, val in enumerate(values, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.font = cell_font
            c.border = thin_border
            c.alignment = center
        row += 1

    # --- итого ---
    row += 1
    ws.cell(row=row, column=7, value="ИТОГО:").font = Font(name="Arial", size=11, bold=True)
    ws.cell(row=row, column=9, value=round(shipment.total_volume, 4)).font = Font(
        name="Arial", size=11, bold=True
    )
    ws.cell(row=row, column=11, value=round(shipment.total_price, 2)).font = Font(
        name="Arial", size=11, bold=True
    )

    # --- ширины колонок ---
    widths = [5, 14, 16, 8, 10, 10, 9, 9, 10, 12, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w

    # сохранение в буфер
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf