from config import STATIC_DIR, MENU_IMG_DIR
from models import Category
from sqlalchemy.orm import Session

def ensure_placeholder_exists():
    placeholder_path = STATIC_DIR / "placeholder-food.jpg"
    if not placeholder_path.exists():
        with open(placeholder_path, "wb") as f:
            f.write(b"Placeholder image")

def initialize_database(db: Session):
    if db.query(Category).count() == 0:
        db.add_all([
            Category(id="breakfast", name="Sarapan", display_order=1),
            Category(id="lunch", name="Makan Siang", display_order=2),
            Category(id="dinner", name="Makan Malam", display_order=3),
            Category(id="drinks", name="Minuman", display_order=4),
            Category(id="snacks", name="Cemilan", display_order=5)
        ])
        db.commit()
