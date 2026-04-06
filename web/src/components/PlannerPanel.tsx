import { useState } from 'react';
import type { PlannerResult, PlannerPhase, PlannerMilestone } from '../App';

interface PlannerPanelProps {
  data: PlannerResult | null;
  isLoading: boolean;
}

function MethodologyBadge({ methodology }: { methodology: string }) {
  const norm = methodology?.toLowerCase() ?? '';
  if (norm === 'agile') {
    return <span className="badge-agile">Agile</span>;
  }
  if (norm === 'waterfall') {
    return <span className="badge-waterfall">Waterfall</span>;
  }
  if (norm === 'hybrid') {
    return <span className="badge-hybrid">Hybrid</span>;
  }
  return (
    <span className="badge bg-slate-700 text-slate-300 ring-1 ring-slate-600">
      {methodology}
    </span>
  );
}

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-slate-800/60 rounded-lg px-3 py-2.5">
      <div className="text-xs text-slate-500 font-medium mb-0.5">{label}</div>
      <div className="text-xl font-bold text-slate-100 tabular-nums leading-tight">
        {value}
        {sub && <span className="text-sm font-normal text-slate-400 ml-1">{sub}</span>}
      </div>
    </div>
  );
}

function PhaseRow({ phase, index }: { phase: PlannerPhase; index: number }) {
  const [open, setOpen] = useState(false);
  const hasTasks = phase.tasks && phase.tasks.length > 0;

  return (
    <div className="border border-slate-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-800/60 transition-colors"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-5 h-5 rounded-full bg-indigo-900/60 text-indigo-300 text-xs font-bold flex items-center justify-center shrink-0">
            {index + 1}
          </span>
          <span className="text-sm text-slate-200 font-medium truncate">{phase.name}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          {phase.duration_days != null && (
            <span className="text-xs text-slate-500">{phase.duration_days}d</span>
          )}
          {hasTasks && (
            <svg
              className={`w-3.5 h-3.5 text-slate-500 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>
      </button>

      {open && hasTasks && (
        <div className="px-3 pb-3 pt-1 bg-slate-900/50 border-t border-slate-800">
          <ul className="space-y-1">
            {phase.tasks!.map((task, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-slate-400">
                <span className="mt-1 w-1 h-1 rounded-full bg-indigo-500 shrink-0" />
                {task}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MilestoneRow({ milestone }: { milestone: PlannerMilestone }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-indigo-400">◆</span>
      <span className="text-slate-300">{milestone.name}</span>
      {milestone.day != null && (
        <span className="text-slate-600 ml-auto tabular-nums">Day {milestone.day}</span>
      )}
    </div>
  );
}

function SkeletonLoading() {
  return (
    <div className="p-4 space-y-4 animate-pulse">
      <div className="grid grid-cols-2 gap-3">
        <div className="skeleton h-16 rounded-lg" />
        <div className="skeleton h-16 rounded-lg" />
        <div className="skeleton h-16 rounded-lg" />
        <div className="skeleton h-16 rounded-lg" />
      </div>
      <div className="skeleton h-4 w-24 rounded" />
      <div className="space-y-2">
        <div className="skeleton h-9 rounded-lg" />
        <div className="skeleton h-9 rounded-lg" />
        <div className="skeleton h-9 rounded-lg" />
      </div>
    </div>
  );
}

export default function PlannerPanel({ data, isLoading }: PlannerPanelProps) {
  const [phasesOpen, setPhasesOpen] = useState(false);
  const [milestonesOpen, setMilestonesOpen] = useState(false);

  return (
    <article className="panel-card" aria-label="Planner results">
      <div className="panel-header">
        <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        <span className="panel-title">Planner</span>
        <span className="ml-auto text-xs text-slate-600 font-mono">PMPlanner 171.8M</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <SkeletonLoading />
        ) : !data ? (
          <div className="flex flex-col items-center justify-center h-full min-h-[200px] p-6 text-center">
            <svg className="w-10 h-10 text-slate-800 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
            </svg>
            <p className="text-sm text-slate-600">Run the pipeline to generate a project plan</p>
          </div>
        ) : (
          <div className="p-4 space-y-4 animate-fade-in">
            {/* Methodology */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 font-medium">Methodology</span>
              <MethodologyBadge methodology={data.methodology} />
            </div>

            {/* Stats grid */}
            <div className="grid grid-cols-2 gap-2">
              <Stat label="Duration" value={data.duration_days} sub="days" />
              <Stat label="Tasks" value={data.num_tasks} />
              {data.phases?.length > 0 && (
                <Stat label="Phases" value={data.phases.length} />
              )}
              {data.budget_usd > 0 && (
                <Stat
                  label="Budget"
                  value={`$${(data.budget_usd / 1_000_000).toFixed(1)}M`}
                />
              )}
              {data.milestones?.length > 0 && (
                <Stat label="Milestones" value={data.milestones.length} />
              )}
            </div>

            {/* Phases */}
            {data.phases?.length > 0 && (
              <div>
                <button
                  onClick={() => setPhasesOpen((o) => !o)}
                  className="w-full flex items-center justify-between text-xs font-semibold text-slate-400 hover:text-slate-200 transition-colors py-1 group"
                  aria-expanded={phasesOpen}
                >
                  <span className="uppercase tracking-wider">
                    Phases ({data.phases.length})
                  </span>
                  <svg
                    className={`w-3.5 h-3.5 transition-transform duration-200 ${phasesOpen ? 'rotate-180' : ''} group-hover:text-slate-300`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {phasesOpen && (
                  <div className="mt-2 space-y-1.5 animate-fade-in">
                    {data.phases.map((phase, i) => (
                      <PhaseRow key={i} phase={phase} index={i} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Milestones */}
            {data.milestones?.length > 0 && (
              <div>
                <button
                  onClick={() => setMilestonesOpen((o) => !o)}
                  className="w-full flex items-center justify-between text-xs font-semibold text-slate-400 hover:text-slate-200 transition-colors py-1 group"
                  aria-expanded={milestonesOpen}
                >
                  <span className="uppercase tracking-wider">
                    Milestones ({data.milestones.length})
                  </span>
                  <svg
                    className={`w-3.5 h-3.5 transition-transform duration-200 ${milestonesOpen ? 'rotate-180' : ''} group-hover:text-slate-300`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {milestonesOpen && (
                  <div className="mt-2 space-y-2 animate-fade-in">
                    {data.milestones.map((m, i) => (
                      <MilestoneRow key={i} milestone={m} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
