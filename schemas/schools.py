from datetime import datetime

from pydantic import BaseModel, Field


class SchoolPublic(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SchoolMeResponse(BaseModel):
    school: SchoolPublic
    role: str
