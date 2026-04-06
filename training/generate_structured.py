"""
PMCore Structured Data Generator
==================================
Generates synthetic but realistic structured JSON training examples
for PMPlanner, PMReasoner, and PMCommunicator output formats.

Produces ~8,000 examples covering:
- Hotel renovation projects (target domain)
- General construction / capex
- IT / digital transformation
- Infrastructure / government
- Agile / software delivery

Each example is a valid {input, output} pair where output is the
JSON structure (or prose) the models need to learn to produce.
"""

import json
import random
import hashlib
from pathlib import Path
from itertools import product

OUT_PATH = Path("corpus/raw/synthetic_structured.jsonl")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

random.seed(42)

# ── Project Templates ─────────────────────────────────────────────────────────

HOTEL_PROJECTS = [
    ("Hotel Lobby Renovation", "Renovate the main lobby including new flooring, lighting, furniture, and front desk redesign."),
    ("Guest Room Refresh", "Refresh {n} guest rooms with new FF&E, bedding, bathroom fixtures, and artwork."),
    ("Restaurant Remodel", "Full remodel of the hotel restaurant including kitchen equipment, dining room, and bar area."),
    ("Spa & Wellness Center Build-Out", "Build out a new spa and wellness center with treatment rooms, pool, and fitness facility."),
    ("Meeting & Conference Center Upgrade", "Upgrade {n} meeting rooms with new AV technology, furniture, and breakout spaces."),
    ("Hotel Exterior & Facade Renovation", "Renovate the building exterior including signage, landscaping, entrance canopy, and parking."),
    ("PMS & Technology Upgrade", "Replace the property management system and upgrade in-room technology across all {n} rooms."),
    ("Pool & Recreation Area Renovation", "Renovate the pool deck, add cabanas, upgrade pool equipment, and refresh landscaping."),
    ("Brand Conversion & PIP Completion", "Complete property improvement plan for brand conversion from independent to franchise flag."),
    ("Fire Suppression & Life Safety Upgrade", "Upgrade fire suppression, sprinkler system, and life safety systems to current code."),
    ("HVAC & MEP Systems Replacement", "Replace aging HVAC, mechanical, electrical, and plumbing systems across the property."),
    ("Parking Structure Renovation", "Renovate {n}-space parking structure including waterproofing, lighting, and signage."),
    ("Food & Beverage Outlet Repositioning", "Reposition {n} F&B outlets with new concepts, branding, and physical renovations."),
    ("Energy Efficiency & Sustainability Retrofit", "Install solar panels, LED lighting, BMS upgrades, and EV charging stations."),
    ("Accessibility & ADA Compliance Upgrade", "Bring property into full ADA compliance including accessible rooms, pathways, and amenities."),
]

GENERAL_PROJECTS = [
    ("Office Building Renovation", "Renovate {n} floors of commercial office space with modern open-plan layout."),
    ("Data Center Build-Out", "Build out a new Tier III data center with {n} MW capacity."),
    ("Hospital Wing Expansion", "Construct a new {n}-bed patient care wing with ICU, operating rooms, and support spaces."),
    ("Highway Bridge Replacement", "Replace aging {n}-span highway bridge with new precast concrete structure."),
    ("Airport Terminal Expansion", "Expand terminal to add {n} new gates and modernize passenger experience."),
    ("ERP System Implementation", "Implement new enterprise resource planning system across {n} business units."),
    ("Manufacturing Plant Upgrade", "Upgrade production line with new automated equipment and quality control systems."),
    ("Retail Store Rollout", "Roll out new store format across {n} locations over {t} months."),
    ("Cybersecurity Infrastructure Overhaul", "Overhaul cybersecurity infrastructure including SIEM, zero-trust architecture, and SOC."),
    ("Smart Building Retrofit", "Retrofit {n}-story building with IoT sensors, smart HVAC, and integrated BMS."),
]

METHODOLOGIES = ["Hybrid", "Agile", "Waterfall", "PRINCE2", "Scrum", "PMP"]
HEALTH_STATES = ["green", "yellow", "red"]
SEVERITY = ["low", "medium", "high"]

RISK_TYPES = [
    ("Schedule Delay", "Add 15% schedule buffer and track velocity weekly via earned value metrics."),
    ("Budget Overrun", "Implement change control board and bi-weekly cost reviews against baseline."),
    ("Scope Creep", "Lock scope with signed charter; all changes require CCB approval and re-baseline."),
    ("Resource Availability", "Identify backup resources and cross-train team members on critical path tasks."),
    ("Vendor/Contractor Risk", "Qualify alternate vendors; include penalty clauses and milestone payments in contracts."),
    ("Regulatory/Permit Risk", "Engage AHJ early in design phase; track permit timeline on critical path."),
    ("Supply Chain Disruption", "Order long-lead items in phase 1; maintain buffer stock for critical materials."),
    ("Stakeholder Alignment", "Weekly steering committee reviews; escalation matrix defined in project charter."),
    ("Technical Complexity", "Prototype critical systems in phase 1; engage specialist consultants early."),
    ("Quality/Defect Risk", "Define quality gates at each phase; independent QA inspection before handover."),
    ("Environmental/Weather", "Build weather contingency days into schedule; purchase weather delay insurance."),
    ("Financial/Funding Risk", "Secure funding commitment before mobilization; monthly financial forecast reviews."),
    ("Change Management Risk", "Develop change management plan; stakeholder communication cadence from day 1."),
    ("Safety/OSHA Risk", "Site safety plan with daily toolbox talks; zero-tolerance safety policy enforced."),
]

PHASES = {
    "construction": [
        ("Initiation & Planning", 10),
        ("Design & Engineering", 21),
        ("Permitting & Procurement", 14),
        ("Mobilization", 5),
        ("Construction / Execution", 0),  # filled dynamically
        ("Inspections & Commissioning", 10),
        ("Punch List & Closeout", 7),
    ],
    "it": [
        ("Discovery & Requirements", 14),
        ("Solution Design", 21),
        ("Development / Configuration", 0),
        ("Testing & QA", 14),
        ("Training & Change Management", 10),
        ("Go-Live & Hypercare", 7),
        ("Project Closeout", 5),
    ],
    "agile": [
        ("Sprint 0 / Setup", 14),
        ("Sprint 1", 14),
        ("Sprint 2", 14),
        ("Sprint 3", 14),
        ("Sprint 4", 14),
        ("Sprint 5", 14),
        ("UAT & Release", 14),
    ],
}

COMM_TYPES = [
    "Write a professional project kickoff summary for stakeholders.",
    "Write a weekly status report for the ownership group.",
    "Write a risk escalation email to the executive team.",
    "Write an executive summary for the board.",
    "Write a project update email to all stakeholders.",
    "Write a milestone completion announcement.",
    "Write a scope change request memo.",
    "Write a budget variance explanation to the CFO.",
    "Write a vendor selection recommendation.",
    "Write a project closeout report.",
]

PLANNER_QUESTIONS = [
    "What are the project objectives, budget, timeline, and risk factors for this project?",
    "Describe the project scope, implementation plan, and risk management approach.",
    "What is the project work breakdown structure, milestones, and expected outcomes?",
    "Create a structured project plan with tasks, dependencies, and timeline.",
    "Break down this project into phases, tasks, and deliverables with a timeline.",
    "What are the key workstreams, milestones, and resource requirements for this project?",
]

REASONER_QUESTIONS = [
    "Analyze the risks, critical path, and constraints for this project.",
    "What are the primary risks and mitigation strategies for this project?",
    "Identify the critical path, risks, and overall project health.",
    "Perform a risk assessment and critical path analysis for this project.",
    "What risk factors and constraints should the project manager focus on?",
]


# ── Builder functions ─────────────────────────────────────────────────────────

def pick_project():
    pool = HOTEL_PROJECTS + GENERAL_PROJECTS
    tmpl = random.choice(pool)
    name_tmpl, desc_tmpl = tmpl
    n = random.choice([20, 40, 50, 80, 100, 120, 200, 300, 500])
    t = random.choice([6, 8, 10, 12, 16, 18, 24])
    name = name_tmpl.format(n=n, t=t)
    desc = desc_tmpl.format(n=n, t=t)
    return name, desc


def pick_budget(name: str) -> int:
    if any(w in name.lower() for w in ["hospital", "airport", "bridge", "highway"]):
        return random.randint(10, 500) * 1_000_000
    if any(w in name.lower() for w in ["data center", "erp", "cyber"]):
        return random.randint(2, 50) * 1_000_000
    if any(w in name.lower() for w in ["hotel", "guest room", "lobby", "restaurant"]):
        return random.randint(500, 10_000) * 1_000
    return random.randint(1, 20) * 1_000_000


def pick_phase_type(name: str) -> str:
    if any(w in name.lower() for w in ["erp", "pms", "cyber", "technology", "system", "software"]):
        return random.choice(["it", "agile"])
    return "construction"


def build_tasks(phase_type: str, duration_days: int, methodology: str) -> list:
    template = PHASES[phase_type]
    tasks = []
    remaining = duration_days

    for i, (phase_name, fixed_days) in enumerate(template):
        if fixed_days == 0:
            # Execution phase gets remaining days minus fixed days ahead
            fixed_ahead = sum(d for _, d in template[i+1:])
            dur = max(7, remaining - fixed_ahead)
        else:
            dur = fixed_days
        remaining -= dur

        task = {
            "id": f"T{i+1:02d}",
            "name": phase_name,
            "duration_days": dur,
            "dependencies": [f"T{i:02d}"] if i > 0 else [],
            "owner": random.choice(["Project Manager", "GC", "PM Team", "Design Team",
                                     "IT Team", "Vendor", "Operations"]),
            "phase": phase_name.split("/")[0].strip(),
            "status": "not_started",
        }
        tasks.append(task)

    return tasks


def build_planner_json(name: str, desc: str, methodology: str,
                       duration_days: int, budget: int) -> dict:
    phase_type = pick_phase_type(name)
    tasks = build_tasks(phase_type, duration_days, methodology)

    return {
        "project": {
            "name": name,
            "description": desc,
            "methodology": methodology,
            "estimated_duration_days": duration_days,
            "budget_usd": budget,
            "status": "planning",
            "start_date": "TBD",
        },
        "tasks": tasks,
        "milestones": [
            {"name": "Project Kickoff", "day": 1},
            {"name": "Design Complete", "day": duration_days // 4},
            {"name": "Midpoint Review", "day": duration_days // 2},
            {"name": "Substantial Completion", "day": int(duration_days * 0.9)},
            {"name": "Final Closeout", "day": duration_days},
        ],
        "resources": {
            "team_size": random.randint(3, 15),
            "key_roles": ["Project Manager", "Design Lead", "Construction Manager",
                          "Owner's Rep", "QA Inspector"],
        },
    }


def build_reasoner_json(planner: dict, health: str) -> dict:
    num_risks = random.randint(3, 6)
    selected_risks = random.sample(RISK_TYPES, num_risks)
    duration = planner["project"]["estimated_duration_days"]
    tasks = planner["tasks"]
    critical = [t["name"] for t in tasks[:4]]

    risks = []
    for rtype, mitigation in selected_risks:
        severity = random.choice(SEVERITY)
        risks.append({
            "type": rtype,
            "severity": severity,
            "probability": random.choice(["low", "medium", "high"]),
            "impact": random.choice(["low", "medium", "high"]),
            "mitigation": mitigation,
            "owner": "Project Manager",
        })

    # Health driven by number of high risks
    high_risk_count = sum(1 for r in risks if r["severity"] == "high")
    if high_risk_count >= 2:
        health = "red"
    elif high_risk_count == 1:
        health = "yellow"
    else:
        health = "green"

    return {
        "overall_health": health,
        "health_summary": {
            "green": "Project is on track with manageable risks.",
            "yellow": "Project has moderate risks requiring active monitoring.",
            "red": "Project has critical risks requiring immediate escalation.",
        }[health],
        "risks": risks,
        "critical_path": {
            "tasks": critical,
            "total_duration_days": duration,
            "float_days": max(0, duration // 10),
            "critical_tasks_count": len(critical),
        },
        "constraints": [
            f"Total budget: ${planner['project']['budget_usd']:,}",
            f"Deadline: {duration} days from NTP",
            "Operational continuity required during construction",
        ],
        "recommendations": [
            "Establish PMO governance structure before kickoff",
            "Lock scope with signed charter before procurement",
            "Weekly steering committee reviews during execution",
            "Implement earned value management from day 1",
        ],
        "earned_value": {
            "planned_value": 0,
            "earned_value": 0,
            "actual_cost": 0,
            "spi": 1.0,
            "cpi": 1.0,
            "status": "Not started",
        },
    }


# ── Generate records ──────────────────────────────────────────────────────────

COMM_REQUESTS = [
    "Write a professional project kickoff summary for stakeholders.",
    "Draft a project status update email for the project sponsor.",
    "Write an executive summary of the project plan and risks.",
    "Compose a risk escalation memo for senior leadership.",
    "Draft a weekly status report for the project team.",
    "Write a project initiation announcement for all stakeholders.",
    "Create a concise project overview for the steering committee.",
    "Draft a go/no-go decision brief for project leadership.",
    "Write a project health summary suitable for a board update.",
    "Compose a project kickoff agenda and talking points.",
]

HEALTH_TO_WORD = {
    "green": "on track",
    "yellow": "at risk",
    "red": "off track",
}

COMM_TEMPLATES = [
    # Kickoff summary
    lambda n, d, tasks, risks, health, weeks, budget_str, method: (
        f"Subject: Project Kickoff — {n}\n\n"
        f"Team,\n\n"
        f"We are officially kicking off the {n} project. Here is a summary of our plan:\n\n"
        f"Project Overview: {d}\n\n"
        f"Methodology: {method}\n"
        f"Timeline: {weeks} weeks ({weeks * 7} days)\n"
        f"Budget: {budget_str}\n"
        f"Overall Health: {health.upper()}\n\n"
        f"Key Milestones:\n" +
        "".join(f"  - {t['name']} ({t['duration_days']} days)\n" for t in tasks[:4]) +
        f"\nTop Risks:\n" +
        "".join(f"  - {r['type']}: {r['mitigation']}\n" for r in risks[:3]) +
        f"\nPlease review the attached plan and confirm your availability for the kickoff meeting.\n\n"
        f"Best regards,\nProject Manager"
    ),
    # Status report
    lambda n, d, tasks, risks, health, weeks, budget_str, method: (
        f"PROJECT STATUS REPORT — {n}\n"
        f"{'=' * 60}\n\n"
        f"Status: {HEALTH_TO_WORD.get(health, 'at risk').upper()}\n"
        f"Methodology: {method} | Timeline: {weeks} weeks | Budget: {budget_str}\n\n"
        f"SUMMARY\n{d}\n\n"
        f"WORKSTREAMS\n" +
        "".join(f"  [{t['id']}] {t['name']} — {t['duration_days']} days — {t['status'].replace('_', ' ').title()}\n" for t in tasks[:5]) +
        f"\nRISK REGISTER\n" +
        "".join(f"  {r['severity'].upper()} | {r['type']}: {r['mitigation']}\n" for r in risks[:3]) +
        f"\nRECOMMENDATION\nContinue execution per plan. Next steering committee: end of week.\n"
    ),
    # Executive summary
    lambda n, d, tasks, risks, health, weeks, budget_str, method: (
        f"EXECUTIVE SUMMARY: {n}\n\n"
        f"This project involves {d.lower()} "
        f"The initiative will be delivered using a {method} approach over {weeks} weeks "
        f"with a total investment of {budget_str}.\n\n"
        f"The project is currently {HEALTH_TO_WORD.get(health, 'at risk')}. "
        f"Key deliverables include: " +
        ", ".join(t['name'] for t in tasks[:3]) + ".\n\n"
        f"Primary risks include " +
        " and ".join(r['type'].lower() for r in risks[:2]) +
        f". Mitigation plans are in place and will be reviewed weekly.\n\n"
        f"Leadership approval is requested to proceed to execution phase."
    ),
    # Risk escalation
    lambda n, d, tasks, risks, health, weeks, budget_str, method: (
        f"RISK ESCALATION MEMO\n\n"
        f"Project: {n}\n"
        f"Health: {health.upper()} — Immediate attention required\n\n"
        f"This memo escalates critical risks identified during {n} planning.\n\n"
        f"CRITICAL RISKS:\n" +
        "".join(
            f"  {i+1}. {r['type']} (Severity: {r['severity'].upper()}, Probability: {r['probability'].upper()})\n"
            f"     Mitigation: {r['mitigation']}\n"
            for i, r in enumerate(risks[:3])
        ) +
        f"\nIMPACT\nWithout immediate action, the project risks missing its {weeks}-week deadline "
        f"and exceeding the {budget_str} budget.\n\n"
        f"ACTION REQUIRED\nSteering committee decision needed within 48 hours.\n"
    ),
]


def build_communicator_record(
    name: str,
    desc: str,
    planner_json: dict,
    reasoner_json: dict,
    request_str: str,
) -> dict:
    """Build a PMCommunicator training record with <|project_context|> token."""
    tasks = planner_json.get("tasks", [])
    proj = planner_json.get("project", {})
    risks = reasoner_json.get("risks", [])
    health = reasoner_json.get("overall_health", "yellow")
    method = proj.get("methodology", "Hybrid")
    duration_days = proj.get("estimated_duration_days", 84)
    budget = proj.get("budget_usd", 500000)
    weeks = duration_days // 7
    budget_str = (f"${budget // 1_000_000}M" if budget >= 1_000_000
                  else f"${budget // 1_000}K")

    comm_request = random.choice(COMM_REQUESTS)

    context = {
        "project_summary": request_str,
        "num_tasks": len(tasks),
        "methodology": method,
        "duration_days": duration_days,
        "health": f"{health.upper()}",
        "top_risks": [r["type"] for r in risks[:3]],
        "critical_path_tasks": [t["name"] for t in tasks[:4]],
    }

    template = random.choice(COMM_TEMPLATES)
    prose_output = template(name, desc, tasks, risks, health, weeks, budget_str, method)

    return {
        "source": "synthetic_communicator",
        "text": (
            f"<|pm_request|>\n{comm_request}\n"
            f"<|project_context|>\n{json.dumps(context, indent=2)}\n"
            f"<|response|>\n{prose_output}\n<|end|>"
        ),
        "format": "structured_prose",
    }


def make_request_string(name: str, desc: str, budget: int, duration_days: int) -> str:
    weeks = duration_days // 7
    budget_str = (f"${budget // 1_000_000}M" if budget >= 1_000_000
                  else f"${budget // 1_000}K")
    templates = [
        f"Plan a {name.lower()}. Budget {budget_str}, {weeks}-week deadline.",
        f"Create a project plan for: {desc} Budget: {budget_str}. Timeline: {weeks} weeks.",
        f"{name}: {desc} Total budget {budget_str} with a {duration_days}-day schedule.",
        f"We need to execute a {name.lower()}. Allocated budget: {budget_str}. Must complete in {weeks} weeks.",
        f"Project scope: {desc} Budget {budget_str}, {weeks} weeks, starting immediately.",
    ]
    return random.choice(templates)


def generate():
    records = []
    seen = set()

    target = 8000
    attempts = 0

    while len(records) < target and attempts < target * 3:
        attempts += 1

        name, desc = pick_project()
        methodology = random.choice(METHODOLOGIES)
        duration_days = random.choice([28, 35, 42, 56, 63, 70, 84, 90, 112, 120, 140, 168, 180])
        budget = pick_budget(name)
        health = random.choice(HEALTH_STATES)

        request_str = make_request_string(name, desc, budget, duration_days)

        planner_json = build_planner_json(name, desc, methodology, duration_days, budget)
        reasoner_json = build_reasoner_json(planner_json, health)

        # Deduplicate on project name + duration combo
        key = hashlib.md5(f"{name}{duration_days}{budget}".encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)

        # PMPlanner record — use EXACT training format with special tokens
        # train.py wraps as: <|pm_request|>\n{input}\n<|response|>\n{output}\n<|end|>
        planner_q = random.choice(PLANNER_QUESTIONS)
        planner_record = {
            "source": "synthetic_planner",
            "input": f"{planner_q}\n\n{request_str}",
            "output": json.dumps(planner_json, indent=2),
            "format": "structured_json",
        }

        # PMReasoner record — includes task graph context via <|task_graph|>
        # Use the text format so train.py wraps it correctly
        reasoner_q = random.choice(REASONER_QUESTIONS)
        task_graph_summary = json.dumps(planner_json, indent=2)[:800]
        reasoner_record = {
            "source": "synthetic_reasoner",
            "text": (
                f"<|pm_request|>\n{reasoner_q}\n\n{request_str}\n"
                f"<|task_graph|>\n{task_graph_summary}\n"
                f"<|response|>\n{json.dumps(reasoner_json, indent=2)}\n<|end|>"
            ),
            "format": "structured_json",
        }

        records.append(planner_record)
        records.append(reasoner_record)

        # PMCommunicator record — natural language output with <|project_context|> token
        comm_record = build_communicator_record(
            name, desc, planner_json, reasoner_json, request_str
        )
        records.append(comm_record)

    random.shuffle(records)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(f"Generated {len(records):,} structured records -> {OUT_PATH}")
    return len(records)


if __name__ == "__main__":
    print("Generating synthetic structured training data...")
    n = generate()
    print(f"Done. {n:,} records written.")
