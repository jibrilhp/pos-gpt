from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Category, Menu
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/admin/categories", response_class=HTMLResponse)
def category_management(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.display_order).all()
    return templates.TemplateResponse("admin_categories.html", {"request": request, "categories": categories})

@router.post("/admin/categories/add", response_class=RedirectResponse)
async def add_category(
    id: str = Form(...),
    name: str = Form(...),
    description: str = Form(None),
    display_order: int = Form(0),
    db: Session = Depends(get_db)
):
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

@router.post("/admin/categories/edit/{category_id}", response_class=RedirectResponse)
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

@router.get("/admin/categories/delete/{category_id}", response_class=RedirectResponse)
async def delete_category(category_id: str, db: Session = Depends(get_db)):
    items_count = db.query(Menu).filter(Menu.category_id == category_id).count()
    if items_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete category with associated menu items")

    category = db.query(Category).filter(Category.id == category_id).first()
    if category:
        db.delete(category)
        db.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)
