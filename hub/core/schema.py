"""A small JSON Schema check for MCP tool arguments: the subset the hub's flat tool schemas use.

Supports type (object, string, integer, number, boolean, array), required, properties,
additionalProperties (false or a schema), default (top level), enum, minLength, maxLength,
minimum, maximum, multipleOf, maxProperties, minItems, maxItems, items.
"""
from __future__ import annotations

import copy
from typing import Any

from hub.core.api import Invalid


def check(schema: dict, args: Any) -> dict:
    """Validated arguments with top-level defaults filled in. Raises Invalid with a plain line."""
    if args is None:
        args = {}
    out = _object(schema, args, "arguments")
    for name, sub in schema.get("properties", {}).items():
        if name not in out and isinstance(sub, dict) and "default" in sub:
            out[name] = copy.deepcopy(sub["default"])
    return out


def _object(schema: dict, value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise Invalid(path, f"{path} must be an object")
    props = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in value:
            raise Invalid(name, f"{name} is required")
    if "maxProperties" in schema and len(value) > schema["maxProperties"]:
        raise Invalid(path, f"{path} takes at most {schema['maxProperties']} entries")
    extra = schema.get("additionalProperties", True)
    out = {}
    for key, item in value.items():
        if item is None and key in props and key not in schema.get("required", []):
            continue                 # null for a setting is the same as leaving it out (get reports "none" as null)
        if key in props:
            out[key] = _value(props[key], item, key)
        elif extra is False:
            raise Invalid(key, f"unknown argument {key}")
        elif isinstance(extra, dict):
            out[key] = _value(extra, item, f"{path}.{key}")
        else:
            out[key] = item
    return out


def _value(schema: dict, value: Any, path: str) -> Any:
    kind = schema.get("type")
    if kind == "object":
        return _object(schema, value, path)
    if kind == "string":
        if not isinstance(value, str):
            raise Invalid(path, f"{path} must be text")
        if len(value) < schema.get("minLength", 0):
            raise Invalid(path, f"{path} must not be empty" if schema.get("minLength") == 1 else f"{path} is too short")
        if len(value) > schema.get("maxLength", 1 << 20):
            raise Invalid(path, f"{path} is too long (at most {schema['maxLength']} characters)")
    elif kind in ("integer", "number"):
        if kind == "integer" and isinstance(value, float) and value.is_integer():
            value = int(value)       # 15.0 is 15 (a model, or its JSON, may write a whole number that way)
        ok = isinstance(value, int) if kind == "integer" else isinstance(value, (int, float))
        if not ok or isinstance(value, bool):
            raise Invalid(path, f"{path} must be a {'whole ' if kind == 'integer' else ''}number")
        lo, hi = schema.get("minimum"), schema.get("maximum")
        if lo is not None and value < lo:
            raise Invalid(path, f"{path} must be at least {lo}")
        if hi is not None and value > hi:
            raise Invalid(path, f"{path} must be at most {hi}")
        step = schema.get("multipleOf")
        if step and value % step:
            raise Invalid(path, f"{path} must be a multiple of {step}")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise Invalid(path, f"{path} must be true or false")
    elif kind == "array":
        if not isinstance(value, list):
            raise Invalid(path, f"{path} must be a list")
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1 << 20):
            raise Invalid(path, f"{path} has the wrong number of items")
        if isinstance(schema.get("items"), dict):
            value = [_value(schema["items"], v, f"{path}[{i}]") for i, v in enumerate(value)]
    if "enum" in schema and value not in schema["enum"]:
        raise Invalid(path, f"{path} must be one of: {', '.join(map(str, schema['enum']))}")
    return value
