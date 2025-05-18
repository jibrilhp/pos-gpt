from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from database import SessionLocal
from models import Order, OrderItem, Menu
from utils.qris import convert_qris_to_dynamic, string_to_qrcode_base64
from fastapi.templating import Jinja2Templates
import uuid
from datetime import datetime, timedelta

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/order", response_class=HTMLResponse)
async def place_order(
    request: Request,
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    customer_address: str = Form(...),
    customer_note: str = Form(None),
    item_ids: list[int] = Form(...),
    quantities: list[int] = Form(...),
    db: Session = Depends(get_db)
):
    form_data = await request.form()
    notes = {int(k.split('[')[1].split(']')[0]): v for k, v in form_data.items() if k.startswith('notes[')}

    order_id = str(uuid.uuid4())[:8]
    order = Order(
        id=order_id,
        customer=customer_name,
        phone=customer_phone,
        address=customer_address,
        note=customer_note,
        status="Menunggu Konfirmasi"
    )
    db.add(order)

    has_items = False
    for i, menu_id in enumerate(item_ids):
        qty = int(quantities[i])
        if qty > 0:
            has_items = True
            item_note = notes.get(int(menu_id), '')
            db.add(OrderItem(order_id=order_id, menu_id=menu_id, qty=qty, note=item_note))

    if not has_items:
        return HTMLResponse("Pesanan Anda tidak memiliki item. Silakan pilih menu.", status_code=400)

    db.commit()
    return RedirectResponse(f"/order-status/{order_id}", status_code=303)

@router.get("/order-status/{order_id}", response_class=HTMLResponse)
def order_status(request: Request, order_id: str, partial: bool = False, db: Session = Depends(get_db)):
    order = db.query(Order).options(joinedload(Order.items).joinedload(OrderItem.menu)).filter(Order.id == order_id).first()
    if not order:
        return HTMLResponse("Order not found", status_code=404)

    if partial:
        return JSONResponse(content={"status": order.status, "is_paid": order.is_paid})

    total_price = sum(item.menu.price * item.qty for item in order.items)
    qr_data = convert_qris_to_dynamic(
        "00020101021126650013ID.CO.BCA.WWW011893600014000299749202150008850029974920303UKE51440014ID.CO.QRIS.WWW0215ID10254011522240303UKE5204581453033605802ID5918DAPUR ANTAR 24 JAM6015JAKARTA SELATAN61051263062070703A0163042B58",
        total_price
    )
    string_qris = string_to_qrcode_base64(qr_data)

    return templates.TemplateResponse("order_status.html", {"request": request, "order": order, "items": order.items, "qrcode": string_qris})

@router.post("/mark-paid/{order_id}", response_class=RedirectResponse)
def mark_paid(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        order.is_paid = True
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@router.get("/receipt/{order_id}", response_class=HTMLResponse)
def print_receipt(request: Request, order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).options(joinedload(Order.items).joinedload(OrderItem.menu)).filter(Order.id == order_id).first()
    if not order:
        return HTMLResponse("Order not found", status_code=404)

    order.total = sum(item.menu.price * item.qty for item in order.items)
    return templates.TemplateResponse("receipt.html", {"request": request, "order": order, "items": order.items})
