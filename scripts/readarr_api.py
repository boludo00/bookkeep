#!/usr/bin/env python3
import argparse
import json
from urllib.parse import urljoin

import requests


def build_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def parse_kv_pairs(values: list[str]) -> dict:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid key=value pair: {value}")
        key, val = value.split("=", 1)
        parsed[key] = val
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simple Readarr API client for quick exploration."
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Readarr base URL, e.g. https://readarr.example.com"
    )
    parser.add_argument(
        "--api-key",
        required=True,
        help="Readarr API key"
    )
    parser.add_argument(
        "--method",
        default="GET",
        help="HTTP method (GET, POST, PUT, PATCH, DELETE)"
    )
    parser.add_argument(
        "--path",
        required=True,
        help="API path, e.g. /api/v1/system/status"
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Query parameter key=value (can be used multiple times)"
    )
    parser.add_argument(
        "--data",
        help="JSON payload string for POST/PUT/PATCH"
    )
    parser.add_argument(
        "--data-file",
        help="Path to a JSON file for POST/PUT/PATCH"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON responses"
    )
    args = parser.parse_args()

    params = parse_kv_pairs(args.param)
    method = args.method.upper()
    url = build_url(args.base_url, args.path)

    payload = None
    if args.data and args.data_file:
        raise SystemExit("Use only one of --data or --data-file.")
    if args.data:
        payload = json.loads(args.data)
    elif args.data_file:
        with open(args.data_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

    headers = {
        "X-Api-Key": args.api_key,
        "Accept": "application/json",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"

    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        json=payload,
        timeout=30
    )

    print(f"{response.status_code} {response.reason}")
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        data = response.json()
        if args.pretty:
            print(json.dumps(data, indent=2))
        else:
            print(json.dumps(data))
    else:
        print(response.text)


if __name__ == "__main__":
    main()
