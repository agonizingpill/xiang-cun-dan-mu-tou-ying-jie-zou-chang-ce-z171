from typing import Annotated

from pydantic import BaseModel, ConfigDict, FiniteFloat, StringConstraints

class CompareCues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    track: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class SaveCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
