from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, joinedload, Session

from datetime import datetime, timedelta
import uuid
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost/restaurant")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

Base = declarative_base()

class Menu(Base):
    __tablename__ = "menu"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Integer)

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    customer = Column(String)
    phone = Column(String)
    note = Column(String)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    items = relationship("OrderItem", back_populates="order")
    is_paid = Column(Boolean, default=False)

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(String, ForeignKey("orders.id"))
    menu_id = Column(Integer, ForeignKey("menu.id"))
    qty = Column(Integer)
    note = Column(String)
    order = relationship("Order", back_populates="items")
    menu = relationship("Menu")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
def menu_page(request: Request, db: Session = Depends(get_db)):
    menu = db.query(Menu).all()
    return templates.TemplateResponse("menu.html", {"request": request, "menu": menu})

@app.post("/order", response_class=HTMLResponse)
async def place_order(
    request: Request,
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    customer_note: str = Form(None),
    item_ids: list[int] = Form(...),
    quantities: list[int] = Form(...),
    db: Session = Depends(get_db)
):
    form_data = await request.form()
    
    # Parse the notes manually since they are sent as notes[1], notes[2], etc.
    notes = {}
    for key, value in form_data.items():
        if key.startswith('notes['):
            # Extract the item ID from the notes key (e.g., 'notes[1]' -> 1)
            item_id = int(key.split('[')[1].split(']')[0])
            notes[item_id] = value

    order_id = str(uuid.uuid4())[:8]
    order = Order(
        id=order_id,
        customer=customer_name,
        phone=customer_phone,
        note=customer_note,
        status="Menunggu Konfirmasi"
    )
    db.add(order)

    for i, menu_id in enumerate(item_ids):
        qty = int(quantities[i])
        if qty > 0:
            item_note = notes.get(menu_id, '')
            item = OrderItem(order_id=order_id, menu_id=menu_id, qty=qty, note=item_note)
            db.add(item)

    db.commit()
    return RedirectResponse(f"/order-status/{order_id}", status_code=303)

@app.get("/order-status/{order_id}", response_class=HTMLResponse)
def order_status(request: Request, order_id: str, db: Session = Depends(get_db)):
    # Eagerly load OrderItem and its related Menu items
    order = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.menu)
    ).filter(Order.id == order_id).first()

    if not order:
        return HTMLResponse("Order not found", status_code=404)

    return templates.TemplateResponse("order_status.html", {"request": request, "order": order, "items": order.items})

@app.post("/mark-paid/{order_id}", response_class=RedirectResponse)
def mark_paid(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        order.is_paid = True
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    # Check for orders that need to be auto-cancelled (not paid after 10 minutes)
    unpaid_orders = db.query(Order).filter(
        Order.is_paid == False,
        Order.status != "Cancelled",
        Order.created_at < datetime.utcnow() - timedelta(minutes=10)
    ).all()
    
    # Auto-cancel orders older than 10 minutes that are not paid
    for order in unpaid_orders:
        order.status = "Cancelled"
    
    if unpaid_orders:
        db.commit()
    
    # Eagerly load the related items and menu for each order
    orders = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.menu)
    ).order_by(Order.created_at.asc()).all()
    
    # Calculate total price for each order
    for order in orders:
        order.total = sum(item.menu.price * item.qty for item in order.items)
    
    return templates.TemplateResponse("admin.html", {"request": request, "orders": orders})

@app.get("/api/new-orders", response_class=JSONResponse)
def check_new_orders(db: Session = Depends(get_db)):
    # Check for orders that need to be auto-cancelled (not paid after 10 minutes)
    unpaid_orders = db.query(Order).filter(
        Order.is_paid == False,
        Order.status != "Cancelled",
        Order.created_at < datetime.utcnow() - timedelta(minutes=10)
    ).all()
    
    # Auto-cancel orders older than 10 minutes that are not paid
    for order in unpaid_orders:
        order.status = "Cancelled"
    
    if unpaid_orders:
        db.commit()
    
    # Find orders that are not paid and are in "Menunggu Konfirmasi" status
    new_orders = db.query(Order).filter(
        Order.is_paid == False,
        Order.status == "Menunggu Konfirmasi"
    ).count()
    
    return {"new_orders": new_orders > 0}

@app.post("/update-status/{order_id}", response_class=RedirectResponse)
def update_status(order_id: str, status: str = Form(...), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return HTMLResponse("Order tidak ditemukan", status_code=404)
        
    # Allow setting to Cancelled status anytime
    if status == "Cancelled":
        order.status = status
        db.commit()
        return RedirectResponse(url="/admin", status_code=303)
    
    # For other status changes, check if it's paid or within the 10-minute window
    elapsed = datetime.utcnow() - order.created_at
    if not order.is_paid and elapsed > timedelta(minutes=10):
        return HTMLResponse("Order belum dibayar dan sudah lewat 10 menit.", status_code=403)
    
    order.status = status
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)
         
@app.get("/receipt/{order_id}", response_class=HTMLResponse)
def print_receipt(request: Request, order_id: str, db: Session = Depends(get_db)):
    # Eagerly load OrderItem and its related Menu items
    order = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.menu)
    ).filter(Order.id == order_id).first()

    if not order:
        return HTMLResponse("Order not found", status_code=404)

    # Calculate the total price
    total = sum(item.menu.price * item.qty for item in order.items)
    order.total = total

    return templates.TemplateResponse("receipt.html", {
        "request": request,
        "order": order,
        "items": order.items
    })