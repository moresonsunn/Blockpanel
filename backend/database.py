from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
import os

# Database URL - support both SQLite and PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./minecraft_controller.db")

# For PostgreSQL in Docker, use this URL:
if os.getenv("USE_POSTGRES", "false").lower() == "true":
    DATABASE_URL = "postgresql://postgres:postgres123@db:5432/minecraft_controller"

# Create engine with optimized connection pool settings
connect_args = {}
engine_kwargs = {
    # Increase connection pool size for high-frequency requests
    "pool_size": 20,  # Base pool size
    "max_overflow": 40,  # Additional connections beyond pool_size
    "pool_timeout": 60,  # Timeout for getting connection from pool
    "pool_recycle": 3600,  # Recycle connections after 1 hour
    "pool_pre_ping": True,  # Verify connections before use
    "echo": False  # Set to True for debugging SQL queries
}

if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}
    # SQLite-specific optimizations
    engine_kwargs.update({
        "pool_size": 10,  # SQLite doesn't need as many connections
        "max_overflow": 20,
        "poolclass": None  # Use StaticPool for SQLite
    })
elif "postgresql" in DATABASE_URL:
    # PostgreSQL-specific optimizations
    engine_kwargs.update({
        "pool_size": 25,  # PostgreSQL can handle more connections
        "max_overflow": 50
    })

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)

# Create SessionLocal class with optimized settings
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    # Optimize session settings for high-frequency use
    expire_on_commit=False  # Keep objects accessible after commit
)

# Create Base class
Base = declarative_base()

# Dependency to get DB session with proper error handling
def get_db():
    db = SessionLocal()
    try:
        yield db
        # Commit any pending changes
        db.commit()
    except Exception as e:
        # Rollback on any exception
        db.rollback()
        raise e
    finally:
        # Always close the session to return connection to pool
        db.close()

# Context manager for database sessions
class DatabaseSession:
    def __init__(self):
        self.db = None
    
    def __enter__(self):
        self.db = SessionLocal()
        return self.db
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.db.rollback()
        else:
            self.db.commit()
        self.db.close()

# Helper function for manual session management
def get_db_session():
    """Get a database session for manual management.
    Remember to call session.close() when done!
    """
    return SessionLocal()

# Database connection monitoring
def get_connection_pool_status():
    """Get database connection pool status for monitoring."""
    try:
        pool = engine.pool
        return {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total_connections": pool.size() + pool.overflow()
        }
    except Exception as e:
        return {"error": str(e)}

def health_check_db():
    """Quick database health check."""
    try:
        with DatabaseSession() as db:
            # Simple query to test connection
            db.execute(text("SELECT 1"))
            return True
    except Exception as e:
        print(f"Database health check failed: {e}")
        return False

# Cleanup function to clear expired sessions
def cleanup_expired_sessions():
    """Clean up expired database sessions and connections."""
    try:
        # Force cleanup of connection pool
        engine.dispose()
        print("Database connection pool cleaned up")
    except Exception as e:
        print(f"Error during connection cleanup: {e}")

# Initialize database
def init_db():
    """Initialize the database and create tables."""
    # Import all models first to register them with Base
    # Import here to avoid circular imports
    import models  # This will trigger the model class definitions
    
    # Now create all tables
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")

    # Create helpful indexes to speed up queries (safe if they already exist)
    try:
        from sqlalchemy import text as _text
        with engine.begin() as conn:
            # Drop legacy curated templates table if it still exists
            try:
                conn.execute(_text("DROP TABLE IF EXISTS server_templates"))
                print("Dropped legacy table: server_templates (if existed)")
            except Exception as _e:
                print(f"Warning: could not drop legacy server_templates table: {_e}")
            conn.execute(_text("CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs (timestamp)"))
            conn.execute(_text("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs (user_id)"))
            conn.execute(_text("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action)"))
        print("Database indexes ensured for audit_logs")
    except Exception as e:
        print(f"Warning: could not create indexes (non-fatal): {e}")
    
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
