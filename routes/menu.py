from fastapi import APIRouter, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from models import Menu, Category
from database import SessionLocal
from config import MENU_IMG_DIR
from fastapi.templating import Jinja2Templates
import shutil

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_class=HTMLResponse)
def menu_page(request: Request, db: Session = Depends(get_db)):
    menu = db.query(Menu).all()
    return templates.TemplateResponse("menu.html", {"request": request, "menu": menu})

@router.get("/admin/menu", response_class=HTMLResponse)
def menu_management(request: Request, db: Session = Depends(get_db)):
    menu_items = db.query(Menu).options(joinedload(Menu.category)).all()
    categories = db.query(Category).order_by(Category.display_order).all()
    return templates.TemplateResponse("admin_menu.html", {
        "request": request, 
        "menu_items": menu_items,
        "categories": categories
    })

@router.post("/admin/menu/add", response_class=RedirectResponse)
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
    menu_item = Menu(
        name=name,
        price=price,
        description=description,
        category_id=category_id if category_id else None,
        is_popular=is_popular,
        is_available=is_available
    )
    db.add(menu_item)
    db.flush()

    if image and image.filename:
        file_extension = image.filename.split(".")[-1]
        filename = f"menu_{menu_item.id}.{file_extension}"
        file_path = MENU_IMG_DIR / filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        menu_item.image_url = f"/static/menu/{filename}"

    db.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)

@router.post("/admin/menu/edit/{menu_id}", response_class=RedirectResponse)
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

    if image and image.filename:
        if menu_item.image_url:
            old_filename = menu_item.image_url.split("/")[-1]
            old_path = MENU_IMG_DIR / old_filename
            if old_path.exists():
                old_path.unlink()

        file_extension = image.filename.split(".")[-1]
        filename = f"menu_{menu_id}.{file_extension}"
        file_path = MENU_IMG_DIR / filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        menu_item.image_url = f"/static/menu/{filename}"

    db.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)

@router.get("/admin/menu/delete/{menu_id}", response_class=RedirectResponse)
async def delete_menu_item(menu_id: int, db: Session = Depends(get_db)):
    from models import OrderItem
    order_count = db.query(OrderItem).filter(OrderItem.menu_id == menu_id).count()
    menu_item = db.query(Menu).filter(Menu.id == menu_id).first()

    if order_count > 0:
        if menu_item:
            menu_item.is_available = False
            db.commit()
    else:
        if menu_item:
            if menu_item.image_url:
                filename = menu_item.image_url.split("/")[-1]
                file_path = MENU_IMG_DIR / filename
                if file_path.exists():
                    file_path.unlink()
            db.delete(menu_item)
            db.commit()

    return RedirectResponse(url="/admin/menu", status_code=303)
