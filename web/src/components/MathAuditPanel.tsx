import React from "react";

interface MathCheck {
  name: string;
  status: "pass" | "warn" | "fail" | "skip";
  message: string;
  detail?: Record<string, unknown>;
}

interface MathAudit {
  overall: "pass" | "warn" | "fail";
  summary: string;
  checks: MathCheck[];
  corrections: Record<string, number>;
}

interface Props {
  audit: MathAudit | null;
  loading?: boolean;
}

const STATUS_CONFIG = {
  pass: { icon: "✓", bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-400", badge: "bg-emerald-500/20 text-emerald-300" },
  warn: { icon: "⚠", bg: "bg-amber-500/10",   border: "border-amber-500/30",   text: "text-amber-400",   badge: "bg-amber-500/20   text-amber-300"   },
  fail: { icon: "✗", bg: "bg-red-500/10",     border: "border-red-500/30",     text: "text-red-400",     badge: "bg-red-500/20     text-red-300"     },
  skip: { icon: "–", bg: "bg-slate-700/30",   border: "border-slate-600/30",   text: "text-slate-500",   badge: "bg-slate-700/50   text-slate-400"   },
};

const CHECK_LABELS: Record<string, string> = {
  budget_phases:     "Budget Breakdown",
  duration_phases:   "Timeline Phases",
  team_utilization:  "Team Capacity",
  milestone_timing:  "Milestone Timing",
  risk_buffer:       "Risk Buffer",
  comm_numbers:      "Comm. Accuracy",
};

function fmt(val: unknown): string {
  if (typeof val === "number") {
    if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
    if (val >= 1_000) return `$${(val / 1_000).toFixed(0)}K`;
    if (Number.isInteger(val)) return val.toString();
    return val.toFixed(2);
  }
  return String(val);
}

export default function MathAuditPanel({ audit, loading }: Props) {
  const [expanded, setExpanded] = React.useState<string | null>(null);

  if (loading) {
    return (
      <div className="panel-card">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xs font-bold tracking-widest text-slate-400 uppercase">PMMath</span>
        </div>
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-8 rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (!audit) {
    return (
      <div className="panel-card">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xs font-bold tracking-widest text-slate-400 uppercase">PMMath</span>
          <span className="text-xs text-slate-500">— Math Validator</span>
        </div>
        <p className="text-sm text-slate-500 italic">
          Run the pipeline to validate project numbers.
        </p>
      </div>
    );
  }

  const cfg = STATUS_CONFIG[audit.overall] || STATUS_CONFIG.skip;
  const activeChecks = audit.checks.filter((c) => c.status !== "skip");
  const skippedCount = audit.checks.length - activeChecks.length;
  const hasFixes = Object.keys(audit.corrections).length > 0;

  return (
    <div className="panel-card">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold tracking-widest text-slate-400 uppercase">PMMath</span>
          <span className="text-xs text-slate-500">— Math Validator</span>
        </div>
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold ${cfg.badge}`}>
          {cfg.icon} {audit.overall.toUpperCase()}
        </span>
      </div>

      {/* Summary */}
      <p className={`text-xs mb-4 leading-relaxed ${cfg.text}`}>
        {audit.summary}
      </p>

      {/* Suggested corrections */}
      {hasFixes && (
        <div className="mb-4 rounded border border-amber-500/30 bg-amber-500/5 p-3">
          <p className="text-xs font-semibold text-amber-400 mb-1.5">Suggested Corrections</p>
          <div className="space-y-1">
            {Object.entries(audit.corrections).map(([key, val]) => (
              <div key={key} className="flex justify-between text-xs">
                <span className="text-slate-400">{key.replace(/_/g, " ")}</span>
                <span className="text-amber-300 font-mono">{fmt(val)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Individual checks */}
      <div className="space-y-1.5">
        {audit.checks.map((check) => {
          const c = STATUS_CONFIG[check.status] || STATUS_CONFIG.skip;
          const isOpen = expanded === check.name;
          const hasDetail = !!check.detail && Object.keys(check.detail).length > 0;
          const label = CHECK_LABELS[check.name] || check.name.replace(/_/g, " ");

          return (
            <div key={check.name} className={`rounded border ${c.border} ${c.bg} overflow-hidden`}>
              <button
                className="w-full flex items-center gap-2 px-3 py-2 text-left"
                onClick={() => hasDetail && setExpanded(isOpen ? null : check.name)}
                disabled={!hasDetail}
              >
                <span className={`text-sm font-medium ${c.text} w-4 shrink-0`}>{c.icon}</span>
                <span className="text-xs font-medium text-slate-300 flex-1">{label}</span>
                {check.status !== "skip" && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${c.badge} shrink-0`}>
                    {check.status}
                  </span>
                )}
                {hasDetail && (
                  <span className="text-slate-500 text-xs">{isOpen ? "▲" : "▼"}</span>
                )}
              </button>

              {/* Message */}
              <div className="px-3 pb-2">
                <p className="text-xs text-slate-400 leading-relaxed">{check.message}</p>
              </div>

              {/* Detail expansion */}
              {isOpen && check.detail && (
                <div className="px-3 pb-3 pt-1 border-t border-slate-700/50">
                  <div className="space-y-1">
                    {Object.entries(check.detail).map(([k, v]) => (
                      <div key={k} className="flex justify-between text-xs">
                        <span className="text-slate-500">{k.replace(/_/g, " ")}</span>
                        <span className="text-slate-300 font-mono text-right ml-4">
                          {typeof v === "object" && v !== null
                            ? JSON.stringify(v, null, 0).slice(0, 60)
                            : fmt(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {skippedCount > 0 && (
        <p className="text-xs text-slate-600 mt-2 text-right">
          {skippedCount} check{skippedCount > 1 ? "s" : ""} skipped (insufficient data)
        </p>
      )}
    </div>
  );
}
