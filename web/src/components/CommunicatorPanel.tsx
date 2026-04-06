import { useState, useCallback, useRef } from 'react';
import type { CommunicatorResult } from '../App';

interface CommunicatorPanelProps {
  data: CommunicatorResult | null;
  isLoading: boolean;
}

const COMM_TYPE_LABELS: Record<string, string> = {
  kickoff: 'Kickoff Email',
  status_report: 'Status Report',
  escalation: 'Risk Escalation',
  board: 'Board Update',
  closeout: 'Project Closeout',
};

function CommTypeBadge({ type }: { type: string }) {
  const label = COMM_TYPE_LABELS[type] ?? type;
  const colorMap: Record<string, string> = {
    kickoff: 'bg-blue-500/20 text-blue-300 ring-blue-500/30',
    status_report: 'bg-emerald-500/20 text-emerald-300 ring-emerald-500/30',
    escalation: 'bg-red-500/20 text-red-300 ring-red-500/30',
    board: 'bg-purple-500/20 text-purple-300 ring-purple-500/30',
    closeout: 'bg-slate-500/20 text-slate-300 ring-slate-500/30',
  };
  const colorClass = colorMap[type] ?? 'bg-indigo-500/20 text-indigo-300 ring-indigo-500/30';

  return (
    <span className={`badge ring-1 ${colorClass}`}>{label}</span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for environments without clipboard API
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className={`btn-ghost transition-all duration-200 ${
        copied
          ? 'text-emerald-400 hover:text-emerald-400 hover:bg-emerald-900/30'
          : 'text-slate-400'
      }`}
      title="Copy to clipboard"
      aria-label={copied ? 'Copied!' : 'Copy to clipboard'}
    >
      {copied ? (
        <>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span>Copied!</span>
        </>
      ) : (
        <>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
          </svg>
          <span>Copy</span>
        </>
      )}
    </button>
  );
}

function ExportPdfButton({ subject, text }: { subject?: string; text: string }) {
  const handlePrint = useCallback(() => {
    // Set the print content div content
    const printEl = document.getElementById('print-communication');
    if (printEl) {
      const subjectHtml = subject
        ? `<h1>${subject.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</h1>`
        : '';
      const bodyHtml = text
        .split('\n')
        .map((line) =>
          line.trim() === ''
            ? '<br/>'
            : `<p>${line.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</p>`
        )
        .join('\n');
      printEl.innerHTML = subjectHtml + bodyHtml;
    }
    window.print();
  }, [subject, text]);

  return (
    <button
      onClick={handlePrint}
      className="btn-ghost"
      title="Export as PDF (use Save as PDF in the print dialog)"
      aria-label="Export to PDF"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
      </svg>
      <span>Export PDF</span>
    </button>
  );
}

function SkeletonLoading() {
  return (
    <div className="p-4 space-y-3 animate-pulse flex-1">
      <div className="skeleton h-5 w-3/4 rounded" />
      <div className="h-4" />
      <div className="skeleton h-4 rounded w-full" />
      <div className="skeleton h-4 rounded w-5/6" />
      <div className="skeleton h-4 rounded w-full" />
      <div className="skeleton h-4 rounded w-4/5" />
      <div className="h-4" />
      <div className="skeleton h-4 rounded w-full" />
      <div className="skeleton h-4 rounded w-3/4" />
      <div className="skeleton h-4 rounded w-full" />
      <div className="skeleton h-4 rounded w-5/6" />
      <div className="skeleton h-4 rounded w-full" />
      <div className="h-4" />
      <div className="skeleton h-4 rounded w-3/5" />
      <div className="skeleton h-4 rounded w-full" />
      <div className="skeleton h-4 rounded w-4/5" />
    </div>
  );
}

function ProseContent({ text }: { text: string }) {
  // Render paragraphs, preserving blank lines as paragraph breaks
  const paragraphs = text.split(/\n\n+/);

  return (
    <div className="space-y-3">
      {paragraphs.map((para, i) => {
        const lines = para.split('\n');
        return (
          <div key={i} className="text-sm text-slate-200 leading-relaxed">
            {lines.map((line, j) => (
              <span key={j}>
                {line}
                {j < lines.length - 1 && <br />}
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
}

export default function CommunicatorPanel({ data, isLoading }: CommunicatorPanelProps) {
  const contentRef = useRef<HTMLDivElement>(null);

  return (
    <article className="panel-card" aria-label="Communicator output">
      <div className="panel-header">
        <svg className="w-4 h-4 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
        <span className="panel-title">Communication</span>
        {data && <CommTypeBadge type={data.comm_type} />}
        <span className="ml-auto text-xs text-slate-600 font-mono">Phi-3.5 LoRA</span>
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        {isLoading ? (
          <SkeletonLoading />
        ) : !data ? (
          <div className="flex flex-col items-center justify-center flex-1 p-6 text-center min-h-[200px]">
            <svg className="w-10 h-10 text-slate-800 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <p className="text-sm text-slate-600">Run the pipeline to generate a communication document</p>
          </div>
        ) : (
          <>
            {/* Scrollable prose area */}
            <div
              ref={contentRef}
              className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0"
            >
              {/* Subject line */}
              {data.subject && (
                <div className="border-b border-slate-800 pb-3 mb-4">
                  <div className="text-xs text-slate-500 font-medium mb-1 uppercase tracking-wider">Subject</div>
                  <div className="text-base font-semibold text-slate-100 leading-snug">{data.subject}</div>
                </div>
              )}

              {/* Communication body */}
              <div className="animate-fade-in">
                <ProseContent text={data.communication} />
              </div>
            </div>

            {/* Actions toolbar */}
            <div className="border-t border-slate-800 px-3 py-2 flex items-center gap-1 bg-slate-900/50">
              <CopyButton text={data.subject ? `Subject: ${data.subject}\n\n${data.communication}` : data.communication} />
              <div className="w-px h-4 bg-slate-700 mx-1" />
              <ExportPdfButton subject={data.subject} text={data.communication} />

              <div className="ml-auto">
                <span className="text-xs text-slate-700 tabular-nums">
                  {data.communication.split(/\s+/).filter(Boolean).length} words
                </span>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Hidden print target — populated by ExportPdfButton */}
      <div id="print-communication" aria-hidden="true" />
    </article>
  );
}
