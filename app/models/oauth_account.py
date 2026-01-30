from fastapi_users_db_sqlalchemy import SQLAlchemyBaseOAuthAccountTableUUID

from app.database import Base


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """Stores linked OAuth provider accounts (Google, etc.)."""
