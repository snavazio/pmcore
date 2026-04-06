#!/usr/bin/env python3
"""
Generate a sample outputs report with full, untruncated communications.
Runs 10 diverse projects through the full pipeline and writes a readable report.
"""
import json, time, urllib.request
from pathlib import Path

BASE = "http://localhost:8765"
OUT  = Path("sample_outputs_report.md")

SAMPLES = [
    ("Build a 40-story luxury residential tower in downtown Chicago. Budget $250M, 36 months, 120-person team.",
     "Write a project kickoff email to the project team."),
    ("Migrate enterprise from on-prem SAP to SAP S4/HANA cloud. 3000 users, Budget $15M, 18 months.",
     "Write a weekly status report for stakeholders."),
    ("Launch Phase III clinical trial for oncology drug, 3000 patients, 30 sites. Budget $80M, 48 months.",
     "Write a risk escalation memo to the executive team."),
    ("Implement Epic EHR across 8-hospital health system, 12000 staff. Budget $35M, 30 months.",
     "Write an executive summary for the board."),
    ("Construct offshore wind farm, 500MW, 80 turbines. Budget $2B, 60 months.",
     "Write a board update on project status."),
    ("Build a real-time fraud detection ML platform processing 10M transactions/day. Budget $6M, 12 months.",
     "Write a project closeout report."),
    ("Launch a streaming platform competing with Netflix — 10K titles, 5M subscribers year 1. Budget $50M, 24 months.",
     "Write an executive summary for the board."),
    ("Achieve net-zero carbon emissions across global operations by 2030. Budget $50M, 48 months.",
     "Write a risk escalation memo to the executive sponsor."),
    ("Implement unified 911 emergency dispatch platform, 50 PSAPs. Budget $40M, 24 months.",
     "Write a weekly status report."),
    ("Build lithium-ion battery gigafactory, 10GWh annual output. Budget $800M, 48 months.",
     "Write a project kickoff email to all stakeholders."),
]

def post(endpoint, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{endpoint}", data=data,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

lines = [
    "# PMCore v6 — Sample Full Pipeline Outputs",
    f"*Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}*",
    "",
    "Each sample shows the full pipeline: PMPlanner → PMReasoner → PMCommunicator (Phi-3.5)",
    "",
    "---",
    "",
]

for i, (project, comm_req) in enumerate(SAMPLES, 1):
    print(f"[{i}/10] Running: {project[:60]}...")
    t0 = time.time()
    try:
        d = post("/plan", {"request": project, "comm_request": comm_req, "verbose": False})
        ms = int((time.time()-t0)*1000)

        p = d.get("planner", {})
        r = d.get("reasoner", {})
        c = d.get("communicator", {})

        lines += [
            f"## Sample {i}: {comm_req}",
            "",
            f"**Project:** {project}",
            "",
            f"**Pipeline:** {p.get('methodology','?')} | {p.get('duration_days','?')} days | "
            f"{p.get('num_tasks','?')} tasks | Health: {r.get('overall_health','?').upper()} | "
            f"Latency: {ms/1000:.1f}s",
            "",
            f"**Top Risks:** {', '.join(r.get('top_risks', [])[:3]) or 'none'}",
            "",
            "**Communication Output:**",
            "```",
            c.get("communication", "(no output)"),
            "```",
            "",
            "---",
            "",
        ]
        print(f"  → {c.get('comm_type','?')} | {len(c.get('communication',''))} chars | {ms/1000:.1f}s")
    except Exception as e:
        lines += [f"## Sample {i}: ERROR", f"> {e}", "", "---", ""]
        print(f"  → ERROR: {e}")

OUT.write_text("\n".join(lines))
print(f"\nReport written to {OUT}")
