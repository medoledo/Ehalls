import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://register.must.edu.eg/StudentRegistrationSsb/ssb"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})

session.post(f"{BASE_URL}/term/search", data={"term": "202620"}, verify=False)
session.get(f"{BASE_URL}/classSearch/classSearch", verify=False)

resp = session.get(
    f"{BASE_URL}/classSearch/get_subject",
    params={"term": "202620", "offset": 1, "max": 5000, "searchTerm": ""},
    verify=False,
)
data = resp.json()
print(f"Actually found {len(data)} subjects with max=5000")
if data:
    print(f"First: {data[0]['code']}, Last: {data[-1]['code']}")
