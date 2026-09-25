import React from 'react';
import type { CriticalDate } from '../types';

interface DeadlineCardProps {
  dates: CriticalDate[];
}

export const DeadlineCard: React.FC<DeadlineCardProps> = ({ dates }) => {
  if (dates.length === 0) {
    return null;
  }

  return (
    <div className="border border-zinc-800 mt-4">
      <div className="bg-zinc-900 px-4 py-2 border-b border-zinc-800 text-xs font-mono uppercase tracking-widest text-zinc-400">
        Critical Dates
      </div>
      <div className="p-4 grid grid-cols-1 gap-2">
        {dates.map((d, i) => (
          <div key={i} className="flex justify-between items-center text-sm">
            <span className="text-zinc-300">{d.event}</span>
            <span className="font-mono text-zinc-500">{d.date}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
