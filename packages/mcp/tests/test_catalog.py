from __future__ import annotations

import pytest
from content_kit_mcp._catalog import (
    build_argv,
    build_input_schema,
    tool_name,
    tools_from_catalog,
)

# A representative slice of a real `bookkit introspect` envelope, covering a
# group command (space in the name), every option type, a paired bool flag, and
# a simple bool flag.
CATALOG = {
    "ok": True,
    "command": "introspect",
    "data": {
        "name": "bookkit",
        "commands": [
            {"name": "introspect", "description": "self-describe"},
            {
                "name": "new",
                "description": "Create a new book.",
                "arguments": [{"name": "title", "required": True, "description": "Book title."}],
                "options": [
                    {"name": "--chapters", "short": "-n", "type": "integer", "default": 1},
                    {"name": "--output", "type": "enum[text|json]", "default": "text"},
                ],
                "examples": [{"description": "x", "invocation": "bookkit new 'My Book' -n 12"}],
            },
            {
                "name": "write outline",
                "description": "Draft an outline.",
                "arguments": [{"name": "concept", "required": True}],
                "options": [
                    {"name": "--writer", "type": "enum[claude|ollama|openai]"},
                    {"name": "--output", "type": "path", "default": "outline.md"},
                ],
            },
            {
                "name": "audiobook",
                "description": "Bridge to podcastkit.",
                "options": [
                    {"name": "--book-dir", "type": "path", "default": "."},
                    {"name": "--cast", "type": "bool"},
                    {"name": "--recap/--no-recap", "type": "bool"},
                    {"name": "--output", "type": "enum[text|json]"},
                ],
            },
        ],
    },
}


@pytest.fixture
def specs():
    return {s.name: s for s in tools_from_catalog("bookkit", CATALOG)}


def test_introspect_is_not_exposed_as_a_tool(specs):
    assert "bookkit_introspect" not in specs


def test_group_command_names_are_flattened(specs):
    assert "bookkit_write_outline" in specs
    assert "bookkit_new" in specs


def test_tool_name_sanitization():
    assert tool_name("bookkit", "write outline") == "bookkit_write_outline"
    assert tool_name("podcastkit", "generate") == "podcastkit_generate"


def test_input_schema_types_and_required():
    schema = build_input_schema(CATALOG["data"]["commands"][1])  # new
    assert schema["required"] == ["title"]
    assert schema["properties"]["chapters"]["type"] == "integer"
    # --output is forced by the server, never a user-facing parameter.
    assert "output" not in schema["properties"]


def test_enum_option_becomes_string_enum():
    schema = build_input_schema(CATALOG["data"]["commands"][2])  # write outline
    assert schema["properties"]["writer"] == {
        "type": "string",
        "enum": ["claude", "ollama", "openai"],
    }


def test_example_is_appended_to_description(specs):
    assert "Example: bookkit new 'My Book' -n 12" in specs["bookkit_new"].description


def test_build_argv_positional_and_option_and_forced_json(specs):
    argv = build_argv(specs["bookkit_new"], {"title": "My Book", "chapters": 12})
    assert argv == ["bookkit", "new", "My Book", "--chapters", "12", "--output", "json"]


def test_build_argv_group_command(specs):
    argv = build_argv(specs["bookkit_write_outline"], {"concept": "a heist"})
    # write outline's --output is a *path*, not the format switch: the tool
    # must neither hide it nor append "--output json" and clobber it.
    assert argv == ["bookkit", "write", "outline", "a heist"]


def test_path_typed_output_option_is_a_real_parameter(specs):
    spec = specs["bookkit_write_outline"]
    assert spec.json_output is False
    assert "output" in spec.input_schema["properties"]
    argv = build_argv(spec, {"concept": "a heist", "output": "plans/outline.md"})
    assert argv == ["bookkit", "write", "outline", "a heist", "--output", "plans/outline.md"]


def test_build_argv_missing_required_raises(specs):
    with pytest.raises(ValueError, match="required argument"):
        build_argv(specs["bookkit_new"], {})


def test_build_argv_simple_bool_flag(specs):
    on = build_argv(specs["bookkit_audiobook"], {"cast": True})
    assert "--cast" in on
    off = build_argv(specs["bookkit_audiobook"], {"cast": False})
    assert "--cast" not in off


def test_build_argv_paired_bool_flag(specs):
    pos = build_argv(specs["bookkit_audiobook"], {"recap": True})
    assert "--recap" in pos and "--no-recap" not in pos
    neg = build_argv(specs["bookkit_audiobook"], {"recap": False})
    assert "--no-recap" in neg
