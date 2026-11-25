from typing import Annotated

from pydantic import BaseModel, ConfigDict, FiniteFloat, StringConstraints

class RecordTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    venue: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    timings: list | dict
    shift: FiniteFloat


class LockTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    track: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
