#!/usr/bin/env python3
"""
Simple NZBGet connection test script
"""
import requests
import json
import sys

def test_nzbget(host, port, username, password, use_ssl=True, verify_ssl=True):
    """Test NZBGet connection with detailed error reporting"""

    protocol = "https" if use_ssl else "http"

    # Build URL with auth
    if username and password:
        url = f"{protocol}://{username}:{password}@{host}:{port}/jsonrpc"
    else:
        url = f"{protocol}://{host}:{port}/jsonrpc"

    # Build URL for display (hide password)
    display_url = f"{protocol}://{username}:****@{host}:{port}/jsonrpc" if username else url

    print(f"Testing NZBGet connection to: {display_url}")
    print(f"SSL Verification: {verify_ssl}")
    print()

    # Test payload
    payload = {
        "jsonrpc": "2.0",
        "method": "version",
        "params": [],
        "id": 1
    }

    try:
        print("Making request...")
        response = requests.post(
            url,
            json=payload,
            timeout=10,
            verify=verify_ssl
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print()

        if response.status_code == 200:
            result = response.json()
            print(f"Response JSON: {json.dumps(result, indent=2)}")

            if "error" in result:
                print(f"\n❌ RPC Error: {result['error']}")
                return False
            elif "result" in result:
                print(f"\n✅ Success! NZBGet version: {result['result']}")
                return True
            else:
                print(f"\n⚠️  Unexpected response format")
                return False
        else:
            print(f"Response Text: {response.text}")
            print(f"\n❌ HTTP Error {response.status_code}")
            return False

    except requests.exceptions.SSLError as e:
        print(f"❌ SSL Error: {e}")
        print("\nThis might be a self-signed certificate issue.")
        print("Try running with verify_ssl=False to test without SSL verification.")
        return False

    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection Error: {e}")
        print("\nPossible issues:")
        print("- Host/port incorrect")
        print("- NZBGet not running")
        print("- Firewall blocking connection")
        print("- Wrong protocol (http vs https)")
        return False

    except requests.exceptions.Timeout as e:
        print(f"❌ Timeout Error: {e}")
        print("\nConnection timed out after 10 seconds")
        return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Request Error: {e}")
        return False

    except Exception as e:
        print(f"❌ Unexpected Error: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    # Test with user's configuration
    print("=" * 60)
    print("NZBGet Connection Test")
    print("=" * 60)
    print()

    # User's config from screenshot
    host = "downloads.akiraslingshot.tv"
    port = 443
    username = input("Enter NZBGet username (or press Enter if none): ").strip()
    password = input("Enter NZBGet password (or press Enter if none): ").strip()
    use_ssl = True

    # First try with SSL verification
    print("\n--- Test 1: With SSL verification ---")
    success = test_nzbget(host, port, username, password, use_ssl, verify_ssl=True)

    if not success:
        print("\n--- Test 2: Without SSL verification ---")
        success = test_nzbget(host, port, username, password, use_ssl, verify_ssl=False)

    if not success:
        print("\n--- Test 3: Try HTTP instead of HTTPS ---")
        success = test_nzbget(host, port, username, password, use_ssl=False, verify_ssl=False)

    if not success:
        print("\n--- Test 4: Try default NZBGet port 6789 ---")
        success = test_nzbget(host, 6789, username, password, use_ssl=False, verify_ssl=False)

    print("\n" + "=" * 60)
    if success:
        print("✅ Connection test passed!")
    else:
        print("❌ All connection tests failed")
        print("\nTroubleshooting tips:")
        print("1. Verify NZBGet is running and accessible")
        print("2. Check username/password are correct")
        print("3. Check if NZBGet is behind a reverse proxy with a different path")
        print("4. Try accessing the NZBGet web UI at https://downloads.akiraslingshot.tv:443")
    print("=" * 60)
