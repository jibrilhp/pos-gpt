from database import SessionLocal
from models import Customer
from auth import get_password_hash

# Create a database session
db = SessionLocal()

# Default user data
default_user = {
    "name": "admin",
    "phone": "1234567890",
    "email": "admin@example.com",
    "hashed_password": get_password_hash("secret")  # Hash the password
}

# Check if the user already exists
existing_user = db.query(Customer).filter(Customer.name == default_user["name"]).first()
if not existing_user:
    # Create the default user
    db_user = Customer(**default_user)
    db.add(db_user)
    db.commit()
    print("Default user created successfully!")
else:
    print("Default user already exists.")

db.close()