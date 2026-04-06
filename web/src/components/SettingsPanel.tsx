import { useState, useEffect, useRef, useCallback } from 'react';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  apiUrl: string;
  onApiUrlChange: (url: string) => void;
}

type ConnectionStatus = 'idle' | 'testing' | 'ok' | 'error';

interface ModelInfo {
  name: string;
  loaded: boolean;
  params?: string;
}

interface HealthResponse {
  status: string;
  models_loaded: boolean;
  [key: string]: unknown;
}


const DEFAULT_MODELS: ModelInfo[] = [
  { name: 'PMPlanner', loaded: false, params: '171.8M' },
  { name: 'PMReasoner', loaded: false, params: '125.3M' },
  { name: 'PMCommunicator', loaded: false, params: 'Phi-3.5 LoRA' },
];

export default function SettingsPanel({ isOpen, onClose, apiUrl, onApiUrlChange }: SettingsPanelProps) {
  const [localUrl, setLocalUrl] = useState(apiUrl);
  const [connStatus, setConnStatus] = useState<ConnectionStatus>('idle');
  const [connMessage, setConnMessage] = useState('');
  const [models, setModels] = useState<ModelInfo[]>(DEFAULT_MODELS);
  const [modelsLoaded, setModelsLoaded] = useState<boolean | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const firstInputRef = useRef<HTMLInputElement>(null);

  // Sync local URL with prop
  useEffect(() => {
    setLocalUrl(apiUrl);
  }, [apiUrl]);

  // Focus trap & keyboard close
  useEffect(() => {
    if (!isOpen) return;
    firstInputRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Reset connection status when URL changes
  useEffect(() => {
    setConnStatus('idle');
    setConnMessage('');
    setModelsLoaded(null);
    setModels(DEFAULT_MODELS);
  }, [localUrl]);

  const testConnection = useCallback(async () => {
    setConnStatus('testing');
    setConnMessage('');
    setModelsLoaded(null);

    const trimmed = localUrl.trim().replace(/\/+$/, '');

    try {
      const [healthRes, modelsRes] = await Promise.allSettled([
        fetch(`${trimmed}/health`, { signal: AbortSignal.timeout(5000) }),
        fetch(`${trimmed}/models`, { signal: AbortSignal.timeout(5000) }),
      ]);

      if (healthRes.status === 'rejected') {
        throw new Error(`Cannot connect to ${trimmed}`);
      }

      const healthFetch = healthRes.value;
      if (!healthFetch.ok) {
        throw new Error(`Server responded with HTTP ${healthFetch.status}`);
      }

      const health: HealthResponse = await healthFetch.json();
      setModelsLoaded(health.models_loaded ?? false);
      setConnStatus('ok');
      setConnMessage(`Connected · Status: ${health.status ?? 'unknown'}`);

      // Try to parse models endpoint (consumed for side effects; we rely on health for loaded state)
      if (modelsRes.status === 'fulfilled' && modelsRes.value.ok) {
        try {
          await modelsRes.value.json();
          setModels(DEFAULT_MODELS.map((m) => ({
            ...m,
            loaded: health.models_loaded ?? false,
          })));
        } catch {
          setModels(DEFAULT_MODELS.map((m) => ({
            ...m,
            loaded: health.models_loaded ?? false,
          })));
        }
      } else {
        setModels(DEFAULT_MODELS.map((m) => ({
          ...m,
          loaded: health.models_loaded ?? false,
        })));
      }
    } catch (err: unknown) {
      setConnStatus('error');
      setConnMessage(
        err instanceof Error ? err.message : 'Connection failed'
      );
      setModels(DEFAULT_MODELS);
    }
  }, [localUrl]);

  const handleSave = useCallback(() => {
    const trimmed = localUrl.trim().replace(/\/+$/, '');
    onApiUrlChange(trimmed);
    onClose();
  }, [localUrl, onApiUrlChange, onClose]);

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
      onClick={handleOverlayClick}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" aria-hidden="true" />

      {/* Panel */}
      <div
        ref={panelRef}
        className="relative w-full max-w-md bg-slate-900 border-l border-slate-700 h-full flex flex-col shadow-2xl animate-slide-in"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <h2 className="font-semibold text-slate-100">Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-200 transition-colors p-1 rounded-lg hover:bg-slate-800"
            aria-label="Close settings"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6">

          {/* API URL section */}
          <section>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">API Connection</h3>

            <div className="space-y-3">
              <div>
                <label htmlFor="api-url" className="block text-xs font-medium text-slate-400 mb-1.5">
                  API Base URL
                </label>
                <input
                  id="api-url"
                  ref={firstInputRef}
                  type="url"
                  value={localUrl}
                  onChange={(e) => setLocalUrl(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') testConnection();
                  }}
                  placeholder="http://localhost:8765"
                  className="input-base font-mono text-sm"
                  spellCheck={false}
                  autoCorrect="off"
                  autoCapitalize="off"
                />
                <p className="mt-1 text-xs text-slate-600">
                  Default: http://localhost:8765
                </p>
              </div>

              <button
                onClick={testConnection}
                disabled={connStatus === 'testing' || !localUrl.trim()}
                className="btn-secondary w-full justify-center"
              >
                {connStatus === 'testing' ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Testing...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Test Connection
                  </>
                )}
              </button>

              {/* Connection status */}
              {connStatus !== 'idle' && connStatus !== 'testing' && (
                <div
                  className={`flex items-start gap-2.5 rounded-lg px-3 py-2.5 text-sm animate-fade-in ${
                    connStatus === 'ok'
                      ? 'bg-emerald-950/40 border border-emerald-700/40 text-emerald-300'
                      : 'bg-red-950/40 border border-red-700/40 text-red-300'
                  }`}
                >
                  {connStatus === 'ok' ? (
                    <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  )}
                  <span>{connMessage}</span>
                </div>
              )}
            </div>
          </section>

          {/* Model status section */}
          <section>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
              Model Status
              {modelsLoaded !== null && (
                <span className={`ml-2 font-normal normal-case tracking-normal ${
                  modelsLoaded ? 'text-emerald-400' : 'text-red-400'
                }`}>
                  {modelsLoaded ? '— all loaded' : '— not loaded'}
                </span>
              )}
            </h3>

            <div className="space-y-2">
              {models.map((model) => (
                <div
                  key={model.name}
                  className="flex items-center justify-between bg-slate-800/60 rounded-lg px-3 py-2.5"
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${
                        modelsLoaded === null
                          ? 'bg-slate-600'
                          : model.loaded
                          ? 'bg-emerald-400'
                          : 'bg-red-400'
                      }`}
                    />
                    <span className="text-sm font-medium text-slate-200">{model.name}</span>
                  </div>
                  <div className="flex items-center gap-2 text-right">
                    {model.params && (
                      <span className="text-xs text-slate-500 font-mono">{model.params}</span>
                    )}
                    <span className={`text-xs font-medium ${
                      modelsLoaded === null
                        ? 'text-slate-600'
                        : model.loaded
                        ? 'text-emerald-400'
                        : 'text-slate-600'
                    }`}>
                      {modelsLoaded === null ? 'unknown' : model.loaded ? 'loaded' : 'not loaded'}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {modelsLoaded === null && (
              <p className="mt-2 text-xs text-slate-600 text-center">
                Test the connection to check model status
              </p>
            )}
          </section>

          {/* Keyboard shortcuts */}
          <section>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">Keyboard Shortcuts</h3>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-400">Run pipeline</span>
                <div className="flex items-center gap-1">
                  <kbd className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 text-xs font-mono">
                    {navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'}
                  </kbd>
                  <span className="text-slate-600 text-xs">+</span>
                  <kbd className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 text-xs font-mono">
                    Enter
                  </kbd>
                </div>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-400">Close settings</span>
                <kbd className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 text-xs font-mono">
                  Esc
                </kbd>
              </div>
            </div>
          </section>
        </div>

        {/* Footer actions */}
        <div className="px-5 py-4 border-t border-slate-800 flex items-center gap-3">
          <button
            onClick={handleSave}
            className="btn-primary flex-1 justify-center"
          >
            Save &amp; Close
          </button>
          <button
            onClick={onClose}
            className="btn-secondary flex-1 justify-center"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
