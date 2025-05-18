from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

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
