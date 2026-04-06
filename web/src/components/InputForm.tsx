import { useState, useRef, useCallback, useEffect, KeyboardEvent } from 'react';

interface InputFormProps {
  onRun: (request: string, commRequest: string) => void;
  onOpenSettings: () => void;
  isLoading: boolean;
}

const COMM_OPTIONS = [
  { value: 'Write a project kickoff email', label: 'Project kickoff email' },
  { value: 'Write a weekly status report', label: 'Weekly status report' },
  { value: 'Write a risk escalation memo', label: 'Risk escalation memo' },
  { value: 'Write an executive summary for the board', label: 'Executive summary for the board' },
  { value: 'Write a board update', label: 'Board update' },
  { value: 'Write a project closeout report', label: 'Project closeout report' },
  { value: 'custom', label: 'Custom...' },
] as const;

export default function InputForm({ onRun, onOpenSettings, isLoading }: InputFormProps) {
  const [projectDesc, setProjectDesc] = useState('');
  const [commSelection, setCommSelection] = useState(COMM_OPTIONS[0].value);
  const [customComm, setCustomComm] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const customInputRef = useRef<HTMLInputElement>(null);

  const isCustom = commSelection === 'custom';
  const effectiveComm = isCustom ? customComm : commSelection;
  const canRun = projectDesc.trim().length > 0 && effectiveComm.trim().length > 0 && !isLoading;

  // Auto-resize textarea
  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.max(120, el.scrollHeight)}px`;
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [projectDesc, resizeTextarea]);

  // Focus custom input when "Custom..." is selected
  useEffect(() => {
    if (isCustom) {
      customInputRef.current?.focus();
    }
  }, [isCustom]);

  const handleRun = useCallback(() => {
    if (!canRun) return;
    onRun(projectDesc.trim(), effectiveComm.trim());
  }, [canRun, onRun, projectDesc, effectiveComm]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleRun();
      }
    },
    [handleRun]
  );

  return (
    <section className="panel-card" aria-label="Pipeline input">
      <div className="panel-header">
        <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <span className="panel-title">Project Input</span>
      </div>

      <div className="p-4 flex flex-col gap-4">
        {/* Project Description */}
        <div>
          <label htmlFor="project-desc" className="block text-xs font-medium text-slate-400 mb-1.5">
            Project Description
          </label>
          <textarea
            id="project-desc"
            ref={textareaRef}
            value={projectDesc}
            onChange={(e) => setProjectDesc(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={resizeTextarea}
            placeholder="Describe your project — scale, budget, timeline, team size, industry..."
            rows={4}
            className="input-base resize-none font-mono text-sm leading-relaxed overflow-hidden"
            style={{ minHeight: '120px' }}
            disabled={isLoading}
            aria-describedby="project-desc-hint"
          />
          <p id="project-desc-hint" className="mt-1 text-xs text-slate-600">
            Press <kbd className="px-1 py-0.5 rounded bg-slate-800 text-slate-400 text-xs font-mono">
              {navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'}+Enter
            </kbd> to run
          </p>
        </div>

        {/* Communication Type */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <label htmlFor="comm-type" className="block text-xs font-medium text-slate-400 mb-1.5">
              Communication Type
            </label>
            <div className="relative">
              <select
                id="comm-type"
                value={commSelection}
                onChange={(e) => setCommSelection(e.target.value)}
                disabled={isLoading}
                className="input-base appearance-none pr-9 cursor-pointer"
              >
                {COMM_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <svg
                className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>

          {/* Custom communication input */}
          {isCustom && (
            <div className="flex-1 animate-fade-in">
              <label htmlFor="comm-custom" className="block text-xs font-medium text-slate-400 mb-1.5">
                Custom Instruction
              </label>
              <input
                id="comm-custom"
                ref={customInputRef}
                type="text"
                value={customComm}
                onChange={(e) => setCustomComm(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                    e.preventDefault();
                    handleRun();
                  }
                }}
                placeholder="e.g. Write a vendor briefing document..."
                disabled={isLoading}
                className="input-base"
              />
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={handleRun}
            disabled={!canRun}
            className="btn-primary min-w-[140px]"
            aria-label="Run the PMCore pipeline"
          >
            {isLoading ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Running...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Run Pipeline</span>
              </>
            )}
          </button>

          <button
            onClick={onOpenSettings}
            className="btn-secondary"
            disabled={isLoading}
            aria-label="Open settings"
            title="Settings"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span className="hidden sm:inline">Settings</span>
          </button>

          {isLoading && (
            <span className="text-xs text-slate-500 animate-pulse-slow ml-1">
              Processing through PMPlanner → PMReasoner → PMCommunicator...
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
