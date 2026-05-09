from datetime import datetime

from pydantic import BaseModel


class AdminResponse(BaseModel):
    id: str
    school_id: str
    name: str
    email: str
    date_added: datetime

    model_config = {"from_attributes": True}
