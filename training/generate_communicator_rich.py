"""
PMCommunicator Rich Synthetic Data Generator
=============================================
Generates high-quality, diverse training records for PMCommunicator.
Produces ~15,000 records covering:
- 28 request types across kickoff, status, risk, budget, closeout, board comms
- 12 prose templates (email, memo, brief, agenda, status report, board deck, etc.)
- Planning AND in-progress project states with EV metrics
- All 3 health states (GREEN / YELLOW / RED) with appropriate language
- Variable prose length (100-600 words)
- Real PM vocabulary: SPI, CPI, EV, PV, AC, earned value, float, critical path

Output: corpus/raw/synthetic_communicator_rich.jsonl
"""

import json
import random
import hashlib
from pathlib import Path

OUT_PATH = Path("corpus/raw/synthetic_communicator_rich.jsonl")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

random.seed(99)

# ── Projects ──────────────────────────────────────────────────────────────────

PROJECTS = [
    ("Hotel Lobby Renovation", "Renovate the main lobby including new flooring, lighting, furniture, and front desk redesign."),
    ("Guest Room Refresh — {n} Rooms", "Refresh {n} guest rooms with new FF&E, bedding, bathroom fixtures, and updated artwork packages."),
    ("Restaurant & Bar Remodel", "Full remodel of the hotel restaurant and bar including kitchen equipment, dining room, and service areas."),
    ("Spa & Wellness Center Build-Out", "Build out a new spa and wellness center with treatment rooms, pool, steam room, and fitness facility."),
    ("Conference Center Upgrade", "Upgrade {n} meeting rooms with new AV technology, flexible furniture systems, and refreshed finishes."),
    ("Hotel Exterior & Facade Renovation", "Renovate the building exterior including new signage, landscaping, entrance canopy, and valet area."),
    ("PMS & Technology Upgrade", "Replace the property management system and upgrade in-room technology across all {n} rooms."),
    ("Pool Deck & Recreation Area Renovation", "Renovate the pool deck, install new cabanas, upgrade pool equipment, and refresh surrounding landscaping."),
    ("Brand Conversion & PIP Completion", "Complete property improvement plan for brand conversion from independent to franchise flag."),
    ("Fire Suppression & Life Safety Upgrade", "Upgrade fire suppression, sprinkler system, and life safety systems to current code requirements."),
    ("HVAC & MEP Systems Replacement", "Replace aging HVAC, mechanical, electrical, and plumbing systems across the property."),
    ("Parking Structure Renovation", "Renovate {n}-space parking structure including waterproofing, new lighting, and updated wayfinding."),
    ("Food & Beverage Outlet Repositioning", "Reposition {n} F&B outlets with new concepts, branding, and physical renovations."),
    ("Energy Efficiency & Sustainability Retrofit", "Install solar panels, LED lighting throughout, BMS upgrades, and EV charging stations."),
    ("Accessibility & ADA Compliance Upgrade", "Bring property into full ADA compliance including accessible rooms, pathways, and all amenities."),
    ("Office Building Renovation", "Renovate {n} floors of commercial office space with modern open-plan layout and new MEP infrastructure."),
    ("Data Center Build-Out", "Build out a new Tier III data center with redundant power, cooling, and {n}MW capacity."),
    ("Hospital Wing Expansion", "Construct a new {n}-bed patient care wing with ICU, operating rooms, and support spaces."),
    ("Airport Terminal Expansion", "Expand terminal to add {n} new gates and modernize passenger experience throughout."),
    ("ERP System Implementation", "Implement new enterprise resource planning system across {n} business units with full data migration."),
    ("Manufacturing Plant Upgrade", "Upgrade production line with automated equipment, quality control systems, and safety improvements."),
    ("Retail Store Rollout", "Roll out new store format across {n} locations over {t} months with standardized fit-out packages."),
    ("Cybersecurity Infrastructure Overhaul", "Overhaul cybersecurity infrastructure including SIEM, zero-trust architecture, and 24/7 SOC."),
    ("Smart Building Retrofit", "Retrofit {n}-story building with IoT sensors, smart HVAC, occupancy analytics, and integrated BMS."),
    ("Highway Bridge Replacement", "Replace aging {n}-span highway bridge with new precast concrete structure and improved drainage."),
    ("Wastewater Treatment Plant Upgrade", "Upgrade wastewater treatment capacity and install advanced nutrient removal systems."),
    ("School Campus Modernization", "Modernize {n} buildings with new HVAC, electrical, roof systems, and accessibility improvements."),
    ("Luxury Condo Tower Construction", "Construct {n}-story luxury residential tower with {n2} units, amenity floor, and below-grade parking."),
]

METHODOLOGIES = ["Hybrid", "Agile", "Waterfall", "PRINCE2", "Scrum"]
HEALTH_STATES = ["GREEN", "YELLOW", "RED"]
SEVERITY = ["Low", "Medium", "High"]

RISK_TYPES = [
    ("Schedule Delay", "Add 15% schedule buffer; track velocity weekly via earned value metrics."),
    ("Budget Overrun", "Implement change control board; conduct bi-weekly cost reviews against baseline."),
    ("Scope Creep", "Lock scope with signed charter; all changes require CCB approval and re-baseline."),
    ("Resource Availability", "Identify backup resources; cross-train team members on all critical-path tasks."),
    ("Vendor/Contractor Risk", "Qualify alternate vendors; include penalty clauses and milestone payments in all contracts."),
    ("Regulatory/Permit Risk", "Engage authority having jurisdiction early in design; track permit timeline on critical path."),
    ("Supply Chain Disruption", "Order long-lead items in phase 1; maintain buffer stock for all critical materials."),
    ("Stakeholder Alignment", "Weekly steering committee reviews; escalation matrix defined in project charter."),
    ("Technical Complexity", "Prototype critical systems in phase 1; engage specialist consultants early in design."),
    ("Quality/Defect Risk", "Define quality gates at each phase; independent QA inspection before handover."),
    ("Environmental/Weather", "Build weather contingency into schedule; consider weather delay insurance for critical phases."),
    ("Financial/Funding Risk", "Secure funding commitment before mobilization; monthly financial forecast reviews required."),
    ("Change Management Risk", "Develop change management plan; stakeholder communication cadence from day 1."),
    ("Safety/OSHA Risk", "Site safety plan with daily toolbox talks; zero-tolerance safety policy enforced."),
]

PHASES_CONSTRUCTION = [
    "Initiation & Planning", "Design & Engineering", "Permitting & Procurement",
    "Mobilization", "Construction / Execution", "Inspections & Commissioning", "Punch List & Closeout"
]

PHASES_IT = [
    "Discovery & Requirements", "Solution Design", "Development / Configuration",
    "Testing & QA", "Training & Change Management", "Go-Live & Hypercare", "Project Closeout"
]

PROJECT_STATUSES = ["planning", "in_progress", "in_progress", "in_progress", "at_risk"]

COMM_REQUESTS = [
    # Kickoff
    "Write a professional project kickoff announcement for all stakeholders.",
    "Draft a kickoff email from the project manager to the full project team.",
    "Write a project initiation memo for the ownership group.",
    "Compose a kickoff agenda and talking points for the project sponsor meeting.",
    "Write a project charter summary suitable for distribution to all stakeholders.",
    # Status
    "Draft a weekly project status report for the project sponsor.",
    "Write a bi-weekly status update for the steering committee.",
    "Prepare a project health update for the ownership group.",
    "Write a monthly progress report for the board of directors.",
    "Draft a mid-project status summary for all stakeholders.",
    # Executive / Board
    "Write an executive summary for the board of directors.",
    "Draft a board presentation narrative for project approval.",
    "Write a project overview brief for executive leadership.",
    "Compose a concise project summary for the C-suite.",
    "Draft a go/no-go recommendation brief for the steering committee.",
    # Risk
    "Compose a risk escalation memo for senior leadership.",
    "Write a critical risk alert for the project sponsor.",
    "Draft an issues log summary with recommended actions.",
    "Write a schedule risk notification for the owner's representative.",
    "Compose a budget variance alert for the CFO.",
    # Milestone
    "Write a milestone completion announcement for the team.",
    "Draft a phase completion summary for the project record.",
    "Write a substantial completion notification for the ownership group.",
    "Compose a go-live announcement for all stakeholders.",
    # Closeout
    "Write a project closeout report for the permanent record.",
    "Draft a lessons-learned summary for the project portfolio.",
    "Write a final project performance summary for leadership.",
    "Compose a handover letter to operations at project completion.",
]

HEALTH_LANGUAGE = {
    "GREEN": {
        "adj": "on track",
        "summary": "The project is performing well against all baseline targets.",
        "action": "Continue execution per plan.",
        "tone": "positive",
    },
    "YELLOW": {
        "adj": "at risk",
        "summary": "The project has moderate variances requiring active management.",
        "action": "Immediate corrective actions are in progress.",
        "tone": "cautious",
    },
    "RED": {
        "adj": "off track",
        "summary": "The project has critical issues requiring immediate escalation.",
        "action": "Executive intervention required within 48 hours.",
        "tone": "urgent",
    },
}


# ── Project builder ────────────────────────────────────────────────────────────

def pick_project():
    tmpl_name, tmpl_desc = random.choice(PROJECTS)
    n = random.choice([20, 30, 40, 50, 80, 100, 120, 150, 200, 300, 500])
    n2 = random.choice([60, 80, 100, 120, 150, 200])
    t = random.choice([6, 8, 10, 12, 18, 24])
    name = tmpl_name.format(n=n, t=t, n2=n2)
    desc = tmpl_desc.format(n=n, t=t, n2=n2)
    return name, desc


def pick_budget(name: str) -> int:
    low = name.lower()
    if any(w in low for w in ["hospital", "airport", "bridge", "highway", "tower", "wastewater"]):
        return random.randint(15, 500) * 1_000_000
    if any(w in low for w in ["data center", "erp", "cyber", "smart building"]):
        return random.randint(2, 60) * 1_000_000
    if any(w in low for w in ["hotel", "guest room", "lobby", "restaurant", "spa", "pool", "conference"]):
        return random.randint(300, 12_000) * 1_000
    return random.randint(1, 25) * 1_000_000


def budget_str(b: int) -> str:
    if b >= 1_000_000:
        if b % 1_000_000 == 0:
            return f"${b // 1_000_000}M"
        return f"${b / 1_000_000:.1f}M"
    return f"${b // 1_000}K"


def build_project_context(name, desc, methodology, duration_days, budget, health, status):
    is_it = any(w in name.lower() for w in ["erp", "pms", "cyber", "technology", "system", "software", "data center"])
    phases = PHASES_IT if is_it else PHASES_CONSTRUCTION
    n_risks = random.randint(3, 5)
    risks = random.sample(RISK_TYPES, n_risks)

    pct_complete = 0
    if status == "planning":
        pct_complete = random.randint(0, 5)
    elif status == "in_progress":
        pct_complete = random.randint(15, 75)
    elif status == "at_risk":
        pct_complete = random.randint(25, 65)

    spi = 1.0
    cpi = 1.0
    if health == "GREEN":
        spi = round(random.uniform(0.95, 1.10), 2)
        cpi = round(random.uniform(0.95, 1.08), 2)
    elif health == "YELLOW":
        spi = round(random.uniform(0.80, 0.95), 2)
        cpi = round(random.uniform(0.82, 0.97), 2)
    elif health == "RED":
        spi = round(random.uniform(0.60, 0.82), 2)
        cpi = round(random.uniform(0.62, 0.84), 2)

    spent = int(budget * pct_complete / 100)

    return {
        "project_name": name,
        "project_summary": desc,
        "methodology": methodology,
        "duration_days": duration_days,
        "budget_usd": budget,
        "health": health,
        "status": status,
        "pct_complete": pct_complete,
        "spi": spi,
        "cpi": cpi,
        "budget_spent_usd": spent,
        "top_risks": [r[0] for r in risks[:3]],
        "risk_mitigations": [r[1] for r in risks[:3]],
        "phases": phases,
        "num_phases": len(phases),
    }


# ── Prose templates ────────────────────────────────────────────────────────────

def tmpl_kickoff_email(ctx, request):
    n = ctx["project_name"]
    d = ctx["project_summary"]
    method = ctx["methodology"]
    weeks = ctx["duration_days"] // 7
    b = budget_str(ctx["budget_usd"])
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    phases = ctx["phases"]
    risks = ctx["top_risks"]
    mitigations = ctx["risk_mitigations"]

    return (
        f"Subject: Project Kickoff — {n}\n\n"
        f"Team,\n\n"
        f"I am pleased to announce the official kickoff of the {n} project. "
        f"Below is a summary of our plan to ensure we are aligned from day one.\n\n"
        f"PROJECT OVERVIEW\n"
        f"{d}\n\n"
        f"Methodology: {method}\n"
        f"Total Timeline: {weeks} weeks ({ctx['duration_days']} calendar days)\n"
        f"Approved Budget: {b}\n"
        f"Overall Health: {h} — {hl['adj'].title()}\n\n"
        f"KEY PHASES\n" +
        "".join(f"  {i+1}. {p}\n" for i, p in enumerate(phases[:5])) +
        f"\nTOP RISKS & MITIGATIONS\n" +
        "".join(f"  • {r}: {m}\n" for r, m in zip(risks, mitigations)) +
        f"\nNEXT STEPS\n"
        f"Please review the attached project charter and confirm your availability "
        f"for the kickoff meeting. All team members are expected to attend.\n\n"
        f"I look forward to working with each of you on this initiative.\n\n"
        f"Best regards,\nProject Manager"
    )


def tmpl_weekly_status(ctx, request):
    n = ctx["project_name"]
    method = ctx["methodology"]
    weeks = ctx["duration_days"] // 7
    b = budget_str(ctx["budget_usd"])
    bs = budget_str(ctx["budget_spent_usd"])
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    pct = ctx["pct_complete"]
    spi = ctx["spi"]
    cpi = ctx["cpi"]
    risks = ctx["top_risks"]
    mitigations = ctx["risk_mitigations"]
    phases = ctx["phases"]

    spi_label = "Ahead" if spi > 1.0 else ("On Track" if spi >= 0.95 else ("At Risk" if spi >= 0.80 else "Behind"))
    cpi_label = "Under Budget" if cpi > 1.0 else ("On Budget" if cpi >= 0.95 else ("Over Budget" if cpi < 0.90 else "Slightly Over"))

    return (
        f"PROJECT STATUS REPORT — {n}\n"
        f"{'=' * 60}\n"
        f"Reporting Period: This Week | Overall Status: {h} — {hl['adj'].upper()}\n\n"
        f"EXECUTIVE SUMMARY\n"
        f"{hl['summary']} The project is {pct}% complete against the {weeks}-week baseline schedule.\n\n"
        f"PERFORMANCE METRICS\n"
        f"  Schedule Performance Index (SPI): {spi:.2f} — {spi_label}\n"
        f"  Cost Performance Index (CPI):     {cpi:.2f} — {cpi_label}\n"
        f"  Budget Spent to Date:             {bs} of {b} approved\n"
        f"  Methodology: {method}\n\n"
        f"WORKSTREAM STATUS\n" +
        "".join(f"  [{i+1}] {p} — {'Complete' if i < max(1, int(len(phases)*pct/100)) else 'In Progress' if i == max(1, int(len(phases)*pct/100)) else 'Not Started'}\n" for i, p in enumerate(phases)) +
        f"\nRISK REGISTER\n" +
        "".join(f"  • {r}: {m}\n" for r, m in zip(risks, mitigations)) +
        f"\nACTION ITEMS\n"
        f"  1. {hl['action']}\n"
        f"  2. Review risk register with steering committee.\n"
        f"  3. Confirm next phase resource assignments.\n\n"
        f"Next status report: End of next week."
    )


def tmpl_executive_summary(ctx, request):
    n = ctx["project_name"]
    d = ctx["project_summary"]
    method = ctx["methodology"]
    weeks = ctx["duration_days"] // 7
    b = budget_str(ctx["budget_usd"])
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    pct = ctx["pct_complete"]
    risks = ctx["top_risks"]
    phases = ctx["phases"]

    return (
        f"EXECUTIVE SUMMARY: {n}\n\n"
        f"This initiative involves {d.rstrip('.')}. "
        f"The project will be delivered using a {method} approach over {weeks} weeks "
        f"with a total approved investment of {b}.\n\n"
        f"CURRENT STATUS: {h} — {hl['adj'].upper()}\n"
        f"{hl['summary']} The project is currently {pct}% complete.\n\n"
        f"KEY WORKSTREAMS\n" +
        "".join(f"  {i+1}. {p}\n" for i, p in enumerate(phases[:4])) +
        f"\nPRIMARY RISKS\n" +
        "".join(f"  • {r}\n" for r in risks) +
        f"\nRECOMMENDATION\n"
        f"Leadership is requested to approve continuation of the project per the baseline plan. "
        f"All critical risks have documented mitigation strategies and owners assigned. "
        f"The project team will provide bi-weekly status updates to the steering committee."
    )


def tmpl_risk_escalation(ctx, request):
    n = ctx["project_name"]
    b = budget_str(ctx["budget_usd"])
    weeks = ctx["duration_days"] // 7
    h = ctx["health"]
    risks = ctx["top_risks"]
    mitigations = ctx["risk_mitigations"]
    spi = ctx["spi"]
    cpi = ctx["cpi"]
    pct = ctx["pct_complete"]

    severity_map = {"GREEN": "MODERATE", "YELLOW": "HIGH", "RED": "CRITICAL"}
    sev = severity_map.get(h, "HIGH")

    return (
        f"RISK ESCALATION MEMO\n\n"
        f"TO: Senior Leadership / Steering Committee\n"
        f"RE: {n} — {sev} Risk Alert\n"
        f"Project Health: {h}\n\n"
        f"SITUATION\n"
        f"This memo escalates {sev.lower()} risks requiring immediate leadership attention on the {n} project. "
        f"The project is currently {pct}% complete against the approved {weeks}-week, {b} baseline.\n\n"
        f"PERFORMANCE INDICATORS\n"
        f"  • Schedule Performance Index (SPI): {spi:.2f} {'⚠ Below threshold' if spi < 0.90 else '✓ Acceptable'}\n"
        f"  • Cost Performance Index (CPI):     {cpi:.2f} {'⚠ Below threshold' if cpi < 0.90 else '✓ Acceptable'}\n\n"
        f"CRITICAL RISKS\n" +
        "".join(
            f"  {i+1}. {r} (Severity: {random.choice(SEVERITY)})\n"
            f"     Mitigation: {m}\n"
            for i, (r, m) in enumerate(zip(risks, mitigations))
        ) +
        f"\nIMPACT ASSESSMENT\n"
        f"Without corrective action, the project risks missing its {weeks}-week deadline "
        f"and exceeding the approved {b} budget.\n\n"
        f"RECOMMENDED ACTIONS\n"
        f"  1. Convene emergency steering committee meeting within 48 hours.\n"
        f"  2. Authorize project manager to implement recovery plan.\n"
        f"  3. Approve contingency budget release if warranted.\n"
        f"  4. Review and formally accept updated risk register.\n\n"
        f"Awaiting your decision and direction."
    )


def tmpl_board_update(ctx, request):
    n = ctx["project_name"]
    d = ctx["project_summary"]
    b = budget_str(ctx["budget_usd"])
    bs = budget_str(ctx["budget_spent_usd"])
    weeks = ctx["duration_days"] // 7
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    pct = ctx["pct_complete"]
    spi = ctx["spi"]
    cpi = ctx["cpi"]
    phases = ctx["phases"]
    risks = ctx["top_risks"]

    return (
        f"BOARD UPDATE: {n}\n"
        f"{'─' * 50}\n\n"
        f"PROJECT AT A GLANCE\n"
        f"  Status:     {h} — {hl['adj'].title()}\n"
        f"  Complete:   {pct}% of {weeks}-week schedule\n"
        f"  Budget:     {bs} expended of {b} approved\n"
        f"  SPI / CPI:  {spi:.2f} / {cpi:.2f}\n\n"
        f"SUMMARY\n"
        f"{d.rstrip('.')}. {hl['summary']}\n\n"
        f"PHASE STATUS\n" +
        "".join(
            f"  {'✓' if i < max(1, int(len(phases)*pct/100)) else '→' if i == max(1, int(len(phases)*pct/100)) else '○'} {p}\n"
            for i, p in enumerate(phases)
        ) +
        f"\nKEY RISKS\n" +
        "".join(f"  • {r}\n" for r in risks) +
        f"\nNEXT BOARD UPDATE\nProject team will report at the next regularly scheduled board meeting. "
        f"Any material changes will be escalated immediately per the governance framework."
    )


def tmpl_milestone_announcement(ctx, request):
    n = ctx["project_name"]
    b = budget_str(ctx["budget_usd"])
    weeks = ctx["duration_days"] // 7
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    pct = ctx["pct_complete"]
    phases = ctx["phases"]
    completed_phase = phases[min(max(1, int(len(phases)*pct/100) - 1), len(phases)-1)]
    next_phase = phases[min(int(len(phases)*pct/100), len(phases)-1)]

    return (
        f"Subject: Milestone Achieved — {n}\n\n"
        f"Team,\n\n"
        f"I am pleased to announce the successful completion of the {completed_phase} phase "
        f"on the {n} project. This milestone keeps us {hl['adj']} against the {weeks}-week, {b} baseline.\n\n"
        f"MILESTONE SUMMARY\n"
        f"  Completed Phase: {completed_phase}\n"
        f"  Overall Progress: {pct}% complete\n"
        f"  Project Health: {h} — {hl['adj'].title()}\n\n"
        f"WHAT THIS MEANS\n"
        f"Completion of this phase confirms that all prerequisites for the next phase are in place. "
        f"The team has demonstrated strong execution discipline and the project remains within budget.\n\n"
        f"NEXT PHASE\n"
        f"We are now entering the {next_phase} phase. "
        f"Detailed work plans will be distributed to all team members by end of week.\n\n"
        f"Thank you to the entire project team for your dedication and hard work.\n\n"
        f"Project Manager"
    )


def tmpl_closeout_report(ctx, request):
    n = ctx["project_name"]
    d = ctx["project_summary"]
    b = budget_str(ctx["budget_usd"])
    bs = budget_str(ctx["budget_spent_usd"])
    weeks = ctx["duration_days"] // 7
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    spi = ctx["spi"]
    cpi = ctx["cpi"]
    phases = ctx["phases"]
    risks = ctx["top_risks"]

    return (
        f"PROJECT CLOSEOUT REPORT\n"
        f"{'=' * 60}\n"
        f"Project: {n}\n"
        f"Final Status: {h} — {hl['adj'].title()}\n\n"
        f"PROJECT OVERVIEW\n"
        f"{d}\n\n"
        f"FINAL PERFORMANCE SUMMARY\n"
        f"  Total Duration:    {weeks} weeks\n"
        f"  Approved Budget:   {b}\n"
        f"  Final Cost:        {bs}\n"
        f"  Final SPI:         {spi:.2f}\n"
        f"  Final CPI:         {cpi:.2f}\n\n"
        f"PHASES COMPLETED\n" +
        "".join(f"  ✓ {p}\n" for p in phases) +
        f"\nKEY RISKS MANAGED\n" +
        "".join(f"  • {r}\n" for r in risks) +
        f"\nLESSONS LEARNED\n"
        f"  1. Early stakeholder alignment was critical to avoiding scope changes mid-project.\n"
        f"  2. Long-lead procurement initiated in phase 1 prevented supply chain delays.\n"
        f"  3. Weekly earned value reporting enabled early identification of variances.\n"
        f"  4. Clear escalation matrix ensured rapid issue resolution throughout execution.\n\n"
        f"HANDOVER\n"
        f"All project documentation, as-built drawings, warranties, and O&M manuals have been "
        f"transferred to the operations team. The project is formally closed effective today."
    )


def tmpl_budget_variance(ctx, request):
    n = ctx["project_name"]
    b = budget_str(ctx["budget_usd"])
    bs = budget_str(ctx["budget_spent_usd"])
    pct = ctx["pct_complete"]
    cpi = ctx["cpi"]
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    risks = ctx["top_risks"]
    mitigations = ctx["risk_mitigations"]

    variance_pct = round((1.0 - cpi) * 100, 1)
    direction = "over" if cpi < 1.0 else "under"
    direction_word = "overrun" if cpi < 1.0 else "savings"

    return (
        f"BUDGET VARIANCE REPORT — {n}\n\n"
        f"TO: Chief Financial Officer\n"
        f"RE: Cost Performance Update — {h} Status\n\n"
        f"SUMMARY\n"
        f"At {pct}% project completion, the {n} project is currently {abs(variance_pct):.1f}% "
        f"{direction} budget (CPI: {cpi:.2f}). "
        f"Total {direction_word} to date: {bs} expended against {b} approved budget.\n\n"
        f"ROOT CAUSE ANALYSIS\n"
        f"The primary drivers of the budget variance are:\n" +
        "".join(f"  {i+1}. {r}: {m}\n" for i, (r, m) in enumerate(zip(risks[:2], mitigations[:2]))) +
        f"\nCORRECTIVE ACTIONS\n"
        f"  1. Change control board has been convened to freeze discretionary scope.\n"
        f"  2. Weekly cost-to-complete reviews have been implemented.\n"
        f"  3. Contingency drawdown request has been submitted per governance procedures.\n\n"
        f"FORECAST\n"
        f"Based on current CPI trend, the project is forecast to complete "
        f"{'within' if cpi >= 0.95 else 'over'} the approved budget. "
        f"Updated forecast at completion will be provided within 5 business days.\n\n"
        f"Please advise on any additional approvals required."
    )


def tmpl_go_no_go(ctx, request):
    n = ctx["project_name"]
    d = ctx["project_summary"]
    b = budget_str(ctx["budget_usd"])
    weeks = ctx["duration_days"] // 7
    method = ctx["methodology"]
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    risks = ctx["top_risks"]
    mitigations = ctx["risk_mitigations"]
    phases = ctx["phases"]

    rec = "GO" if h in ("GREEN", "YELLOW") else "CONDITIONAL GO"
    cond = "" if h == "GREEN" else (
        "\n\nCONDITIONS FOR APPROVAL\n"
        "  1. Steering committee formally accepts the risk register.\n"
        "  2. Contingency reserve of 10% is confirmed and accessible.\n"
        "  3. Executive sponsor commits to weekly steering reviews through execution.\n"
    )

    return (
        f"GO / NO-GO DECISION BRIEF: {n}\n\n"
        f"RECOMMENDATION: {rec}\n\n"
        f"PROJECT OVERVIEW\n"
        f"{d.rstrip('.')}. Methodology: {method}. Timeline: {weeks} weeks. Budget: {b}.\n\n"
        f"READINESS ASSESSMENT\n"
        f"  Scope defined and signed:     {'Yes' if h != 'RED' else 'Partially'}\n"
        f"  Budget approved:              {'Yes' if h in ('GREEN', 'YELLOW') else 'Pending'}\n"
        f"  Team assembled:               {'Yes' if h == 'GREEN' else 'In Progress'}\n"
        f"  Risk register complete:       Yes\n"
        f"  Stakeholder alignment:        {'Confirmed' if h == 'GREEN' else 'In Progress'}\n\n"
        f"PHASE 1 WORKSTREAMS\n" +
        "".join(f"  {i+1}. {p}\n" for i, p in enumerate(phases[:3])) +
        f"\nKEY RISKS\n" +
        "".join(f"  • {r}: {m}\n" for r, m in zip(risks, mitigations)) +
        cond +
        f"\nAWAITING STEERING COMMITTEE DECISION."
    )


def tmpl_lessons_learned(ctx, request):
    n = ctx["project_name"]
    weeks = ctx["duration_days"] // 7
    b = budget_str(ctx["budget_usd"])
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    spi = ctx["spi"]
    cpi = ctx["cpi"]
    risks = ctx["top_risks"]

    positives = [
        "Early stakeholder engagement prevented late-stage scope changes.",
        "Long-lead procurement in Phase 1 avoided supply chain delays.",
        "Weekly earned value tracking enabled early identification of cost variances.",
        "Daily toolbox talks maintained a zero-incident safety record through execution.",
        "Clear change control process reduced unapproved scope additions by 80%.",
        "Dedicated QA inspector at each phase gate eliminated rework costs at handover.",
    ]

    improvements = [
        f"{risks[0]} was underestimated at project outset — earlier mitigation planning recommended.",
        "Stakeholder communication cadence should be established in week 1, not week 3.",
        "Contingency budget should be baselined at 12% for projects of this complexity.",
        "Resource backup plans should be activated at first sign of availability risk.",
    ]

    return (
        f"LESSONS LEARNED SUMMARY — {n}\n\n"
        f"Project Duration: {weeks} weeks | Budget: {b}\n"
        f"Final Health: {h} | SPI: {spi:.2f} | CPI: {cpi:.2f}\n\n"
        f"WHAT WORKED WELL\n" +
        "".join(f"  + {p}\n" for p in random.sample(positives, min(3, len(positives)))) +
        f"\nAREAS FOR IMPROVEMENT\n" +
        "".join(f"  Δ {imp}\n" for imp in random.sample(improvements, min(2, len(improvements)))) +
        f"\nKEY TAKEAWAYS FOR FUTURE PROJECTS\n"
        f"  1. Invest in thorough scope definition before any commitment to schedule or budget.\n"
        f"  2. Establish earned value baselines at project kickoff — not after execution begins.\n"
        f"  3. Risk reviews must be standing agenda items at every steering committee meeting.\n"
        f"  4. Formal lessons learned should be captured at each phase gate, not only at closeout.\n\n"
        f"This document is submitted for inclusion in the project portfolio knowledge base."
    )


def tmpl_handover_letter(ctx, request):
    n = ctx["project_name"]
    d = ctx["project_summary"]
    b = budget_str(ctx["budget_usd"])
    bs = budget_str(ctx["budget_spent_usd"])
    weeks = ctx["duration_days"] // 7
    spi = ctx["spi"]
    cpi = ctx["cpi"]
    phases = ctx["phases"]

    return (
        f"PROJECT HANDOVER LETTER — {n}\n\n"
        f"TO: Director of Operations\n"
        f"FROM: Project Manager\n"
        f"RE: Formal Handover of Completed Project\n\n"
        f"Dear Director,\n\n"
        f"I am writing to formally hand over the completed {n} project. "
        f"{d.rstrip('.')}. The project was delivered over {weeks} weeks with a final "
        f"cost of {bs} against an approved budget of {b}.\n\n"
        f"PERFORMANCE SUMMARY\n"
        f"  Schedule Performance Index: {spi:.2f}\n"
        f"  Cost Performance Index:     {cpi:.2f}\n\n"
        f"HANDOVER DELIVERABLES\n"
        f"  ✓ As-built drawings and specifications\n"
        f"  ✓ Equipment warranties and O&M manuals\n"
        f"  ✓ Certificate of substantial completion\n"
        f"  ✓ Final punch list — all items resolved\n"
        f"  ✓ Training records for operations staff\n"
        f"  ✓ Project close-out report and final budget reconciliation\n\n"
        f"PHASES DELIVERED\n" +
        "".join(f"  ✓ {p}\n" for p in phases) +
        f"\nThe project is now formally closed and transitioned to your team. "
        f"Please do not hesitate to contact me with any post-handover questions.\n\n"
        f"Sincerely,\nProject Manager"
    )


def tmpl_scope_change(ctx, request):
    n = ctx["project_name"]
    b = budget_str(ctx["budget_usd"])
    bs = budget_str(ctx["budget_spent_usd"])
    pct = ctx["pct_complete"]
    h = ctx["health"]
    hl = HEALTH_LANGUAGE[h]
    phases = ctx["phases"]
    risks = ctx["top_risks"]

    add_cost = int(ctx["budget_usd"] * random.uniform(0.05, 0.18))
    add_weeks = random.randint(1, 4)

    return (
        f"SCOPE CHANGE REQUEST MEMO — {n}\n\n"
        f"Change Control Board Reference: CCB-{random.randint(100, 999)}\n"
        f"Project Health at Time of Request: {h}\n\n"
        f"CHANGE DESCRIPTION\n"
        f"The project team requests approval for a scope addition identified during the "
        f"{phases[min(int(len(phases)*pct/100), len(phases)-1)]} phase. "
        f"The addition involves work not included in the original approved scope.\n\n"
        f"COST & SCHEDULE IMPACT\n"
        f"  Current approved budget:    {b}\n"
        f"  Expended to date:           {bs} ({pct}% complete)\n"
        f"  Requested budget increase:  {budget_str(add_cost)}\n"
        f"  Schedule extension:         {add_weeks} week(s)\n\n"
        f"JUSTIFICATION\n"
        f"This scope addition is required to ensure long-term operational integrity and "
        f"avoid substantially higher remediation costs post-completion. "
        f"The project team has evaluated all alternatives and recommends approval.\n\n"
        f"RISK IF NOT APPROVED\n" +
        "".join(f"  • {r}\n" for r in risks[:2]) +
        f"\nREQUESTED ACTION\n"
        f"Approval from the Change Control Board and project sponsor is required to proceed. "
        f"Decision needed within 5 business days to avoid schedule impact."
    )


def tmpl_kickoff_agenda(ctx, request):
    n = ctx["project_name"]
    d = ctx["project_summary"]
    b = budget_str(ctx["budget_usd"])
    weeks = ctx["duration_days"] // 7
    method = ctx["methodology"]
    phases = ctx["phases"]
    risks = ctx["top_risks"]

    return (
        f"KICKOFF MEETING AGENDA — {n}\n\n"
        f"Duration: 90 minutes | Format: In-Person / Video Conference\n"
        f"Attendees: Project Sponsor, PM Team, Key Stakeholders, Steering Committee\n\n"
        f"AGENDA\n\n"
        f"1. Welcome & Introductions (10 min)\n"
        f"   • Sponsor opening remarks\n"
        f"   • Project manager introduction\n"
        f"   • Team introductions\n\n"
        f"2. Project Overview (15 min)\n"
        f"   • Scope: {d.rstrip('.')}\n"
        f"   • Budget: {b} | Timeline: {weeks} weeks | Methodology: {method}\n\n"
        f"3. Project Plan Review (20 min)\n"
        f"   Key phases:\n" +
        "".join(f"   {i+1}. {p}\n" for i, p in enumerate(phases[:5])) +
        f"\n4. Risk Register Review (15 min)\n"
        f"   Top risks to address:\n" +
        "".join(f"   • {r}\n" for r in risks) +
        f"\n5. Roles & Responsibilities (10 min)\n"
        f"   • RACI matrix walkthrough\n"
        f"   • Decision-making authority and escalation path\n\n"
        f"6. Communication Plan (10 min)\n"
        f"   • Status reporting cadence\n"
        f"   • Steering committee meeting schedule\n"
        f"   • Document management and collaboration tools\n\n"
        f"7. Q&A and Next Steps (10 min)\n"
        f"   • Open questions\n"
        f"   • Action items and owners\n"
        f"   • Next milestone and check-in date\n\n"
        f"Meeting materials will be distributed 24 hours in advance."
    )


PROSE_TEMPLATES = [
    tmpl_kickoff_email,
    tmpl_weekly_status,
    tmpl_executive_summary,
    tmpl_risk_escalation,
    tmpl_board_update,
    tmpl_milestone_announcement,
    tmpl_closeout_report,
    tmpl_budget_variance,
    tmpl_go_no_go,
    tmpl_lessons_learned,
    tmpl_handover_letter,
    tmpl_scope_change,
    tmpl_kickoff_agenda,
]


# ── Record builder ─────────────────────────────────────────────────────────────

def build_record(ctx, request):
    tmpl = random.choice(PROSE_TEMPLATES)
    prose = tmpl(ctx, request)
    context_for_model = {k: v for k, v in ctx.items() if k not in ("risk_mitigations", "phases")}
    context_for_model["top_risks"] = ctx["top_risks"]
    context_for_model["critical_path_phases"] = ctx["phases"][:4]

    return {
        "source": "synthetic_communicator_rich",
        "text": (
            f"<|pm_request|>\n{request}\n"
            f"<|project_context|>\n{json.dumps(context_for_model, indent=2)}\n"
            f"<|response|>\n{prose}\n<|end|>"
        ),
        "format": "structured_prose",
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def generate(target=15000):
    records = []
    seen = set()
    attempts = 0
    max_attempts = target * 4

    while len(records) < target and attempts < max_attempts:
        attempts += 1

        name, desc = pick_project()
        methodology = random.choice(METHODOLOGIES)
        duration_days = random.choice([28, 35, 42, 56, 63, 70, 84, 90, 112, 120, 140, 168, 180])
        budget = pick_budget(name)
        health = random.choice(HEALTH_STATES)
        status = random.choice(PROJECT_STATUSES)
        request = random.choice(COMM_REQUESTS)

        key = hashlib.md5(f"{name}{duration_days}{budget}{request[:20]}".encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)

        ctx = build_project_context(name, desc, methodology, duration_days, budget, health, status)
        record = build_record(ctx, request)
        records.append(record)

        if len(records) % 1000 == 0:
            print(f"  Generated {len(records):,} records...")

    random.shuffle(records)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(f"Generated {len(records):,} records -> {OUT_PATH}")
    return len(records)


if __name__ == "__main__":
    print("Generating rich communicator synthetic data...")
    n = generate()
    print(f"Done. {n:,} records.")
