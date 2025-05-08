
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, joinedload

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
    phone = Column(String)         # ➕ Tambahkan ini
    note = Column(String)          # ➕ Tambahkan ini
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
    note = Column(String)  # Add this field for notes
    order = relationship("Order", back_populates="items")
    menu = relationship("Menu")


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def menu_page(request: Request):
    db = SessionLocal()
    menu = db.query(Menu).all()
    db.close()
    return templates.TemplateResponse("menu.html", {"request": request, "menu": menu})

@app.post("/order", response_class=HTMLResponse)
async def place_order(
    request: Request,
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    customer_note: str = Form(None),
    item_ids: list[int] = Form(...),
    quantities: list[int] = Form(...),
):
    form_data = await request.form()
    
    # Parse the notes manually since they are sent as notes[1], notes[2], etc.
    notes = {}
    for key, value in form_data.items():
        if key.startswith('notes['):
            # Extract the item ID from the notes key (e.g., 'notes[1]' -> 1)
            item_id = int(key.split('[')[1].split(']')[0])
            notes[item_id] = value

    db = SessionLocal()
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
            item_note = notes.get(menu_id, '')  # Get the note for this item, default to empty if none
            item = OrderItem(order_id=order_id, menu_id=menu_id, qty=qty, note=item_note)
            db.add(item)

    db.commit()
    db.close()
    return RedirectResponse(f"/order-status/{order_id}", status_code=303)


@app.get("/order-status/{order_id}", response_class=HTMLResponse)
def order_status(request: Request, order_id: str):
    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()
    items = db.query(OrderItem).options(joinedload(OrderItem.menu)).filter(OrderItem.order_id == order_id).all()
    db.close()
    return templates.TemplateResponse("order_status.html", {"request": request, "order": order, "items": items})

@app.post("/mark-paid/{order_id}", response_class=RedirectResponse)
def mark_paid(order_id: str):
    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        order.is_paid = True
        db.commit()
    db.close()
    return RedirectResponse(url="/admin", status_code=303)




@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    db = SessionLocal()
    
    # Eager load the related items for each order
    orders = db.query(Order).options(joinedload(Order.items)).order_by(Order.created_at.asc()).all()
    
    db.close()
    return templates.TemplateResponse("admin.html", {"request": request, "orders": orders})


@app.post("/update-status/{order_id}", response_class=RedirectResponse)
def update_status(order_id: str, status: str = Form(...)):
    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        elapsed = datetime.utcnow() - order.created_at
        if not order.is_paid and elapsed > timedelta(minutes=10):
            db.close()
            return HTMLResponse("Order belum dibayar dan sudah lewat 10 menit.", status_code=403)
        order.status = status
        db.commit()
    db.close()
    return RedirectResponse(url="/admin", status_code=303)
         
@app.get("/receipt/{order_id}", response_class=HTMLResponse)
def print_receipt(request: Request, order_id: str):
    db = SessionLocal()
    order = db.query(Order).filter(Order.id == order_id).first()
    items = db.query(OrderItem).options(joinedload(OrderItem.menu)).filter(OrderItem.order_id == order_id).all()
    
    # Hitung total manual (karena tidak disimpan di DB)
    total = sum(item.menu.price * item.qty for item in items)
    order.total = total

    db.close()
    return templates.TemplateResponse("receipt.html", {
        "request": request,
        "order": order,
        "items": items
    })