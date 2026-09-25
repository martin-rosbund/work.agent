from fastapi import Depends

from app.core.database import get_db
from app.core.security import authenticated

Auth = Depends(authenticated)
DB = Depends(get_db)
