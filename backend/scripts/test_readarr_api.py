#!/usr/bin/env python3
"""
CLI script to test Readarr API requests
Usage:
    python test_readarr_api.py --hostname readarr.example.com --port 8787 --api-key YOUR_KEY --method PUT --endpoint /api/v1/book/1 --payload '{"authorId": 233077, "monitored": true}'
    python test_readarr_api.py --hostname readarr.example.com --port 8787 --api-key YOUR_KEY --method GET --endpoint /api/v1/book/1
    python test_readarr_api.py --hostname readarr.example.com --port 8787 --api-key YOUR_KEY --method POST --endpoint /api/v1/book --payload-file payload.json
"""

import argparse
import json
import sys
import httpx
from typing import Optional, Dict, Any


def build_readarr_url(hostname: str, port: int, use_ssl: bool = False, url_base: Optional[str] = None) -> str:
    """Build Readarr API URL from components"""
    protocol = "https" if use_ssl else "http"
    base_url = f"{protocol}://{hostname}:{port}"
    if url_base:
        url_base = url_base.strip("/")
        if url_base:
            base_url = f"{base_url}/{url_base}"
    return base_url


def load_payload(payload_str: Optional[str] = None, payload_file: Optional[str] = None) -> Optional[Dict[Any, Any]]:
    """Load payload from string or file"""
    if payload_file:
        try:
            with open(payload_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Error: File '{payload_file}' not found", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in file '{payload_file}': {e}", file=sys.stderr)
            sys.exit(1)
    elif payload_str:
        try:
            return json.loads(payload_str)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in payload: {e}", file=sys.stderr)
            sys.exit(1)
    return None


def parse_query_params(query_params: Optional[str]) -> Optional[Dict[str, str]]:
    """Parse query string parameters from string format like 'key1=value1&key2=value2'"""
    if not query_params:
        return None
    
    params = {}
    for pair in query_params.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            # URL decode the value (basic handling)
            import urllib.parse
            params[urllib.parse.unquote(key)] = urllib.parse.unquote(value)
        else:
            params[pair] = ""
    return params


def make_request(
    hostname: str,
    port: int,
    api_key: str,
    method: str,
    endpoint: str,
    use_ssl: bool = False,
    url_base: Optional[str] = None,
    payload: Optional[Dict[Any, Any]] = None,
    query_params: Optional[Dict[str, str]] = None,
    timeout: float = 30.0
) -> None:
    """Make HTTP request to Readarr API"""
    base_url = build_readarr_url(hostname, port, use_ssl, url_base)
    api_url = f"{base_url}/api/v1"
    
    # Ensure endpoint starts with /
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    
    # Remove /api/v1 if present (we'll add it)
    endpoint = endpoint.replace("/api/v1", "")
    
    # Remove any existing query string from endpoint (we'll handle it separately)
    if "?" in endpoint:
        endpoint = endpoint.split("?")[0]
    
    full_url = f"{api_url}{endpoint}"
    
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json"
    }
    
    print(f"Making {method} request to: {full_url}")
    if query_params:
        print(f"Query Parameters: {query_params}")
    if payload:
        print(f"Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        with httpx.Client(timeout=timeout) as client:
            if method.upper() == "GET":
                response = client.get(full_url, headers=headers, params=query_params)
            elif method.upper() == "POST":
                response = client.post(full_url, headers=headers, json=payload, params=query_params)
            elif method.upper() == "PUT":
                response = client.put(full_url, headers=headers, json=payload, params=query_params)
            elif method.upper() == "DELETE":
                response = client.delete(full_url, headers=headers, params=query_params)
            else:
                print(f"Error: Unsupported method '{method}'", file=sys.stderr)
                print("Supported methods: GET, POST, PUT, DELETE", file=sys.stderr)
                sys.exit(1)
            
            print(f"Status Code: {response.status_code}")
            print(f"Status: {response.status_code} {'OK' if response.status_code < 400 else 'ERROR'}")
            print()
            
            # Try to parse JSON response
            try:
                response_data = response.json()
                print("Response JSON:")
                print(json.dumps(response_data, indent=2))
            except json.JSONDecodeError:
                print("Response Text:")
                print(response.text)
            
            # Exit with error code if request failed
            if response.status_code >= 400:
                sys.exit(1)
                
    except httpx.TimeoutException:
        print("Error: Request timed out", file=sys.stderr)
        sys.exit(1)
    except httpx.ConnectError:
        print(f"Error: Could not connect to {hostname}:{port}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Test Readarr API requests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # GET request
  python test_readarr_api.py --hostname readarr.example.com --port 8787 --api-key KEY --method GET --endpoint /book/1
  
  # GET request with query parameters
  python test_readarr_api.py --hostname readarr.example.com --port 8787 --api-key KEY --method GET --endpoint /queue/details --query-params "bookIds=1"
  python test_readarr_api.py --hostname readarr.example.com --port 8787 --api-key KEY --method GET --endpoint /book --query-params "foreignBookId=123"
  python test_readarr_api.py --hostname readarr.example.com --port 8787 --api-key KEY --method GET --endpoint /book/lookup --query-params "term=work:123"
  
  # PUT request with JSON payload
  python test_readarr_api.py --hostname readarr.example.com --port 8787 --api-key KEY --method PUT --endpoint /book/1 --payload '{"monitored": true, "authorId": 233077}'
  
  # POST request with payload from file
  python test_readarr_api.py --hostname readarr.example.com --port 8787 --api-key KEY --method POST --endpoint /book --payload-file payload.json
  
  # With SSL and URL base
  python test_readarr_api.py --hostname readarr.example.com --port 443 --api-key KEY --use-ssl --url-base /readarr --method GET --endpoint /book
        """
    )
    
    parser.add_argument("--hostname", required=True, help="Readarr hostname")
    parser.add_argument("--port", type=int, required=True, help="Readarr port")
    parser.add_argument("--api-key", required=True, help="Readarr API key")
    parser.add_argument("--method", required=True, choices=["GET", "POST", "PUT", "DELETE"], help="HTTP method")
    parser.add_argument("--endpoint", required=True, help="API endpoint (e.g., /book/1 or /author/lookup?term=author:123)")
    parser.add_argument("--use-ssl", action="store_true", help="Use HTTPS")
    parser.add_argument("--url-base", help="URL base path (e.g., /readarr)")
    parser.add_argument("--payload", help="JSON payload as string")
    parser.add_argument("--payload-file", help="Path to JSON file containing payload")
    parser.add_argument("--query-params", help="Query string parameters (e.g., 'bookIds=1&term=author:123' or 'foreignBookId=123')")
    parser.add_argument("--timeout", type=float, default=30.0, help="Request timeout in seconds (default: 30)")
    
    args = parser.parse_args()
    
    # Validate payload arguments
    if args.method in ["POST", "PUT"] and not args.payload and not args.payload_file:
        print("Error: --payload or --payload-file is required for POST/PUT requests", file=sys.stderr)
        sys.exit(1)
    
    payload = load_payload(args.payload, args.payload_file)
    query_params = parse_query_params(args.query_params)
    
    make_request(
        hostname=args.hostname,
        port=args.port,
        api_key=args.api_key,
        method=args.method,
        endpoint=args.endpoint,
        use_ssl=args.use_ssl,
        url_base=args.url_base,
        payload=payload,
        query_params=query_params,
        timeout=args.timeout
    )


if __name__ == "__main__":
    main()

