# Auto-generated domain models from MetaCompiler pipeline
from typing import Optional, Any, Dict
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID

class User(BaseModel):
    model_config = ConfigDict(extra='ignore')

    userId: str
    firstName: str
    lastName: str

