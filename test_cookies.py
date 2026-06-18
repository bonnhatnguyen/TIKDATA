import browser_cookie3
import json

try:
    print("Trying Chrome...")
    cj = browser_cookie3.chrome(domain_name='tiktok.com')
    ms_token = None
    for cookie in cj:
        if cookie.name == 'msToken':
            ms_token = cookie.value
            break
    print(f"Chrome msToken: {ms_token}")
except Exception as e:
    print(f"Chrome error: {e}")

try:
    print("Trying Edge...")
    cj = browser_cookie3.edge(domain_name='tiktok.com')
    ms_token = None
    for cookie in cj:
        if cookie.name == 'msToken':
            ms_token = cookie.value
            break
    print(f"Edge msToken: {ms_token}")
except Exception as e:
    print(f"Edge error: {e}")
