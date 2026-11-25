"""整晚排演的请求模型（规范契约）。

实际接口对字段别名更宽容（直接解析 JSON dict），这里的模型用于文档与
可能的程序化调用。
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra='allow')


class PlanNight(_Tolerant):
    date: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    tracks: list[str] | None = None
    venues: list[str] | None = None


class DraftRehearsal(PlanNight):
    pass


class IssueRehearsal(_Tolerant):
    date: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=40)] = None
    tracks: list[str] | None = None
    venues: list[str] | None = None
    code: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=160)] = None
    base_version: int | None = None
    idempotency_key: Annotated[str | None, StringConstraints(max_length=160)] = None
    draft_token: Annotated[str | None, StringConstraints(max_length=160)] = None


class SignRehearsal(IssueRehearsal):
    pass
