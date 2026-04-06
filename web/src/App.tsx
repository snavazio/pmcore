import { useState, useCallback, useEffect } from 'react';
import InputForm from './components/InputForm';
import PlannerPanel from './components/PlannerPanel';
import ReasonerPanel from './components/ReasonerPanel';
import CommunicatorPanel from './components/CommunicatorPanel';
import MathAuditPanel from './components/MathAuditPanel';
import SettingsPanel from './components/SettingsPanel';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PlannerPhase {
  name: string;
  duration_days?: number;
  tasks?: string[];
  [key: string]: unknown;
}

export interface PlannerMilestone {
  name: string;
  day?: number;
  [key: string]: unknown;
}

export interface PlannerResult {
  methodology: 'agile' | 'waterfall' | 'hybrid' | string;
  duration_days: number;
  num_tasks: number;
  phases: PlannerPhase[];
  milestones: PlannerMilestone[];
  budget_usd: number;
}

export interface ReasonerResult {
  overall_health: 'green' | 'yellow' | 'red' | string;
  top_risks: string[];
  critical_path: string;
  recommendations: string[];
}

export interface CommunicatorResult {
  communication: string;
  comm_type: 'kickoff' | 'status_report' | 'escalation' | 'board' | 'closeout' | string;
  subject?: string;
}

export interface MathCheck {
  name: string;
  status: 'pass' | 'warn' | 'fail' | 'skip';
  message: string;
  detail?: Record<string, unknown>;
}

export interface MathAuditResult {
  overall: 'pass' | 'warn' | 'fail';
  summary: string;
  checks: MathCheck[];
  corrections: Record<string, number>;
}

export interface PipelineResponse {
  planner: PlannerResult;
  reasoner: ReasonerResult;
  communicator: CommunicatorResult;
  math_audit?: MathAuditResult;
}

export type LoadingState = 'idle' | 'loading' | 'success' | 'error';

export interface AppError {
  type: 'network' | 'api' | 'unknown';
  message: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function App() {
  const [apiUrl, setApiUrl] = useState<string>(() => {
    return localStorage.getItem('pmcore_api_url') ?? 'http://localhost:8765';
  });
  const [showSettings, setShowSettings] = useState(false);
  const [loadingState, setLoadingState] = useState<LoadingState>('idle');
  const [error, setError] = useState<AppError | null>(null);
  const [result, setResult] = useState<PipelineResponse | null>(null);

  // Persist API URL
  useEffect(() => {
    localStorage.setItem('pmcore_api_url', apiUrl);
  }, [apiUrl]);

  const runPipeline = useCallback(
    async (request: string, commRequest: string) => {
      setLoadingState('loading');
      setError(null);
      setResult(null);

      const endpoint = `${apiUrl}/plan`;

      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            request,
            comm_request: commRequest,
            verbose: false,
          }),
        });

        if (!response.ok) {
          let detail = `HTTP ${response.status}`;
          try {
            const errData = await response.json();
            detail = (errData.detail as string | undefined) ?? (errData.message as string | undefined) ?? detail;
          } catch {
            // ignore parse error, use status text
          }
          setError({ type: 'api', message: detail });
          setLoadingState('error');
          return;
        }

        const data: PipelineResponse = await response.json();
        setResult(data);
        setLoadingState('success');
      } catch (err: unknown) {
        if (err instanceof TypeError) {
          setError({
            type: 'network',
            message: `Cannot reach PMCore API at ${apiUrl}. Is the server running?`,
          });
        } else {
          setError({
            type: 'unknown',
            message: err instanceof Error ? err.message : 'An unexpected error occurred.',
          });
        }
        setLoadingState('error');
      }
    },
    [apiUrl]
  );

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* ── Header ── */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl select-none" aria-hidden="true">🏗</span>
            <div>
              <span className="font-bold text-slate-100 text-lg tracking-tight">PMCore</span>
              <span className="ml-2 text-xs text-slate-500 font-medium hidden sm:inline">
                AI Project Management
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <a
              href="https://github.com/snavazio/pmcore"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost text-slate-500 hover:text-slate-300"
              title="View on GitHub"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              <span className="hidden sm:inline">GitHub</span>
            </a>
          </div>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="flex-1 flex flex-col max-w-[1600px] mx-auto w-full px-4 sm:px-6 py-6 gap-5">

        {/* Error Banner */}
        {error && (
          <div
            role="alert"
            className={`rounded-lg border px-4 py-3 flex items-start gap-3 animate-fade-in ${
              error.type === 'network'
                ? 'bg-amber-950/40 border-amber-700/60 text-amber-300'
                : 'bg-red-950/40 border-red-700/60 text-red-300'
            }`}
          >
            <svg className="w-5 h-5 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div className="flex-1 text-sm">
              <span className="font-semibold">{error.type === 'network' ? 'Connection Error' : 'Pipeline Error'}: </span>
              {error.message}
            </div>
            <button
              onClick={() => setError(null)}
              className="text-current opacity-60 hover:opacity-100 transition-opacity shrink-0"
              aria-label="Dismiss error"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Input Form */}
        <InputForm
          onRun={runPipeline}
          onOpenSettings={() => setShowSettings(true)}
          isLoading={loadingState === 'loading'}
        />

        {/* Four-panel output grid: 3 top + 1 math audit bottom-left */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <PlannerPanel
            data={result?.planner ?? null}
            isLoading={loadingState === 'loading'}
          />
          <ReasonerPanel
            data={result?.reasoner ?? null}
            isLoading={loadingState === 'loading'}
          />
          <CommunicatorPanel
            data={result?.communicator ?? null}
            isLoading={loadingState === 'loading'}
          />
        </div>
        {/* PMMath audit spans full width below the three panels */}
        {(loadingState === 'loading' || result?.math_audit) && (
          <MathAuditPanel
            audit={result?.math_audit ?? null}
            loading={loadingState === 'loading'}
          />
        )}
      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-slate-800 bg-slate-900/50 py-3 px-6">
        <div className="max-w-[1600px] mx-auto">
          <p className="text-center text-xs text-slate-600 font-mono">
            PMCore v6 · PMPlanner 171.8M · PMReasoner 125.3M · PMCommunicator Phi-3.5 LoRA · PMMath Validator
          </p>
        </div>
      </footer>

      {/* ── Settings Panel ── */}
      <SettingsPanel
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
        apiUrl={apiUrl}
        onApiUrlChange={setApiUrl}
      />
    </div>
  );
}
