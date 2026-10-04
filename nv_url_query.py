#!/usr/bin/env python3
"""
URL query parameter support for NV fuzzing framework.

Extends seed format to support query parameters alongside JSON body:
{
  "query": {"key1": "value1", "key2": "value2"},  // Optional
  "body": {...}  // Existing JSON body (optional)
}

Backward compatible: pure JSON body seeds work as before.
"""

import json
import urllib.parse
from typing import Dict, Optional, Tuple, Any


def parse_seed(seed_bytes: bytes) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Parse seed into query and body components.

    Supports two formats:
    1. Extended: {"query": {...}, "body": {...}}
    2. Legacy: {...} (pure JSON body)

    Args:
        seed_bytes: Raw seed bytes

    Returns:
        (query_dict, body_dict) where either can be None
    """
    if not seed_bytes:
        return None, None

    try:
        data = json.loads(seed_bytes.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, None

    # Extended format: {"query": {...}, "body": {...}}
    if isinstance(data, dict) and ("query" in data or "body" in data):
        query = data.get("query")
        body = data.get("body")

        # Validate query is dict or None
        if query is not None and not isinstance(query, dict):
            query = None

        # Validate body is dict or None
        if body is not None and not isinstance(body, dict):
            body = None

        return query, body

    # Legacy format: pure JSON body
    if isinstance(data, dict):
        return None, data

    return None, None


def serialize_seed(query: Optional[Dict], body: Optional[Dict]) -> bytes:
    """
    Serialize query and body into seed format.

    Args:
        query: Query parameters dict or None
        body: JSON body dict or None

    Returns:
        Serialized seed bytes
    """
    if query is None and body is None:
        return b"{}"

    # Use extended format if query present
    if query is not None:
        data = {}
        if query:
            data["query"] = query
        if body:
            data["body"] = body
        return json.dumps(data, separators=(',', ':')).encode('utf-8')

    # Legacy format: body only
    if body is not None:
        return json.dumps(body, separators=(',', ':')).encode('utf-8')

    return b"{}"


def build_query_string(query: Dict) -> str:
    """
    Build URL-encoded query string from dict.

    Handles:
    - UTF-8 encoding
    - Percent encoding
    - Multiple values (list values)
    - Empty values

    Args:
        query: Query parameters dict

    Returns:
        URL-encoded query string (without leading '?')
    """
    if not query:
        return ""

    params = []
    for key, value in query.items():
        # Handle list values (repeated keys)
        if isinstance(value, list):
            for item in value:
                params.append((key, str(item) if item is not None else ""))
        else:
            params.append((key, str(value) if value is not None else ""))

    # Use urllib.parse.urlencode for safe encoding
    return urllib.parse.urlencode(params, encoding='utf-8', safe='')


def parse_query_string(query_string: str) -> Dict:
    """
    Parse URL-encoded query string into dict.

    Args:
        query_string: URL-encoded query string (with or without leading '?')

    Returns:
        Query parameters dict
    """
    if not query_string:
        return {}

    # Remove leading '?' if present
    if query_string.startswith('?'):
        query_string = query_string[1:]

    # Parse using urllib
    params = urllib.parse.parse_qs(
        query_string,
        keep_blank_values=True,
        encoding='utf-8'
    )

    # Flatten single-value lists
    result = {}
    for key, values in params.items():
        if len(values) == 1:
            result[key] = values[0]
        else:
            result[key] = values

    return result


def construct_url(base_path: str, query: Optional[Dict]) -> str:
    """
    Construct full URL with query string.

    Args:
        base_path: Base URL path
        query: Query parameters dict or None

    Returns:
        Complete URL with query string if present
    """
    if not query:
        return base_path

    query_string = build_query_string(query)
    if not query_string:
        return base_path

    # Add query separator
    separator = '&' if '?' in base_path else '?'
    return f"{base_path}{separator}{query_string}"


def mutate_query_value(query: Dict, mutation_type: str = 'value') -> Dict:
    """
    Mutate query parameter values.

    Args:
        query: Query parameters dict
        mutation_type: Type of mutation ('value', 'boundary', 'structure')

    Returns:
        Mutated query dict
    """
    import random
    import copy

    if not query:
        return query

    result = copy.deepcopy(query)

    if mutation_type == 'value':
        # Mutate a random parameter value
        keys = list(result.keys())
        if keys:
            key = random.choice(keys)
            value = result[key]

            if isinstance(value, list):
                if value:
                    idx = random.randint(0, len(value) - 1)
                    value[idx] = _mutate_scalar(value[idx])
            else:
                result[key] = _mutate_scalar(value)

    elif mutation_type == 'boundary':
        # Add/remove parameters
        if random.random() < 0.5 and query:
            # Remove a parameter
            keys = list(result.keys())
            if keys:
                del result[random.choice(keys)]
        else:
            # Add a parameter
            result[f"param_{random.randint(1000, 9999)}"] = str(random.randint(0, 100))

    elif mutation_type == 'structure':
        # Change structure (single value <-> list)
        keys = list(result.keys())
        if keys:
            key = random.choice(keys)
            value = result[key]

            if isinstance(value, list):
                # Convert list to single value
                if value:
                    result[key] = value[0]
            else:
                # Convert single value to list
                result[key] = [value, _mutate_scalar(value)]

    return result


def _mutate_scalar(value: Any) -> Any:
    """Mutate a scalar value."""
    import random

    if isinstance(value, str):
        mutations = [
            lambda v: v + str(random.randint(0, 100)),
            lambda v: v[:len(v)//2] if len(v) > 1 else v,
            lambda v: v * 2,
            lambda v: "",
            lambda v: str(random.randint(0, 1000))
        ]
        return random.choice(mutations)(value)

    elif isinstance(value, (int, float)):
        return random.choice([value + 1, value - 1, value * 2, 0, -value])

    elif isinstance(value, bool):
        return not value

    return value
