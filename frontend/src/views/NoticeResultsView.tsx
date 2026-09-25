import React from 'react';
import type { NoticeResult } from '../types';
import { ValidationBadge } from '../components/ValidationBadge';
import { ActionChecklist } from '../components/ActionChecklist';
import { DeadlineCard } from '../components/DeadlineCard';
import { AffectedGroupList } from '../components/AffectedGroupList';
import { EvidencePanel } from '../components/EvidencePanel';

interface NoticeResultsViewProps {
  data: NoticeResult;
}

export const NoticeResultsView: React.FC<NoticeResultsViewProps> = ({ data }) => {
  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto h-[85vh]">
      <div className="flex justify-between items-start border-b border-zinc-800 pb-4">
        <h1 className="font-sans text-2xl text-zinc-100">{data.title}</h1>
        <ValidationBadge status={data.validation_status} />
      </div>

      <div className="flex flex-col lg:flex-row gap-6 flex-grow overflow-hidden">
        {/* Left Column 60% */}
        <div className="lg:w-[60%] flex flex-col gap-6 overflow-y-auto pr-2 pb-10">
          
          <div className="border border-zinc-800 p-4 bg-zinc-900">
            <h4 className="text-[10px] font-mono text-zinc-500 uppercase mb-2">Core Update</h4>
            <p className="text-zinc-200 text-sm leading-relaxed">{data.core_update}</p>
          </div>

          <ActionChecklist items={data.action_checklist} />
          
          <DeadlineCard dates={data.critical_dates} />
          
          <AffectedGroupList group={data.target_audience} />

          {data.consequence_if_missed && (
             <div className="border border-red-500/50 bg-red-950/10 p-4 mt-2">
               <h4 className="text-[10px] font-mono text-red-400 uppercase mb-2">Consequence if Missed</h4>
               <p className="text-zinc-200 text-sm font-mono">{data.consequence_if_missed}</p>
             </div>
          )}
        </div>

        {/* Right Column 40% */}
        <div className="lg:w-[40%] flex flex-col gap-4 h-full">
          <div className="flex-grow min-h-[300px]">
            <EvidencePanel evidence={data.raw_evidence} />
          </div>
          
          <details className="border border-zinc-800 bg-zinc-950 group">
            <summary className="px-4 py-3 text-xs font-mono uppercase tracking-widest text-zinc-400 cursor-pointer list-none flex justify-between border-b border-transparent group-open:border-zinc-800">
              Original Text <span className="group-open:rotate-180 transition-transform">▼</span>
            </summary>
            <div className="p-4 max-h-[30vh] overflow-y-auto">
              <pre className="font-mono text-[10px] text-zinc-500 whitespace-pre-wrap leading-relaxed">
                {data.original_text}
              </pre>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
};
