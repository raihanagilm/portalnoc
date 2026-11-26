from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# Engine SQLAlchemy untuk Database MySQL Lokal
connect_args = {}
if settings.DB_HOST not in ["127.0.0.1", "localhost", "::1"]:
    connect_args["ssl_verify_cert"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=30,
    max_overflow=50
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Deklarasi Model Terpisah: MasterBase (Global) & TenantBase (Per-Kantor)
MasterBase = declarative_base()
TenantBase = declarative_base()

# Base alias untuk backward compatibility
Base = MasterBase

from fastapi import Request

def get_master_db():
    """Dependency eksplisit untuk modul master global (Users, Auth, Kantor Global)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db(request: Request = None):
    """
    Dependency dinamis:
    Jika request memiliki active_kantor di state/header/cookie,
    maka otomatis menghubungkan sesi ke Tenant DB kantor tersebut.
    Jika tidak ada atau modul global, fallback ke Master DB.
    """
    from app.core.tenant_database import TenantDatabaseManager

    active_kantor = None
    if request:
        if getattr(request.state, "current_user", None):
            active_kantor = getattr(request.state, "active_kantor", None)
        if not active_kantor:
            active_kantor = request.query_params.get("kantor")
        if not active_kantor:
            active_kantor = getattr(request.state, "active_kantor", None)
        if not active_kantor:
            active_kantor = request.headers.get("X-Active-Kantor") or request.cookies.get("active_kantor")

    if not active_kantor or active_kantor.lower() in ["master", "global", "all"]:
        from app.core.security import get_all_kantor_codes
        all_k = get_all_kantor_codes()
        active_kantor = all_k[0] if all_k else None

    if active_kantor:
        db = TenantDatabaseManager.get_tenant_session(active_kantor)
    else:
        db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
