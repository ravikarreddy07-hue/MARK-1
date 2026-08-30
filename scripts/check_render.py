import requests
import time
import sys

RENDER_API_KEY = "rnd_j5PQcZ83syCgSSufQnEkM1UReGSU"
headers = {
    "Authorization": f"Bearer {RENDER_API_KEY}",
    "Accept": "application/json"
}
service_id = "srv-da8kc73bc2fs73ahg6gg"

for i in range(20):
    r_deploys = requests.get(f"https://api.render.com/v1/services/{service_id}/deploys", headers=headers)
    if r_deploys.status_code == 200:
        latest = r_deploys.json()[0]["deploy"]
        status = latest["status"]
        dep_id = latest["id"]
        print(f"Check {i+1}: Deploy {dep_id} -> {status}", flush=True)
        if status == "live":
            print("SUCCESS: Service is LIVE on Render!", flush=True)
            break
        elif status in ("build_failed", "canceled", "deactivated"):
            print(f"Deploy ended with: {status}", flush=True)
            break
    time.sleep(5)
