import type { ReactNode } from 'react';
import type { ReasonerResult } from '../App';

interface ReasonerPanelProps {
  data: ReasonerResult | null;
  isLoading: boolean;
}

interface HealthConfig {
  dot: string;
  ring: string;
  bg: string;
  text: string;
  label: string;
  pulse: boolean;
}

function getHealthConfig(health: string): HealthConfig {
  const norm = health?.toLowerCase() ?? '';
  if (norm === 'green') {
    return {
      dot: 'bg-emerald-400',
      ring: 'ring-emerald-500/40',
      bg: 'bg-emerald-950/30',
      text: 'text-emerald-300',
      label: 'On Track',
      pulse: false,
    };
  }
  if (norm === 'yellow') {
    return {
      dot: 'bg-amber-400',
      ring: 'ring-amber-500/40',
      bg: 'bg-amber-950/30',
      text: 'text-amber-300',
      label: 'Attention Needed',
      pulse: true,
    };
  }
  if (norm === 'red') {
    return {
      dot: 'bg-red-400',
      ring: 'ring-red-500/40',
      bg: 'bg-red-950/30',
      text: 'text-red-300',
      label: 'Critical',
      pulse: true,
    };
  }
  return {
    dot: 'bg-slate-400',
    ring: 'ring-slate-500/40',
    bg: 'bg-slate-800/30',
    text: 'text-slate-300',
    label: health,
    pulse: false,
  };
}

function HealthIndicator({ health }: { health: string }) {
  const config = getHealthConfig(health);
  return (
    <div className={`flex items-center gap-3 rounded-xl px-4 py-3 ${config.bg} ring-1 ${config.ring}`}>
      <span className="relative flex shrink-0">
        <span
          className={`w-4 h-4 rounded-full ${config.dot} ring-4 ${config.ring} ${
            config.pulse ? 'animate-pulse-slow' : ''
          }`}
        />
      </span>
      <div>
        <div className="text-xs text-slate-500 font-medium">Overall Health</div>
        <div className={`font-bold text-lg leading-tight ${config.text}`}>{config.label}</div>
      </div>
    </div>
  );
}

function BulletList({ items, color }: { items: string[]; color: string }) {
  if (!items || items.length === 0) return null;
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2.5 text-sm text-slate-300 leading-snug">
          <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${color}`} />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">{children}</h3>
  );
}

function SkeletonLoading() {
  return (
    <div className="p-4 space-y-4 animate-pulse">
      <div className="skeleton h-16 rounded-xl" />
      <div>
        <div className="skeleton h-3 w-20 rounded mb-3" />
        <div className="space-y-2">
          <div className="flex gap-2">
            <div className="skeleton w-2 h-2 rounded-full mt-1.5 shrink-0" />
            <div className="skeleton h-4 rounded flex-1" />
          </div>
          <div className="flex gap-2">
            <div className="skeleton w-2 h-2 rounded-full mt-1.5 shrink-0" />
            <div className="skeleton h-4 rounded flex-1" />
          </div>
          <div className="flex gap-2">
            <div className="skeleton w-2 h-2 rounded-full mt-1.5 shrink-0" />
            <div className="skeleton h-4 rounded w-4/5" />
          </div>
        </div>
      </div>
      <div>
        <div className="skeleton h-3 w-24 rounded mb-2" />
        <div className="skeleton h-10 rounded-lg" />
      </div>
      <div>
        <div className="skeleton h-3 w-28 rounded mb-3" />
        <div className="space-y-2">
          <div className="flex gap-2">
            <div className="skeleton w-2 h-2 rounded-full mt-1.5 shrink-0" />
            <div className="skeleton h-4 rounded flex-1" />
          </div>
          <div className="flex gap-2">
            <div className="skeleton w-2 h-2 rounded-full mt-1.5 shrink-0" />
            <div className="skeleton h-4 rounded w-5/6" />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ReasonerPanel({ data, isLoading }: ReasonerPanelProps) {
  return (
    <article className="panel-card" aria-label="Reasoner results">
      <div className="panel-header">
        <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        <span className="panel-title">Reasoner</span>
        <span className="ml-auto text-xs text-slate-600 font-mono">PMReasoner 125.3M</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <SkeletonLoading />
        ) : !data ? (
          <div className="flex flex-col items-center justify-center h-full min-h-[200px] p-6 text-center">
            <svg className="w-10 h-10 text-slate-800 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-sm text-slate-600">Run the pipeline to generate risk analysis</p>
          </div>
        ) : (
          <div className="p-4 space-y-5 animate-fade-in">
            {/* Health */}
            <HealthIndicator health={data.overall_health} />

            {/* Top risks */}
            {data.top_risks?.length > 0 && (
              <div>
                <SectionLabel>Top Risks</SectionLabel>
                <BulletList items={data.top_risks.slice(0, 5)} color="bg-red-400" />
              </div>
            )}

            {/* Critical path */}
            {data.critical_path && (
              <div>
                <SectionLabel>Critical Path</SectionLabel>
                <div className="bg-slate-800/60 rounded-lg px-3 py-2.5 text-sm text-slate-300 font-mono leading-relaxed break-words">
                  {data.critical_path}
                </div>
              </div>
            )}

            {/* Recommendations */}
            {data.recommendations?.length > 0 && (
              <div>
                <SectionLabel>Recommendations</SectionLabel>
                <BulletList items={data.recommendations} color="bg-emerald-400" />
              </div>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
