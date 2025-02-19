from pydantic import BaseModel
from typing import Optional

class HealthResponse(BaseModel):
    status: str
    env: str
    last_ingest: Optional[str] = None