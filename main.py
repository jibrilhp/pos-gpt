from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from database import engine, Base
from routes import menu, category, order, admin
from utils.helpers import ensure_placeholder_exists, initialize_database

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

Base.metadata.create_all(bind=engine)

@app.on_event("startup")
async def startup_event():
    ensure_placeholder_exists()
    from database import SessionLocal
    db = SessionLocal()
    initialize_database(db)
    db.close()

# Include routes
app.include_router(menu.router)
app.include_router(category.router)
app.include_router(order.router)
app.include_router(admin.router)
