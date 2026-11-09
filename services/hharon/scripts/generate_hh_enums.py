# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx>=0.28.1",
# ]
# ///


from pathlib import Path
import sys
import httpx


def to_camel_case(snake_str: str) -> str:
    return "".join(x.capitalize() for x in snake_str.lower().split("_"))


def generate_python_enum(data: dict[str, list[dict[str, str]]]) -> str:
    content = "from enum import StrEnum\n\n\n"
    for enum_name, enum_values in data.items():
        content += f"class {to_camel_case(enum_name)}Enum(StrEnum):\n"
        for value in enum_values:
            id: str | None = value.get("id") or value.get("code")
            if id is None:
                continue

            name = id.upper()
            if len(name) > 0 and not name[0].isalpha():
                name = "VALUE_" + name

            comment = value.get("name")

            content += f'    {name} = "{id}"'
            if comment:
                content += f'\n    """ {comment.replace("\xa0", " ")} """\n'
            else:
                content += "\n"

        content += "\n\n"

    return content


def generate_proto_enum(data: dict[str, list[dict[str, str]]]) -> str:
    content = 'syntax = "proto3";\n\npackage hharon_api.v1;\n\n'

    for enum_name, enum_values in data.items():
        content += f"enum {to_camel_case(enum_name)} {{\n"
        content += f"  {enum_name.upper()}_UNSPECIFIED = 0;\n"
        field_increment = 1

        for value in enum_values:
            id: str | None = value.get("id") or value.get("code")
            if id is None:
                continue

            name = enum_name.upper() + "_" + id.upper()
            comment = value.get("name", "").replace("\xa0", " ") or id

            content += f"  // {comment}\n"
            content += f"  {name} = {field_increment};\n"
            field_increment += 1

        content += "}\n\n"

    return content


def generate_mappers(data: dict[str, list[dict[str, str]]]) -> str:
    content = "from typing import ClassVar, final\n\n"
    content += "import hharon.pkg.hhapi.dictionaries as hh\n"
    content += "import hharon_api.v1.headhunter_pb2 as proto\n\n\n"

    for enum_name, enum_values in data.items():
        python_enum = to_camel_case(enum_name) + "Enum"
        proto_enum = to_camel_case(enum_name)
        proto_zero = enum_name.upper() + "_UNSPECIFIED"

        content += f"@final\n"
        content += f"class {to_camel_case(enum_name)}Mapper:\n"

        content += (
            f"    {enum_name.upper()}_PROTO: ClassVar[dict[hh.{python_enum}, proto.{proto_enum}.ValueType]] = {{\n"
        )
        for value in enum_values:
            id: str | None = value.get("id") or value.get("code")
            if id is None:
                continue

            proto_name = enum_name.upper() + "_" + id.upper()

            python_name = id.upper()
            if len(python_name) > 0 and not python_name[0].isalpha():
                python_name = "VALUE_" + python_name
            python_name = python_enum + "." + python_name

            content += f"        hh.{python_name}: proto.{proto_name},\n"
        content += f"     }}\n"

        content += (
            f"    {enum_name.upper()}_PYTHON: ClassVar[dict[proto.{proto_enum}.ValueType, hh.{python_enum}]] = {{\n"
        )
        for value in enum_values:
            id: str | None = value.get("id") or value.get("code")
            if id is None:
                continue

            proto_name = enum_name.upper() + "_" + id.upper()

            python_name = id.upper()
            if len(python_name) > 0 and not python_name[0].isalpha():
                python_name = "VALUE_" + python_name
            python_name = python_enum + "." + python_name

            content += f"        proto.{proto_name}: hh.{python_name},\n"
        content += f"     }}\n"

        content += f"    @classmethod\n"
        content += f"    def to_proto(cls, value: hh.{python_enum}) -> proto.{proto_enum}.ValueType:\n"
        content += f"        return cls.{enum_name.upper()}_PROTO.get(value, proto.{proto_zero})\n"
        content += f"\n\n"
        content += f"    @classmethod\n"
        content += f"    def to_python(cls, value: proto.{proto_enum}.ValueType) -> hh.{python_enum} | None:\n"
        content += f"        return cls.{enum_name.upper()}_PYTHON.get(value, None)\n"

        content += "\n\n\n"

    return content


def main() -> None:
    data: dict[str, list[dict[str, str]]] = httpx.get("https://api.hh.ru/dictionaries").json()  # pyright: ignore[reportAny]

    match sys.argv[1]:
        case "python":
            content = generate_python_enum(data)
        case "proto":
            content = generate_proto_enum(data)
        case "mappers":
            content = generate_mappers(data)
        case _:
            print("Invalid target")
            sys.exit(1)

    path = Path(sys.argv[2])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        _ = f.write(content)


if __name__ == "__main__":
    main()
