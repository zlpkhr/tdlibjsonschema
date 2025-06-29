import asyncio
from dataclasses import dataclass

import httpx
from parsel import Selector

TDLIB_DOCS_BASE_URL = "https://core.telegram.org/tdlib/docs"
OBJECT_CLASS_REFERENCE_URL = f"{TDLIB_DOCS_BASE_URL}/classtd_1_1td__api_1_1_object.html"


def build_class_url(path: str) -> str:
    return f"{TDLIB_DOCS_BASE_URL}/{path}"


@dataclass
class AbsCls:
    name: str
    url: str
    child_names: list[str]

    def __str__(self):
        return self.name


@dataclass
class FieldType:
    name: str
    cls: bool = False
    child: "FieldType | None" = None


@dataclass
class Field:
    name: str
    type: FieldType


@dataclass
class Cls:
    name: str
    url: str
    fields: list[Field]

    def __str__(self):
        return self.name


async def get_abstract_child_names(cls: AbsCls, client: httpx.AsyncClient):
    resp = await client.get(cls.url)
    selector = Selector(text=resp.text)
    names = selector.css(
        'body > div.contents > p:nth-child(2) a.el[href^="classtd"]::text'
    ).getall()
    return names


async def get_fields(cls: Cls, client: httpx.AsyncClient):
    resp = await client.get(cls.url)
    selector = Selector(text=resp.text)

    table_el = selector.css("body > div.contents > table:first-of-type")

    heading = table_el.css("table > tr.heading > td > h2::text").get()

    if heading.strip() != "Public Fields":
        return []

    field_els = table_el.css('tr[class^="memitem"] > td')

    fields = []
    for el in field_els:
        name = el.css("td.memItemRight > a.el::text").get()
        types = el.css("td.memItemLeft > a.el::text").getall()

        if len(types) > 0:
            prev = None
            for type_name in reversed(types):
                if type_name == "object_ptr" and prev is not None:
                    prev.cls = True
                    continue
                ft = FieldType(type_name, child=prev)
                prev = ft
            type = prev
        else:
            type_name = el.css("td.memItemLeft::text").get()
            type = FieldType(type_name)

        field = Field(name, type)
        fields.append(field)

    return fields


async def get_all_clss():
    async with httpx.AsyncClient() as client:
        resp = await client.get(OBJECT_CLASS_REFERENCE_URL)
        selector = Selector(text=resp.text)

        els = selector.css('body > div.contents > p:nth-child(2) a.el[href^="classtd"]')

        async def process_el(el):
            name = el.css("::text").get()
            path = el.css("::attr(href)").get()
            abstract = name[0].isupper()
            url = build_class_url(path)
            if abstract:
                abs_cls = AbsCls(name, url, [])
                abs_cls.child_names = await get_abstract_child_names(abs_cls, client)
                return abs_cls
            else:
                cls_obj = Cls(name, url, [])
                cls_obj.fields = await get_fields(cls_obj, client)
                return cls_obj

        clss = await asyncio.gather(*[process_el(el) for el in els])
        return clss


typedefjson = {
    "int32": int,
    "int53": int,
    "int64": str,
    "string": str,
    "bytes": str,
    "array": list,
}


async def main():
    classes = await get_all_clss()
    print(next(cls for cls in classes if isinstance(cls, AbsCls)))


if __name__ == "__main__":
    asyncio.run(main())
