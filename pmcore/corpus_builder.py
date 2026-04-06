"""
PMCore Corpus Builder
======================
Builds three specialized training corpora — one per PMCore component.

PMPlanner corpus:    Natural language request → JSON task graph
PMReasoner corpus:   Task graph + context → JSON risk/path analysis
PMCommunicator corpus: Task graph + audience → Human-readable text

Sources:
  1. Synthetic generation (LLM-generated PM scenarios) — MAIN source
  2. HuggingFace PM datasets (filtered)
  3. Public PM templates / PMBOK-aligned examples

Output: Three JSONL files ready for tokenization + training
  ./corpus/planner_corpus.jsonl
  ./corpus/reasoner_corpus.jsonl
  ./corpus/communicator_corpus.jsonl
"""

import json
import random
import os
from pathlib import Path
from typing import Iterator

random.seed(42)
OUTPUT_DIR = Path("./corpus")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── PMPlanner Corpus ──────────────────────────────────────────────────────────
# Format: {"input": "<PM request>", "output": <JSON task graph>}

INDUSTRIES = [
    "hotel renovation", "software development", "hospital construction",
    "marketing campaign", "ERP implementation", "product launch",
    "data center migration", "office relocation", "event management",
    "supply chain overhaul", "sustainability initiative", "M&A integration",
]

CONSTRAINTS = [
    "budget of $2M", "12-week deadline", "3-person team", "remote team across 4 time zones",
    "regulatory approval required", "vendor dependency on critical path",
    "no downtime allowed", "hard launch date tied to conference", "limited to internal resources",
]

RISK_TYPES = [
    "vendor delay", "scope creep", "key person dependency", "budget overrun",
    "regulatory change", "technology failure", "resource unavailability",
    "stakeholder misalignment", "integration failure", "market shift",
]

STAKEHOLDERS = [
    "CEO", "CFO", "CTO", "PMO Director", "Department Head",
    "Board of Directors", "External Client", "Regulatory Body",
    "Engineering Team", "Operations Manager",
]

COMMS_TYPES = [
    "weekly status report", "executive summary", "risk escalation email",
    "kickoff meeting agenda", "project closure report", "stakeholder update",
    "sprint review summary", "budget variance explanation", "milestone completion notice",
    "change request justification",
]


def make_task_graph(project_name: str, num_tasks: int = None) -> dict:
    """Generate a realistic JSON task graph."""
    if num_tasks is None:
        num_tasks = random.randint(5, 12)

    phases = ["Initiation", "Planning", "Execution", "Monitoring", "Closure"]
    tasks = []
    for i in range(1, num_tasks + 1):
        phase = phases[min(i // 3, 4)]
        duration = random.randint(3, 21)
        deps = []
        if i > 2:
            deps = [f"T{random.randint(1, i-1):02d}"]
        if i > 4 and random.random() > 0.5:
            deps.append(f"T{random.randint(1, i-2):02d}")
        deps = list(set(deps))

        tasks.append({
            "id": f"T{i:02d}",
            "name": f"{phase} - Task {i}",
            "phase": phase,
            "duration_days": duration,
            "dependencies": deps,
            "resources": [f"Resource_{chr(65 + (i % 5))}"],
            "status": "not_started",
            "priority": random.choice(["high", "medium", "low"]),
        })

    total_days = sum(t["duration_days"] for t in tasks) // 2  # rough critical path

    return {
        "project": {
            "name": project_name,
            "start_date": "TBD",
            "estimated_duration_days": total_days,
            "methodology": random.choice(["Agile", "Waterfall", "Hybrid"]),
        },
        "tasks": tasks,
        "milestones": [
            {"id": "M1", "name": "Project Kickoff", "depends_on": ["T01"]},
            {"id": "M2", "name": "Phase Gate Review", "depends_on": [f"T{num_tasks//2:02d}"]},
            {"id": "M3", "name": "Project Completion", "depends_on": [f"T{num_tasks:02d}"]},
        ],
        "summary": f"Project has {num_tasks} tasks across {len(phases)} phases.",
    }


def make_risk_analysis(task_graph: dict, risk_count: int = None) -> dict:
    """Generate a risk register + critical path analysis."""
    if risk_count is None:
        risk_count = random.randint(3, 7)

    tasks = task_graph.get("tasks", [])
    risks = []
    for i in range(risk_count):
        risk_type = random.choice(RISK_TYPES)
        affected = random.choice(tasks)["id"] if tasks else "T01"
        prob = round(random.uniform(0.1, 0.9), 2)
        impact = random.choice(["low", "medium", "high", "critical"])
        risks.append({
            "id": f"R{i+1:02d}",
            "type": risk_type,
            "description": f"{risk_type.title()} affecting {affected}",
            "probability": prob,
            "impact": impact,
            "risk_score": round(prob * {"low": 1, "medium": 2, "high": 3, "critical": 4}[impact], 2),
            "mitigation": f"Develop contingency plan for {risk_type}",
            "owner": random.choice(["PM", "Tech Lead", "Sponsor", "Vendor Manager"]),
        })

    # Critical path = longest dependency chain
    task_ids = [t["id"] for t in tasks]
    critical_path = task_ids[:min(len(task_ids), random.randint(3, 6))]

    return {
        "critical_path": {
            "tasks": critical_path,
            "total_duration_days": sum(
                t["duration_days"] for t in tasks if t["id"] in critical_path
            ),
            "float_days": 0,
        },
        "risks": sorted(risks, key=lambda r: r["risk_score"], reverse=True),
        "overall_health": random.choice(["green", "yellow", "red"]),
        "schedule_confidence": f"{random.randint(60, 95)}%",
        "budget_confidence": f"{random.randint(60, 95)}%",
        "top_risk": risks[0]["type"] if risks else "none",
    }


def planner_examples() -> Iterator[dict]:
    """Yield (input, output) pairs for PMPlanner training."""
    templates = [
        "Create a project plan for a {industry} with {constraint}.",
        "I need to manage a {industry} project. We have {constraint}. Break it down.",
        "Plan a {industry} initiative. Constraints: {constraint}. Give me a structured task breakdown.",
        "Our team needs to deliver a {industry}. {constraint}. What's the project structure?",
        "Generate a work breakdown structure for a {industry}. Key constraint: {constraint}.",
        "We're kicking off a {industry} project next month. {constraint}. Build the project plan.",
        "Help me structure a {industry}. We must deal with {constraint}.",
    ]
    for industry in INDUSTRIES:
        for constraint in CONSTRAINTS:
            template = random.choice(templates)
            prompt = template.format(industry=industry, constraint=constraint)
            project_name = f"{industry.title()} Project"
            graph = make_task_graph(project_name)
            yield {"input": prompt, "output": graph}


def reasoner_examples() -> Iterator[dict]:
    """Yield (task_graph, analysis) pairs for PMReasoner training."""
    templates = [
        "Analyze the risks and critical path for this project.",
        "What are the biggest risks here? Identify the critical path.",
        "Review this project plan and flag all risks. What's on the critical path?",
        "Perform a risk assessment and critical path analysis.",
        "Identify schedule risks, budget risks, and the critical path for this project.",
        "What could go wrong? Critical path analysis please.",
    ]
    for industry in INDUSTRIES:
        for constraint in CONSTRAINTS:
            graph = make_task_graph(f"{industry.title()} Project")
            prompt = random.choice(templates)
            analysis = make_risk_analysis(graph)
            yield {
                "input": prompt,
                "context": graph,
                "output": analysis,
            }


def communicator_examples() -> Iterator[dict]:
    """Yield (task_graph + audience, stakeholder communication) pairs."""
    templates = [
        "Write a {comm_type} for {stakeholder} about this project.",
        "Generate a {comm_type} suitable for {stakeholder}.",
        "Draft a {comm_type} — audience is {stakeholder}. Keep it professional.",
        "The {stakeholder} needs a {comm_type}. Write it based on this project data.",
        "Prepare a {comm_type} for {stakeholder} from this project status.",
    ]

    comm_bodies = {
        "weekly status report": (
            "## Weekly Status Report\n\n"
            "**Overall Status:** {health}\n\n"
            "**Accomplishments This Week:**\n- Completed planning phase milestones\n"
            "- Resolved vendor dependency on critical path\n\n"
            "**Planned Next Week:**\n- Begin execution phase\n- Stakeholder review meeting\n\n"
            "**Risks & Issues:**\n- Monitor {risk} — mitigation plan in place\n\n"
            "**Schedule:** {confidence} on track\n"
            "**Budget:** Within approved parameters\n"
        ),
        "executive summary": (
            "## Executive Summary\n\n"
            "The project is currently **{health}** with {confidence} schedule confidence. "
            "Key milestones are being tracked and the team is managing identified risks proactively. "
            "Primary risk is {risk}, with mitigation underway. "
            "No executive decisions required at this time.\n"
        ),
        "risk escalation email": (
            "Subject: Risk Escalation — {risk} Requires Attention\n\n"
            "Dear {stakeholder},\n\n"
            "I am writing to escalate a risk that has materialized and requires your awareness. "
            "Specifically, **{risk}** is currently assessed as high-probability with significant schedule impact. "
            "The team is implementing the mitigation plan, but your support in [specific action] "
            "would significantly reduce exposure.\n\n"
            "Please advise at your earliest convenience.\n\n"
            "Best regards,\nProject Manager\n"
        ),
        "milestone completion notice": (
            "Subject: Milestone Achieved — {milestone}\n\n"
            "Team,\n\n"
            "I'm pleased to announce that we have successfully completed **{milestone}** on schedule. "
            "This is a significant step forward for the project. "
            "The team's focus and execution made this possible.\n\n"
            "Next milestone: Project Phase Gate Review.\n\n"
            "Thank you all for your contributions.\n"
        ),
    }

    for _ in range(len(INDUSTRIES) * len(CONSTRAINTS)):
        industry = random.choice(INDUSTRIES)
        constraint = random.choice(CONSTRAINTS)
        stakeholder = random.choice(STAKEHOLDERS)
        comm_type = random.choice(COMMS_TYPES)
        graph = make_task_graph(f"{industry.title()} Project")
        analysis = make_risk_analysis(graph)

        template = random.choice(templates)
        prompt = template.format(comm_type=comm_type, stakeholder=stakeholder)

        # Pick a body template or generate generic
        health = analysis["overall_health"].upper()
        confidence = analysis["schedule_confidence"]
        risk = analysis["top_risk"]
        milestone = "Planning Phase Complete"

        body_template = comm_bodies.get(
            comm_type,
            f"## {comm_type.title()}\n\nProject status: {health}. "
            f"Schedule confidence: {confidence}. "
            f"Primary risk: {risk}. All deliverables tracking to plan.\n"
        )
        body = body_template.format(
            health=health, confidence=confidence, risk=risk,
            stakeholder=stakeholder, milestone=milestone
        )

        yield {
            "input": prompt,
            "context": {"project": graph, "analysis": analysis},
            "output": body,
        }


# ── Corpus Assembly ───────────────────────────────────────────────────────────

def write_corpus(name: str, gen_fn, formatter_fn):
    """Write a corpus JSONL file from a generator."""
    path = OUTPUT_DIR / f"{name}_corpus.jsonl"
    count = 0
    with open(path, "w") as f:
        for example in gen_fn():
            record = formatter_fn(example)
            f.write(json.dumps(record) + "\n")
            count += 1
    print(f"  {name}: {count:,} examples → {path}")
    return count


def format_planner(ex: dict) -> dict:
    """Format for causal LM training: <input> → <JSON output>"""
    return {
        "text": (
            f"<|pm_request|>\n{ex['input']}\n"
            f"<|task_graph|>\n{json.dumps(ex['output'], indent=2)}\n<|end|>"
        )
    }


def format_reasoner(ex: dict) -> dict:
    """Format: <task graph> + <request> → <JSON analysis>"""
    return {
        "text": (
            f"<|task_graph|>\n{json.dumps(ex['context'], indent=2)}\n"
            f"<|pm_request|>\n{ex['input']}\n"
            f"<|analysis|>\n{json.dumps(ex['output'], indent=2)}\n<|end|>"
        )
    }


def format_communicator(ex: dict) -> dict:
    """Format: <task graph + analysis> + <request> → <human text>"""
    return {
        "text": (
            f"<|project_context|>\n{json.dumps(ex['context'], indent=2)}\n"
            f"<|pm_request|>\n{ex['input']}\n"
            f"<|communication|>\n{ex['output']}\n<|end|>"
        )
    }


if __name__ == "__main__":
    print("Building PMCore training corpora...\n")
    total = 0
    total += write_corpus("planner",      planner_examples,      format_planner)
    total += write_corpus("reasoner",     reasoner_examples,     format_reasoner)
    total += write_corpus("communicator", communicator_examples, format_communicator)
    print(f"\nTotal examples: {total:,}")
    print(f"Corpus files in: {OUTPUT_DIR.resolve()}")
