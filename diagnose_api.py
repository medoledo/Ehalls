"""
Diagnostic script: probe MUST's class search API to understand why Spring/2026 returns empty sections.
"""
import json
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://register.must.edu.eg/StudentRegistrationSsb/ssb"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://register.must.edu.eg/StudentRegistrationSsb/ssb/classSearch/classSearch",
}

session = requests.Session()
session.headers.update(HEADERS)

# Step 1: Get terms
print("=== TERMS ===")
resp = session.get(f"{BASE_URL}/classSearch/getTerms", params={"offset": 1, "max": 10}, verify=False, timeout=30)
terms = resp.json()
for t in terms:
    print(f"  {t.get('code')} - {t.get('description')}")

# Use last available term and Spring/2026 if found
term_code = terms[0]["code"]
for t in terms:
    if "2026" in t.get("description", ""):
        term_code = t["code"]
        break
print(f"\nUsing term: {term_code}")

# Step 2: Init session
print("\n=== SESSION INIT ===")
r = session.post(
    f"{BASE_URL}/term/search",
    params={"mode": "search"},
    data={"term": term_code},
    verify=False,
    timeout=30,
)
print(f"  POST term/search: {r.status_code}")

r2 = session.get(f"{BASE_URL}/classSearch/classSearch", verify=False, timeout=30)
print(f"  GET classSearch: {r2.status_code}")
print(f"  Cookies: {dict(session.cookies)}")

# Step 3: Get a few subjects
print("\n=== SUBJECTS (first 5) ===")
resp = session.get(
    f"{BASE_URL}/classSearch/get_subject",
    params={"term": term_code, "offset": 1, "max": 5, "searchTerm": ""},
    verify=False,
    timeout=30,
)
subj_data = resp.json()
print(f"  Status: {resp.status_code}, Count: {len(subj_data)}")
for s in subj_data[:5]:
    print(f"    {s.get('code')} - {s.get('description')}")

# Step 4: Try getting sections for first few subjects
if subj_data:
    for s in subj_data[:3]:
        code = s["code"]
        resp = session.get(
            f"{BASE_URL}/searchResults/searchResults",
            params={"term": term_code, "subject": code, "pageOffset": 0, "pageMaxSize": 10},
            verify=False,
            timeout=60,
        )
        payload = resp.json()
        total = payload.get("totalCount", "?")
        data = payload.get("data") or []
        print(f"\n  Subject {code}: status={resp.status_code}, totalCount={total}, data_len={len(data)}")
        if data:
            sec = data[0]
            print(f"    Sample: CRN={sec.get('courseReferenceNumber')}, Title={sec.get('courseTitle')}")
            mf = sec.get("meetingsFaculty", [])
            if mf:
                mt = mf[0].get("meetingTime", {})
                print(f"    MeetingTime: bld={mt.get('buildingDescription')}, room={mt.get('room')}, begin={mt.get('beginTime')}")
        else:
            # Print raw response snippet
            raw = resp.text[:500]
            print(f"    Raw response: {raw}")

# Try an older term if Spring/2026 has no data
print("\n=== TRY OLDER TERMS ===")
for t in terms[1:4]:
    tc = t["code"]
    r_init = session.post(f"{BASE_URL}/term/search", params={"mode": "search"}, data={"term": tc}, verify=False, timeout=30)
    r2 = session.get(f"{BASE_URL}/classSearch/classSearch", verify=False, timeout=30)
    # get first subject
    sb = session.get(f"{BASE_URL}/classSearch/get_subject", params={"term": tc, "offset": 1, "max": 1, "searchTerm": ""}, verify=False, timeout=30)
    sb_data = sb.json()
    if sb_data:
        fc = sb_data[0]["code"]
        rs = session.get(f"{BASE_URL}/searchResults/searchResults", params={"term": tc, "subject": fc, "pageOffset": 0, "pageMaxSize": 5}, verify=False, timeout=60)
        rs_payload = rs.json()
        rs_data = rs_payload.get("data") or []
        print(f"  Term {tc} ({t['description']}), subject={fc}: {len(rs_data)} sections, totalCount={rs_payload.get('totalCount', '?')}")
        if rs_data:
            print(f"    First section CRN: {rs_data[0].get('courseReferenceNumber')}")
