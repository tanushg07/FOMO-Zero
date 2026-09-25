import React from 'react';
import type { NoticeResult } from '../types';
import { ValidationBadge } from './ValidationBadge';

interface NoticeCardProps {
  notice: NoticeResult;
}

export const NoticeCard: React.FC<NoticeCardProps> = ({ notice }) => {
  return (
    <button type="button" onClick={() => { window.location.hash = `#notice/${encodeURIComponent(notice.id)}`; }} className="text-left border border-zinc-800 bg-zinc-900 p-4 flex flex-col gap-3 hover:border-zinc-600 focus:outline-none focus:ring-2 focus:ring-zinc-400">
      <div className="flex justify-between items-start gap-4">
        <h3 className="font-sans font-medium text-zinc-100 line-clamp-2">{notice.title}</h3>
        <ValidationBadge status={notice.validation_status} />
      </div>
      <p className="text-sm text-zinc-400 line-clamp-3">
        {notice.core_update}
      </p>
      <div className="flex gap-4 mt-2 border-t border-zinc-800 pt-3">
        <div className="flex flex-col">
          <span className="text-[10px] font-mono text-zinc-500 uppercase">Actions</span>
          <span className="text-sm text-zinc-300 font-mono">{notice.action_checklist.length}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] font-mono text-zinc-500 uppercase">Deadlines</span>
          <span className="text-sm text-zinc-300 font-mono">{notice.critical_dates.length}</span>
        </div>
      </div>
    </button>
  );
};
