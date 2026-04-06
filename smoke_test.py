#!/usr/bin/env python3
"""PMCore 7-test smoke suite."""
import urllib.request, json, time

BASE = "http://localhost:8765"

def post(endpoint, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{endpoint}", data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

tests = [
    ("/communicate", {"project_request": "Office HQ relocation to new building, 400 staff, 8 weeks.",
                      "request": "Write a stakeholder kickoff announcement."}, "kickoff"),
    ("/communicate", {"project_request": "Cloud migration of 50 legacy apps, 18 months, budget 8M.",
                      "request": "Write a weekly status report."}, "status_report"),
    ("/communicate", {"project_request": "New product launch mobile payment app, Q2 deadline.",
                      "request": "Write a risk escalation memo to the executive team."}, "escalation"),
    ("/communicate", {"project_request": "Hospital EHR implementation, 24 months, 12M budget.",
                      "request": "Write an executive summary for the board."}, "board"),
    ("/plan/quick",  {"request": "Rebrand company new logo website marketing materials 3 months."}, "planner_json"),
    ("/communicate", {"project_request": "Data center decommission, 200 servers, 6 months.",
                      "request": "Write a project closeout report."}, "closeout"),
    ("/health",      None, "health"),
]

passed = 0
for i, (endpoint, body, label) in enumerate(tests, 1):
    try:
        t0 = time.time()
        if body is None:
            with urllib.request.urlopen(f"{BASE}{endpoint}", timeout=10) as r:
                result = json.loads(r.read())
        else:
            result = post(endpoint, body)
        ms = int((time.time()-t0)*1000)

        if endpoint == "/health":
            ok = result.get("status") == "healthy"
            status = "PASS" if ok else "FAIL"
            print(f"  Test {i}/7 [{label}]: {status} ({ms}ms)")
        elif endpoint == "/plan/quick":
            meth = result.get("planner", {}).get("methodology", "?")
            health = result.get("reasoner", {}).get("overall_health", "?")
            ok = meth != "?" and health != "?"
            status = "PASS" if ok else "FAIL"
            print(f"  Test {i}/7 [{label}]: {status} | {meth} | {health} ({ms}ms)")
        else:
            comm = result.get("communication", "")
            ok = len(comm) > 100
            status = "PASS" if ok else "FAIL"
            preview = comm[:120].replace('\n', ' ')
            print(f"  Test {i}/7 [{label}]: {status} ({ms}ms) len={len(comm)}")
            print(f"    Preview: {repr(preview)}")

        if ok:
            passed += 1
    except Exception as e:
        print(f"  Test {i}/7 [{label}]: ERROR -- {e}")

print("")
print("="*50)
print(f"Results: {passed}/7 passed")
