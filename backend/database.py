from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
import os

# Database URL - support both SQLite and PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./minecraft_controller.db")

# For PostgreSQL in Docker, use this URL:
if os.getenv("USE_POSTGRES", "false").lower() == "true":
    DATABASE_URL = "postgresql://postgres:postgres123@db:5432/minecraft_controller"

# Create engine
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize database
def init_db():
    """Initialize the database and create tables."""
    # Import all models first to register them with Base
    # Import here to avoid circular imports
    import models  # This will trigger the model class definitions
    
    # Now create all tables
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")
    
    # Initialize default permissions, roles, and admin user
    db = SessionLocal()
    try:
        # Import user service
        from user_service import UserService
        user_service = UserService(db)
        
        # Initialize permissions and roles
        user_service.initialize_default_permissions_and_roles()
        
        # Create default admin user if none exists
        admin_user = user_service.get_user_by_username("admin")
        if not admin_user:
            admin_user = user_service.create_user(
                username="admin",
                email="admin@localhost",
                password="admin123",  # Strong default password
                role="admin",
                full_name="Administrator"
            )
            print("Default admin user created: username=admin, password=admin123")
        else:
            print("Default admin user already exists")
    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
    finally:
        db.close()
