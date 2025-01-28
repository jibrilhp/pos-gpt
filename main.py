from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from auth import (
    authenticate_user, create_access_token, get_current_user,
    get_password_hash, ACCESS_TOKEN_EXPIRE_MINUTES
)
from datetime import timedelta
from sqlalchemy.orm import Session
from models import Customer, Product, Sale
from database import SessionLocal, engine
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from dependencies import get_db  # Import get_db from dependencies

app = FastAPI()



app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("templates/index.html", "r") as file:
        return file.read()
    


# Pydantic models for request/response validation
class CustomerCreate(BaseModel):
    name: str
    phone: str
    email: str = None

class ProductCreate(BaseModel):
    name: str
    price: float
    stock: int

class SaleCreate(BaseModel):
    customer_id: int
    product_id: int
    quantity: int


# Customer endpoints
@app.post("/customers/")
def create_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    db_customer = Customer(**customer.dict())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer


# Product endpoints
@app.post("/products/")
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = Product(**product.dict())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.get("/products/")
def get_products(db: Session = Depends(get_db)):
    return db.query(Product).all()

# Sale endpoints
@app.post("/sales/")
def create_sale(sale: SaleCreate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == sale.product_id).first()
    if not product or product.stock < sale.quantity:
        raise HTTPException(status_code=400, detail="Product not available or insufficient stock")

    total_price = product.price * sale.quantity
    db_sale = Sale(**sale.dict(), total_price=total_price)
    db.add(db_sale)
    db.commit()
    db.refresh(db_sale)

    # Update product stock
    product.stock -= sale.quantity
    db.commit()

    return db_sale

@app.get("/sales/")
def get_sales(db: Session = Depends(get_db)):
    return db.query(Sale).all()



# Token endpoint
@app.post("/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.name}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Protected endpoint example
@app.get("/users/me/")
def read_users_me(current_user: Customer = Depends(get_current_user)):
    return current_user