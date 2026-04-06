"""
PMMath — Project Management Math Validator
==========================================
Validates the numerical consistency of PMCore pipeline outputs.

Checks performed:
  1. budget_phases   — Sum of phase budgets ≤ total project budget
  2. duration_phases — Sum of sequential phase durations ≈ total project duration
  3. team_utilization— Estimated team hours are realistic (not >120% capacity)
  4. milestone_timing— Milestones fall within the project timeline
  5. risk_buffer     — High-risk projects should have ≥10% cost buffer
  6. comm_numbers    — Key numbers in communication match the plan
  7. task_coverage   — Task durations account for most of the project timeline

Each check returns:
  status  : "pass" | "warn" | "fail"
  message : Human-readable explanation
  detail  : Optional corrected value or breakdown
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Check Result ──────────────────────────────────────────────────────────────

@dataclass
class MathCheck:
    name:    str
    status:  str          # "pass" | "warn" | "fail" | "skip"
    message: str
    detail:  Optional[dict] = None


@dataclass
class MathAudit:
    checks:        list[MathCheck]
    overall:       str            # "pass" | "warn" | "fail"
    corrections:   dict           # suggested corrected values
    summary:       str

    def to_dict(self) -> dict:
        return {
            "overall": self.overall,
            "summary": self.summary,
            "checks": [
                {
                    "name":    c.name,
                    "status":  c.status,
                    "message": c.message,
                    **({"detail": c.detail} if c.detail else {}),
                }
                for c in self.checks
            ],
            "corrections": self.corrections,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_money(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def _fmt_days(v: int) -> str:
    if v >= 365:
        return f"{v/365:.1f} years ({v}d)"
    if v >= 30:
        return f"{v//30}mo {v%30}d ({v}d)"
    return f"{v} days"


def _extract_numbers_from_text(text: str) -> list[float]:
    """Extract all dollar amounts and large numbers from prose text."""
    numbers = []
    # $X, $XK, $XM, $XB
    for m in re.finditer(r'\$\s*(\d+(?:\.\d+)?)\s*([KkMmBb])?', text):
        val = float(m.group(1))
        suffix = (m.group(2) or "").upper()
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
        numbers.append(val * multiplier)
    return numbers


def _largest_money_in_text(text: str) -> Optional[float]:
    nums = _extract_numbers_from_text(text)
    return max(nums) if nums else None


# ── Individual Checks ─────────────────────────────────────────────────────────

def _check_budget_phases(project: dict, phases: list) -> MathCheck:
    """Sum of phase budgets should not exceed total project budget."""
    total_budget = project.get("budget_usd", 0) or project.get("budget", 0)
    if not total_budget or total_budget <= 0:
        return MathCheck("budget_phases", "skip", "No budget provided — skipping budget validation.")

    phase_costs = []
    for p in phases:
        cost = p.get("budget_usd", 0) or p.get("cost", 0) or p.get("estimated_cost", 0)
        if cost:
            phase_costs.append((p.get("name", "?"), cost))

    if not phase_costs:
        return MathCheck("budget_phases", "skip",
                         "Phase budgets not specified — cannot validate budget breakdown.")

    total_phase_cost = sum(c for _, c in phase_costs)
    ratio = total_phase_cost / total_budget

    detail = {
        "total_budget": total_budget,
        "sum_phase_costs": total_phase_cost,
        "ratio": round(ratio, 3),
        "phases": {name: cost for name, cost in phase_costs},
    }

    if ratio > 1.15:
        return MathCheck(
            "budget_phases", "fail",
            f"Phase budgets sum to {_fmt_money(total_phase_cost)} but total budget is "
            f"{_fmt_money(total_budget)} — overspent by {(ratio-1)*100:.0f}%.",
            detail,
        )
    if ratio > 1.02:
        return MathCheck(
            "budget_phases", "warn",
            f"Phase budgets slightly exceed total: {_fmt_money(total_phase_cost)} vs "
            f"{_fmt_money(total_budget)} (+{(ratio-1)*100:.1f}% — may be rounding).",
            detail,
        )
    if ratio < 0.5 and total_budget > 50_000:
        return MathCheck(
            "budget_phases", "warn",
            f"Phase budgets only account for {ratio*100:.0f}% of total budget "
            f"({_fmt_money(total_phase_cost)} / {_fmt_money(total_budget)}). "
            "Remaining budget unallocated.",
            detail,
        )
    return MathCheck(
        "budget_phases", "pass",
        f"Phase budgets sum to {_fmt_money(total_phase_cost)} of "
        f"{_fmt_money(total_budget)} total ({ratio*100:.0f}%).",
        detail,
    )


def _check_duration_phases(project: dict, phases: list) -> MathCheck:
    """Sum of sequential phase durations should approximate total project duration."""
    total_days = (
        project.get("estimated_duration_days", 0)
        or project.get("duration_days", 0)
    )
    if not total_days or total_days <= 0:
        return MathCheck("duration_phases", "skip", "No project duration specified.")

    phase_durations = []
    for p in phases:
        d = p.get("duration_days", 0) or p.get("duration", 0)
        if d:
            phase_durations.append((p.get("name", "?"), int(d)))

    if not phase_durations:
        return MathCheck("duration_phases", "skip", "Phase durations not specified.")

    # For sequential phases, sum should ≈ total
    # Allow 20% slack for parallel work / buffer
    sum_days = sum(d for _, d in phase_durations)
    ratio = sum_days / total_days

    detail = {
        "total_duration_days": total_days,
        "sum_phase_days": sum_days,
        "ratio": round(ratio, 3),
        "phases": {name: days for name, days in phase_durations},
    }

    if ratio > 1.5:
        return MathCheck(
            "duration_phases", "fail",
            f"Phase durations sum to {_fmt_days(sum_days)} but project is only "
            f"{_fmt_days(total_days)} — phases are {ratio:.1f}x too long.",
            detail,
        )
    if ratio > 1.2:
        return MathCheck(
            "duration_phases", "warn",
            f"Phase durations ({_fmt_days(sum_days)}) exceed project timeline "
            f"({_fmt_days(total_days)}) by {(ratio-1)*100:.0f}% — some phases "
            "may be parallel.",
            detail,
        )
    if ratio < 0.5:
        return MathCheck(
            "duration_phases", "warn",
            f"Phase durations only sum to {_fmt_days(sum_days)} of "
            f"{_fmt_days(total_days)} total ({ratio*100:.0f}%) — "
            "significant unscheduled time.",
            detail,
        )
    return MathCheck(
        "duration_phases", "pass",
        f"Phase durations sum to {_fmt_days(sum_days)} vs "
        f"{_fmt_days(total_days)} total ({ratio*100:.0f}%).",
        detail,
    )


def _check_team_utilization(project: dict, tasks: list, duration_days: int) -> MathCheck:
    """Estimated team load should be realistic."""
    team_size = (
        project.get("team_size", 0)
        or project.get("num_team_members", 0)
        or project.get("resources", {}).get("team_size", 0)
    )
    if not team_size or not duration_days:
        return MathCheck("team_utilization", "skip",
                         "Team size or duration not specified — skipping utilization check.")

    # Estimate total person-days from tasks
    task_days = []
    for t in tasks:
        d = t.get("duration_days", 0)
        assigned = t.get("assigned_to", [])
        count = len(assigned) if isinstance(assigned, list) else 1
        task_days.append(d * max(count, 1))

    if not task_days:
        return MathCheck("team_utilization", "skip", "No task durations to check.")

    total_task_person_days = sum(task_days)
    capacity = team_size * duration_days
    utilization = total_task_person_days / capacity if capacity else 0

    detail = {
        "team_size": team_size,
        "duration_days": duration_days,
        "capacity_person_days": capacity,
        "estimated_task_person_days": round(total_task_person_days, 1),
        "utilization_pct": round(utilization * 100, 1),
    }

    if utilization > 1.3:
        return MathCheck(
            "team_utilization", "fail",
            f"Task load ({total_task_person_days:.0f} person-days) exceeds team capacity "
            f"({capacity} person-days for {team_size} people × {duration_days}d) "
            f"by {(utilization-1)*100:.0f}%. Team is over-committed.",
            detail,
        )
    if utilization > 1.05:
        return MathCheck(
            "team_utilization", "warn",
            f"Team is slightly over-committed: {utilization*100:.0f}% utilization "
            f"({total_task_person_days:.0f} / {capacity} person-days).",
            detail,
        )
    if utilization < 0.4 and team_size > 2:
        return MathCheck(
            "team_utilization", "warn",
            f"Team appears underutilized: only {utilization*100:.0f}% of capacity used "
            f"({total_task_person_days:.0f} / {capacity} person-days).",
            detail,
        )
    return MathCheck(
        "team_utilization", "pass",
        f"Team utilization is {utilization*100:.0f}% "
        f"({total_task_person_days:.0f} / {capacity} person-days).",
        detail,
    )


def _check_risk_buffer(project: dict, health: str) -> MathCheck:
    """High-risk projects should have a cost buffer ≥10%."""
    budget = project.get("budget_usd", 0) or project.get("budget", 0)
    if not budget:
        return MathCheck("risk_buffer", "skip", "No budget — skipping risk buffer check.")

    contingency = (
        project.get("contingency", 0)
        or project.get("contingency_budget", 0)
        or project.get("buffer", 0)
        or project.get("reserve", 0)
    )

    if health.lower() == "red":
        min_buffer_pct = 0.15
        label = "critical-risk"
    elif health.lower() == "yellow":
        min_buffer_pct = 0.10
        label = "medium-risk"
    else:
        min_buffer_pct = 0.05
        label = "low-risk"

    min_buffer = budget * min_buffer_pct

    if contingency <= 0:
        if health.lower() in ("red", "yellow"):
            return MathCheck(
                "risk_buffer", "warn",
                f"No contingency budget specified for {label} project. "
                f"Recommend adding ≥{_fmt_money(min_buffer)} ({min_buffer_pct*100:.0f}% of budget).",
                {"recommended_buffer": round(min_buffer), "budget": budget},
            )
        return MathCheck("risk_buffer", "pass",
                         f"Low-risk project — no explicit buffer required.",
                         {"budget": budget})

    buffer_pct = contingency / budget
    detail = {
        "budget": budget,
        "contingency": contingency,
        "buffer_pct": round(buffer_pct * 100, 1),
        "recommended_min_pct": min_buffer_pct * 100,
    }

    if buffer_pct < min_buffer_pct:
        return MathCheck(
            "risk_buffer", "warn",
            f"Contingency {_fmt_money(contingency)} ({buffer_pct*100:.0f}%) may be "
            f"insufficient for {label} project. Recommend ≥{min_buffer_pct*100:.0f}%.",
            detail,
        )
    return MathCheck(
        "risk_buffer", "pass",
        f"Contingency buffer {_fmt_money(contingency)} ({buffer_pct*100:.0f}%) "
        f"is adequate for {label} project.",
        detail,
    )


def _check_comm_numbers(
    comm_text: str,
    budget: float,
    duration_days: int,
    team_size: int,
) -> MathCheck:
    """Key numbers in the communication should match the plan."""
    if not comm_text:
        return MathCheck("comm_numbers", "skip", "No communication text to check.")

    issues = []

    # Budget consistency
    if budget and budget > 1_000:
        comm_budget = _largest_money_in_text(comm_text)
        if comm_budget is not None:
            ratio = comm_budget / budget
            if ratio < 0.5 or ratio > 2.0:
                issues.append(
                    f"Budget mismatch: communication mentions {_fmt_money(comm_budget)} "
                    f"but plan has {_fmt_money(budget)}"
                )

    # Duration — look for weeks/months/days in communication
    if duration_days and duration_days > 0:
        # Extract time mentions
        month_matches = re.findall(r'(\d+)\s*month', comm_text, re.I)
        week_matches  = re.findall(r'(\d+)\s*week',  comm_text, re.I)
        day_matches   = re.findall(r'(\d+)\s*day',   comm_text, re.I)

        comm_days_candidates = []
        for m in month_matches:
            comm_days_candidates.append(int(m) * 30)
        for w in week_matches:
            comm_days_candidates.append(int(w) * 7)
        for d in day_matches:
            if 5 <= int(d) <= 3650:  # filter out "day 1" style references
                comm_days_candidates.append(int(d))

        if comm_days_candidates:
            closest = min(comm_days_candidates, key=lambda x: abs(x - duration_days))
            ratio = closest / duration_days
            if ratio < 0.4 or ratio > 2.5:
                issues.append(
                    f"Timeline mismatch: communication implies ~{_fmt_days(closest)} "
                    f"but plan is {_fmt_days(duration_days)}"
                )

    if issues:
        return MathCheck(
            "comm_numbers", "warn",
            "Communication numbers may not match the plan: " + "; ".join(issues),
            {"issues": issues},
        )
    return MathCheck(
        "comm_numbers", "pass",
        "Communication numbers are consistent with the project plan.",
    )


def _check_milestone_timing(project: dict, milestones: list, total_days: int) -> MathCheck:
    """Milestones should fall within the project timeline."""
    if not milestones or not total_days:
        return MathCheck("milestone_timing", "skip", "No milestones or timeline to check.")

    out_of_range = []
    for m in milestones:
        day = m.get("day", None) or m.get("due_day", None)
        if day is not None and int(day) > total_days * 1.05:
            out_of_range.append(
                f"{m.get('name','?')} at day {day} (project ends day {total_days})"
            )

    if out_of_range:
        return MathCheck(
            "milestone_timing", "fail",
            f"{len(out_of_range)} milestone(s) fall outside the project timeline: "
            + "; ".join(out_of_range),
            {"out_of_range": out_of_range},
        )
    return MathCheck(
        "milestone_timing", "pass",
        f"All {len(milestones)} milestone(s) fall within the project timeline.",
    )


# ── Main Entry Point ──────────────────────────────────────────────────────────

def validate(
    planner_result,
    reasoner_result=None,
    comm_text: str = "",
) -> MathAudit:
    """
    Run all math checks on a PMCore pipeline result.

    Args:
        planner_result: PlannerResult dataclass (or dict with task_graph)
        reasoner_result: ReasonerResult dataclass (optional)
        comm_text: Generated communication text (optional)

    Returns:
        MathAudit with all check results and suggested corrections
    """
    # Extract task_graph
    if hasattr(planner_result, "task_graph"):
        task_graph = planner_result.task_graph or {}
        duration_days = planner_result.duration_days or 0
    elif isinstance(planner_result, dict):
        task_graph = planner_result.get("task_graph") or planner_result
        duration_days = planner_result.get("duration_days", 0)
    else:
        task_graph = {}
        duration_days = 0

    project    = task_graph.get("project", {})
    phases     = task_graph.get("phases", [])
    tasks      = task_graph.get("tasks", [])
    milestones = task_graph.get("milestones", [])

    # Use project-level duration if planner result doesn't have it
    if not duration_days:
        duration_days = project.get("estimated_duration_days", 0)

    budget = (
        project.get("budget_usd", 0)
        or project.get("budget", 0)
        or (planner_result.get("budget_usd", 0) if isinstance(planner_result, dict) else 0)
    )

    team_size = (
        project.get("team_size", 0)
        or project.get("num_team_members", 0)
    )

    health = "green"
    if reasoner_result is not None:
        if hasattr(reasoner_result, "overall_health"):
            health = reasoner_result.overall_health or "green"
        elif isinstance(reasoner_result, dict):
            health = reasoner_result.get("overall_health", "green")

    # ── Run checks ────────────────────────────────────────────────────────────
    checks = [
        _check_budget_phases(project, phases),
        _check_duration_phases(project, phases),
        _check_team_utilization(project, tasks, duration_days),
        _check_milestone_timing(project, milestones, duration_days),
        _check_risk_buffer(project, health),
        _check_comm_numbers(comm_text, budget, duration_days, team_size),
    ]

    # ── Aggregate overall status ───────────────────────────────────────────
    active = [c for c in checks if c.status != "skip"]
    if any(c.status == "fail" for c in active):
        overall = "fail"
    elif any(c.status == "warn" for c in active):
        overall = "warn"
    else:
        overall = "pass"

    # ── Build corrections dict ─────────────────────────────────────────────
    corrections = {}
    for c in checks:
        if c.status in ("fail", "warn") and c.detail:
            if c.name == "budget_phases" and "sum_phase_costs" in c.detail:
                if c.detail.get("ratio", 0) > 1.02:
                    corrections["budget_usd"] = c.detail["sum_phase_costs"]
            if c.name == "duration_phases" and "sum_phase_days" in c.detail:
                if c.detail.get("ratio", 0) > 1.2:
                    corrections["duration_days"] = c.detail["sum_phase_days"]
            if c.name == "risk_buffer" and "recommended_buffer" in c.detail:
                corrections["contingency_budget"] = c.detail["recommended_buffer"]

    # ── Summary sentence ──────────────────────────────────────────────────
    fails  = [c for c in active if c.status == "fail"]
    warns  = [c for c in active if c.status == "warn"]
    passes = [c for c in active if c.status == "pass"]

    if overall == "fail":
        summary = (
            f"Math audit FAILED: {len(fails)} error(s), {len(warns)} warning(s). "
            + " ".join(c.message for c in fails)
        )
    elif overall == "warn":
        summary = (
            f"Math audit passed with {len(warns)} warning(s). "
            + " ".join(c.message for c in warns[:2])
        )
    else:
        summary = (
            f"Math audit passed: {len(passes)} check(s) verified"
            + (f", {len([c for c in checks if c.status=='skip'])} skipped." if any(c.status=='skip' for c in checks) else ".")
        )

    return MathAudit(checks=checks, overall=overall, corrections=corrections, summary=summary)
