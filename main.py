from fastapi import FastAPI, Request, Form, Depends, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, joinedload, Session

from datetime import datetime, timedelta
from typing import List, Optional
import uuid
import os
import shutil
from pathlib import Path
import qrcode
import base64
from io import BytesIO


QRIS_STATIC = os.getenv("QRIS_STATIC","")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost/restaurant")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Create static directory for menu images if it doesn't exist
STATIC_DIR = Path("static")
MENU_IMG_DIR = STATIC_DIR / "menu"
MENU_IMG_DIR.mkdir(parents=True, exist_ok=True)

Base = declarative_base()

class Category(Base):
    __tablename__ = "categories"
    id = Column(String, primary_key=True)
    name = Column(String)
    description = Column(String, nullable=True)
    display_order = Column(Integer, default=0)
    items = relationship("Menu", back_populates="category")

class Menu(Base):
    __tablename__ = "menu"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Integer)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    category_id = Column(String, ForeignKey("categories.id"), nullable=True)
    is_available = Column(Boolean, default=True)
    is_popular = Column(Boolean, default=False)
    category = relationship("Category", back_populates="items")

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    customer = Column(String)
    phone = Column(String)
    address = Column(Text, nullable=True)
    note = Column(String, nullable=True)
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
    note = Column(String, nullable=True)
    order = relationship("Order", back_populates="items")
    menu = relationship("Menu")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

import re

def convert_crc16(qris_str):
    def char_code_at(s, idx):
        return ord(s[idx])

    crc = 0xFFFF
    strlen = len(qris_str)

    for c in range(strlen):
        crc ^= char_code_at(qris_str, c) << 8
        for i in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
    hex_crc = crc & 0xFFFF
    return "{:04X}".format(hex_crc)

def convert_qris_to_dynamic(qris, amount, service_fee=None, is_percent=False):
    qris = qris[:-4]  # Remove the last 4 characters (CRC16)
    
    # Modify static QRIS to dynamic
    qris = qris.replace("010211", "010212", 1)  # Make it dynamic by changing 010211 to 010212
    amount_str = f"54{len(str(amount)):02d}{amount}"  # Format amount
    
    # Split QRIS string
    qris_parts = re.split(r"5802ID", qris)
    
    # Add service fee if present
    if service_fee:
        if is_percent:
            fee_str = f"55020357{len(str(service_fee)):02d}{service_fee}"
        else:
            fee_str = f"55020256{len(str(service_fee)):02d}{service_fee}"
        amount_str += fee_str
    
    # Reconstruct QRIS with amount and service fee
    final_qris = f"{qris_parts[0]}{amount_str}5802ID{qris_parts[1]}"
    
    # Add CRC16 checksum
    crc16_checksum = convert_crc16(final_qris)
    final_qris += crc16_checksum
    
    return final_qris


def string_to_qrcode_base64(data: str) -> str:
    # Generate QR code
    qr = qrcode.make(data)
    
    # Save QR to a buffer
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)

    # Encode to base64
    img_base64 = base64.b64encode(buffer.read()).decode("utf-8")
    
    return f"data:image/png;base64,{img_base64}"

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper function to create a placeholder image if none exists
def ensure_placeholder_exists():
    placeholder_path = STATIC_DIR / "placeholder-food.jpg"
    if not placeholder_path.exists():
        # Create a simple placeholder (this is just a basic implementation)
        # In a real system, you might want to copy a real placeholder image file
        with open(placeholder_path, "wb") as f:
            # You could include a base64-encoded small image here, but keeping it simple
            f.write(b"Placeholder image")

# Ensure we have default categories if database is empty
def initialize_database(db: Session):
    # Check if categories exist
    categories_count = db.query(Category).count()
    if categories_count == 0:
        # Create default categories
        default_categories = [
            Category(id="breakfast", name="Sarapan", display_order=1),
            Category(id="lunch", name="Makan Siang", display_order=2),
            Category(id="dinner", name="Makan Malam", display_order=3),
            Category(id="drinks", name="Minuman", display_order=4),
            Category(id="snacks", name="Cemilan", display_order=5)
        ]
        db.add_all(default_categories)
        db.commit()

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    ensure_placeholder_exists()
    db = SessionLocal()
    initialize_database(db)
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
    customer_address: str = Form(...),
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
        address=customer_address,
        note=customer_note,
        status="Menunggu Konfirmasi"
    )
    db.add(order)

    # Only add items with quantity > 0
    has_items = False
    for i, menu_id in enumerate(item_ids):
        qty = int(quantities[i])
        if qty > 0:
            has_items = True
            menu_id = int(menu_id)  # Ensure it's an integer
            item_note = notes.get(menu_id, '')
            item = OrderItem(order_id=order_id, menu_id=menu_id, qty=qty, note=item_note)
            db.add(item)

    # If no items were added, return an error
    if not has_items:
        return HTMLResponse("Pesanan Anda tidak memiliki item. Silakan pilih menu.", status_code=400)

    db.commit()

    
    return RedirectResponse(f"/order-status/{order_id}", status_code=303)

@app.get("/order-status/{order_id}", response_class=HTMLResponse)
def order_status(request: Request, order_id: str, partial: bool = False, db: Session = Depends(get_db)):
    # Eagerly load OrderItem and its related Menu items
    order = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.menu)
    ).filter(Order.id == order_id).first()

    if not order:
        return HTMLResponse("Order not found", status_code=404)
    
    # If partial is True, return just the JSON data for the status check
    if partial:
        return JSONResponse(content={
            "status": order.status,
            "is_paid": order.is_paid
        })

    total_price = 0
    for item in order.items:
        total_price += item.menu.price * item.qty
    
    string_qris = string_to_qrcode_base64(convert_qris_to_dynamic(QRIS_STATIC, total_price))
    

    return templates.TemplateResponse("order_status.html", {"request": request, "order": order, "items": order.items, "qrcode": string_qris})

# Admin routes for category management
@app.get("/admin/categories", response_class=HTMLResponse)
def category_management(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.display_order).all()
    return templates.TemplateResponse("admin_categories.html", {"request": request, "categories": categories})

@app.post("/admin/categories/add", response_class=RedirectResponse)
async def add_category(
    id: str = Form(...),
    name: str = Form(...),
    description: str = Form(None),
    display_order: int = Form(0),
    db: Session = Depends(get_db)
):
    # Check if category with this ID already exists
    existing = db.query(Category).filter(Category.id == id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category ID already exists")
    
    category = Category(
        id=id,
        name=name,
        description=description,
        display_order=display_order
    )
    db.add(category)
    db.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)

@app.post("/admin/categories/edit/{category_id}", response_class=RedirectResponse)
async def edit_category(
    category_id: str,
    name: str = Form(...),
    description: str = Form(None),
    display_order: int = Form(0),
    db: Session = Depends(get_db)
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    category.name = name
    category.description = description
    category.display_order = display_order
    db.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)

@app.get("/admin/categories/delete/{category_id}", response_class=RedirectResponse)
async def delete_category(category_id: str, db: Session = Depends(get_db)):
    # Check if category has associated menu items
    items_count = db.query(Menu).filter(Menu.category_id == category_id).count()
    if items_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete category with associated menu items")
    
    category = db.query(Category).filter(Category.id == category_id).first()
    if category:
        db.delete(category)
        db.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)

# Admin routes for menu management
@app.get("/admin/menu", response_class=HTMLResponse)
def menu_management(request: Request, db: Session = Depends(get_db)):
    menu_items = db.query(Menu).options(joinedload(Menu.category)).all()
    categories = db.query(Category).order_by(Category.display_order).all()
    return templates.TemplateResponse("admin_menu.html", {
        "request": request, 
        "menu_items": menu_items,
        "categories": categories
    })

@app.post("/admin/menu/add", response_class=RedirectResponse)
async def add_menu_item(
    name: str = Form(...),
    price: int = Form(...),
    description: str = Form(None),
    category_id: str = Form(None),
    is_popular: bool = Form(False),
    is_available: bool = Form(True),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # Create menu item
    menu_item = Menu(
        name=name,
        price=price,
        description=description,
        category_id=category_id if category_id else None,
        is_popular=is_popular,
        is_available=is_available
    )
    
    db.add(menu_item)
    db.flush()  # Flush to get the ID but don't commit yet
    
    # Handle image upload if provided
    if image and image.filename:
        file_extension = image.filename.split(".")[-1]
        filename = f"menu_{menu_item.id}.{file_extension}"
        file_path = MENU_IMG_DIR / filename
        
        # Save uploaded file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        
        # Update menu item with image URL
        menu_item.image_url = f"/static/menu/{filename}"
    
    db.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)

@app.post("/admin/menu/edit/{menu_id}", response_class=RedirectResponse)
async def edit_menu_item(
    menu_id: int,
    name: str = Form(...),
    price: int = Form(...),
    description: str = Form(None),
    category_id: str = Form(None),
    is_popular: bool = Form(False),
    is_available: bool = Form(True),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    menu_item = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu_item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    
    menu_item.name = name
    menu_item.price = price
    menu_item.description = description
    menu_item.category_id = category_id if category_id else None
    menu_item.is_popular = is_popular
    menu_item.is_available = is_available
    
    # Handle image upload if provided
    if image and image.filename:
        # Remove old image if exists
        if menu_item.image_url:
            old_filename = menu_item.image_url.split("/")[-1]
            old_path = MENU_IMG_DIR / old_filename
            if old_path.exists():
                old_path.unlink()
        
        # Save new image
        file_extension = image.filename.split(".")[-1]
        filename = f"menu_{menu_id}.{file_extension}"
        file_path = MENU_IMG_DIR / filename
        
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        
        menu_item.image_url = f"/static/menu/{filename}"
    
    db.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)

@app.get("/admin/menu/delete/{menu_id}", response_class=RedirectResponse)
async def delete_menu_item(menu_id: int, db: Session = Depends(get_db)):
    # Check if this menu item is already used in orders
    order_count = db.query(OrderItem).filter(OrderItem.menu_id == menu_id).count()
    if order_count > 0:
        # Instead of deleting, just mark as unavailable
        menu_item = db.query(Menu).filter(Menu.id == menu_id).first()
        if menu_item:
            menu_item.is_available = False
            db.commit()
    else:
        # If not used in orders, we can delete it
        menu_item = db.query(Menu).filter(Menu.id == menu_id).first()
        if menu_item:
            # Delete associated image if exists
            if menu_item.image_url:
                filename = menu_item.image_url.split("/")[-1]
                file_path = MENU_IMG_DIR / filename
                if file_path.exists():
                    file_path.unlink()
            
            db.delete(menu_item)
            db.commit()
    
    return RedirectResponse(url="/admin/menu", status_code=303)

# Existing admin dashboard route
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    # Get date filter from query parameter, default to today
    date_filter = request.query_params.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
        start_date = datetime(filter_date.year, filter_date.month, filter_date.day, 0, 0, 0)
        end_date = datetime(filter_date.year, filter_date.month, filter_date.day, 23, 59, 59)
    except ValueError:
        # Handle invalid date format, default to today
        today = datetime.now()
        start_date = datetime(today.year, today.month, today.day, 0, 0, 0)
        end_date = datetime(today.year, today.month, today.day, 23, 59, 59)
        date_filter = today.strftime('%Y-%m-%d')
    
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
    ).order_by(Order.created_at.desc()).all()
    
    # Filter orders for the recap section
    filtered_orders = [
        order for order in orders 
        if start_date <= order.created_at <= end_date
    ]
    
    # Calculate total price for each order and summary stats
    total_sales = 0
    total_cancelled = 0
    successful_orders = 0
    cancelled_orders = 0
    
    for order in orders:
        order.total = sum(item.menu.price * item.qty for item in order.items)
        
        # For orders in the selected date
        if order in filtered_orders:
            if order.status == "Cancelled":
                total_cancelled += order.total
                cancelled_orders += 1
            elif order.status == "Selesai" and order.is_paid:
                total_sales += order.total
                successful_orders += 1
    
    # Prepare recap data
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

@app.get("/api/new-orders", response_class=JSONResponse)
def check_new_orders(db: Session = Depends(get_db)):
    # Auto-cancel logic same as in admin dashboard
    unpaid_orders = db.query(Order).filter(
        Order.is_paid == False,
        Order.status != "Cancelled",
        Order.created_at < datetime.utcnow() - timedelta(minutes=10)
    ).all()
    
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

@app.post("/mark-paid/{order_id}", response_class=RedirectResponse)
def mark_paid(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        order.is_paid = True
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

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