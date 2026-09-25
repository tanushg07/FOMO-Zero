import React from 'react';
import type { NoticeResult } from '../types';
import { ValidationBadge } from '../components/ValidationBadge';

interface ReviewCenterViewProps {
  data: NoticeResult[];
}

export const ReviewCenterView: React.FC<ReviewCenterViewProps> = ({ data }) => {
  if (data.length === 0) {
    return (
      <div className="border border-zinc-800 p-8 text-center text-sm font-mono text-zinc-500">
        NO NOTICES REQUIRE REVIEW
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 max-w-6xl mx-auto">
      <h2 className="font-sans text-xl uppercase tracking-widest border-b border-zinc-800 pb-2">Review Center</h2>
      <div className="border border-zinc-800 overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-zinc-900 border-b border-zinc-800">
              <th className="p-3 text-xs font-mono uppercase tracking-widest text-zinc-400 font-normal">Notice Title</th>
              <th className="p-3 text-xs font-mono uppercase tracking-widest text-zinc-400 font-normal">Status</th>
              <th className="p-3 text-xs font-mono uppercase tracking-widest text-zinc-400 font-normal">Warnings / Action Items</th>
              <th className="p-3 text-xs font-mono uppercase tracking-widest text-zinc-400 font-normal">Deadlines</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800 text-sm">
            {data.map((notice) => {
              const isBlocked = notice.validation_status === 'Blocked';
              const needsReview = notice.validation_status === 'Needs Review';
              return (
                <tr key={notice.id} className="hover:bg-zinc-900/50 transition-colors">
                  <td className="p-3 align-top max-w-[300px]">
                    <span className="text-zinc-200 line-clamp-2">{notice.title}</span>
                  </td>
                  <td className="p-3 align-top whitespace-nowrap">
                    <ValidationBadge status={notice.validation_status} />
                  </td>
                  <td className="p-3 align-top max-w-[300px]">
                    <div className="flex flex-col gap-1 font-mono text-xs">
                      {isBlocked && <span className="text-red-400">MISSING DATA OR CONFLICTS</span>}
                      {needsReview && <span className="text-amber-400">REQUIRES HUMAN VERIFICATION</span>}
                      <span className="text-zinc-500">{notice.action_checklist.length} actions extracted</span>
                    </div>
                  </td>
                  <td className="p-3 align-top text-zinc-400 font-mono text-xs">
                    {notice.critical_dates.length} dates
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
