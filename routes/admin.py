from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta
from database import SessionLocal
from models import Order, OrderItem
from fastapi.templating import Jinja2Templates
import uuid

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    date_filter = request.query_params.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
    except ValueError:
        filter_date = datetime.now()
    start_date = datetime(filter_date.year, filter_date.month, filter_date.day, 0, 0, 0)
    end_date = datetime(filter_date.year, filter_date.month, filter_date.day, 23, 59, 59)

    unpaid_orders = db.query(Order).filter(
        Order.is_paid == False,
        Order.status != "Cancelled",
        Order.created_at < datetime.utcnow() - timedelta(minutes=10)
    ).all()
    for order in unpaid_orders:
        order.status = "Cancelled"
    if unpaid_orders:
        db.commit()

    orders = db.query(Order).options(joinedload(Order.items).joinedload(OrderItem.menu)).order_by(Order.created_at.desc()).all()

    filtered_orders = [order for order in orders if start_date <= order.created_at <= end_date]

    total_sales = 0
    total_cancelled = 0
    successful_orders = 0
    cancelled_orders = 0

    for order in orders:
        order.total = sum(item.menu.price * item.qty for item in order.items)
        if order in filtered_orders:
            if order.status == "Cancelled":
                total_cancelled += order.total
                cancelled_orders += 1
            elif order.status == "Selesai" and order.is_paid:
                total_sales += order.total
                successful_orders += 1

    recap = {
        'date': date_filter,
        'total_sales': total_sales,
        'total_cancelled': total_cancelled,
        'successful_orders': successful_orders,
        'cancelled_orders': cancelled_orders,
        'filtered_orders': filtered_orders
    }

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "orders": orders,
        "recap": recap
    })

@router.post("/update-status/{order_id}", response_class=RedirectResponse)
def update_status(order_id: str, status: str = Form(...), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return HTMLResponse("Order tidak ditemukan", status_code=404)

    if status == "Cancelled":
        order.status = status
        db.commit()
        return RedirectResponse(url="/admin", status_code=303)

    elapsed = datetime.utcnow() - order.created_at
    if not order.is_paid and elapsed > timedelta(minutes=10):
        return HTMLResponse("Order belum dibayar dan sudah lewat 10 menit.", status_code=403)

    order.status = status
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@router.get("/api/new-orders", response_class=JSONResponse)
def check_new_orders(db: Session = Depends(get_db)):
    unpaid_orders = db.query(Order).filter(
        Order.is_paid == False,
        Order.status != "Cancelled",
        Order.created_at < datetime.utcnow() - timedelta(minutes=10)
    ).all()
    for order in unpaid_orders:
        order.status = "Cancelled"
    if unpaid_orders:
        db.commit()

    new_orders = db.query(Order).filter(
        Order.is_paid == False,
        Order.status == "Menunggu Konfirmasi"
    ).count()

    return {"new_orders": new_orders > 0}

@router.post("/api/n8n-order", response_class=JSONResponse)
def create_order_from_n8n(data: list[dict], db: Session = Depends(get_db)):
    if not data:
        return JSONResponse(content={"error": "No order data received"}, status_code=400)

    user_id = data[0].get("user_id")
    order_id = str(uuid.uuid4())[:8]
    order = Order(
        id=order_id,
        customer=f"User {user_id}",
        phone="-",
        address="From n8n",
        note="Generated via API",
        status="Menunggu Konfirmasi"
    )
    db.add(order)

    for entry in data:
        menu_id = entry.get("id")
        qty = entry.get("qty", 1)
        note = entry.get("notes", "")
        if menu_id:
            item = OrderItem(order_id=order_id, menu_id=menu_id, qty=qty, note=note)
            db.add(item)

    db.commit()
    return {"order_id": order_id, "status": "created"}
