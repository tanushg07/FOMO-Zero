import React from 'react';
import type { NoticeResult } from '../types';
import { NoticeCard } from '../components/NoticeCard';
import { EmptyState } from '../components/EmptyState';
import { ValidationBadge } from '../components/ValidationBadge';

interface DashboardViewProps {
  notices: NoticeResult[];
}

export const DashboardView: React.FC<DashboardViewProps> = ({ notices }) => {
  if (!notices || notices.length === 0) {
    return <EmptyState />;
  }

  const allActions = notices.flatMap((n) => n.action_checklist);
  const reviewRequired = notices.filter((n) => n.validation_status !== 'Verified');
  const allDates = notices.flatMap((n) => n.critical_dates);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 max-w-7xl mx-auto items-start">
      {/* Left Column: Open Actions & Upcoming Deadlines */}
      <div className="flex flex-col gap-6">
        <section className="border border-zinc-800">
          <div className="bg-zinc-900 px-4 py-2 border-b border-zinc-800 text-xs font-mono uppercase tracking-widest text-zinc-400">
            Open Actions ({allActions.length})
          </div>
          <div className="p-4 flex flex-col gap-3">
            {allActions.length > 0 ? (
              allActions.map((action, i) => (
                <div key={i} className="flex flex-col border-b border-zinc-800/50 pb-2 last:border-0 last:pb-0">
                  <span className={`text-sm ${action.priority === 'High' ? 'text-red-400' : 'text-zinc-200'}`}>
                    {action.task}
                  </span>
                  {action.deadline && (
                    <span className="text-[10px] font-mono text-zinc-500">DUE: {action.deadline}</span>
                  )}
                </div>
              ))
            ) : (
              <span className="text-xs font-mono text-zinc-600">NO PENDING ACTIONS</span>
            )}
          </div>
        </section>

        <section className="border border-zinc-800">
          <div className="bg-zinc-900 px-4 py-2 border-b border-zinc-800 text-xs font-mono uppercase tracking-widest text-zinc-400">
            Upcoming Deadlines
          </div>
          <div className="p-4 flex flex-col gap-3">
            {allDates.length > 0 ? (
              allDates.map((date, i) => (
                <div key={i} className="flex justify-between items-center border-b border-zinc-800/50 pb-2 last:border-0 last:pb-0">
                  <span className="text-sm text-zinc-300 truncate pr-2">{date.event}</span>
                  <span className="text-xs font-mono text-amber-400 whitespace-nowrap">{date.date}</span>
                </div>
              ))
            ) : (
              <span className="text-xs font-mono text-zinc-600">NO DEADLINES</span>
            )}
          </div>
        </section>
      </div>

      {/* Middle Column: Recent Notices */}
      <div className="flex flex-col gap-4">
        <h2 className="text-xs font-mono uppercase tracking-widest text-zinc-500 pb-2 border-b border-zinc-800">
          Recent Notices
        </h2>
        {notices.map((notice) => (
          <NoticeCard key={notice.id} notice={notice} />
        ))}
      </div>

      {/* Right Column: Review Required */}
      <div className="flex flex-col gap-4">
        <h2 className="text-xs font-mono uppercase tracking-widest text-zinc-500 pb-2 border-b border-zinc-800">
          Review Required ({reviewRequired.length})
        </h2>
        {reviewRequired.length > 0 ? (
          reviewRequired.map((notice) => (
            <div key={notice.id} className="border border-zinc-800 p-4 bg-zinc-950 flex flex-col gap-2">
              <span className="text-sm text-zinc-200 line-clamp-2">{notice.title}</span>
              <ValidationBadge status={notice.validation_status} />
            </div>
          ))
        ) : (
          <div className="border border-emerald-900/30 p-4 flex flex-col items-center justify-center text-center">
            <span className="text-emerald-500 font-mono text-xs">ALL CLEAR</span>
          </div>
        )}
      </div>
    </div>
  );
};
