import React from 'react';

interface EvidencePanelProps {
  evidence: string;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({ evidence }) => {
  return (
    <div className="h-full border border-zinc-800 flex flex-col bg-black/40">
      <div className="px-4 py-2 border-b border-zinc-800 text-xs font-mono uppercase tracking-widest text-zinc-400 sticky top-0 bg-zinc-950">
        Raw Evidence & Traceability
      </div>
      <div className="p-4 flex-grow overflow-auto">
        <pre className="font-mono text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed">
          {evidence || "No evidence extracted."}
        </pre>
      </div>
    </div>
  );
};
