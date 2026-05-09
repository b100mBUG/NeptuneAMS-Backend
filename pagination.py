from dataclasses import dataclass
from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel, Field

T = TypeVar("T")


@dataclass
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def get_page_params(
    page: int = Query(1, ge=1, description="1-based page"),
    page_size: int | None = Query(None, ge=1, alias="page_size"),
) -> PageParams:
    from settings import get_settings

    cfg = get_settings()
    ps = page_size if page_size is not None else cfg.default_page_size
    ps = min(ps, cfg.max_page_size)
    return PageParams(page=page, page_size=ps)


PageDep = Annotated[PageParams, Depends(get_page_params)]


class Page(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 25
