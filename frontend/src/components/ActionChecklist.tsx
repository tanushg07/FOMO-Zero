import React from 'react';
import type { ActionItem } from '../types';

interface ActionChecklistProps {
  items: ActionItem[];
}

export const ActionChecklist: React.FC<ActionChecklistProps> = ({ items }) => {
  if (items.length === 0) {
    return (
      <div className="border border-zinc-800 p-4 text-sm text-zinc-500 font-mono">
        No specific actions required.
      </div>
    );
  }

  return (
    <div className="border border-zinc-800 flex flex-col">
      <div className="bg-zinc-900 px-4 py-2 border-b border-zinc-800 text-xs font-mono uppercase tracking-widest text-zinc-400">
        Required Actions
      </div>
      <ul className="divide-y divide-zinc-800">
        {items.map((item, index) => {
          const isHighPriority = item.priority === 'High';
          return (
            <li key={index} className={`p-4 flex flex-col sm:flex-row justify-between gap-2 ${isHighPriority ? 'bg-red-950/10' : ''}`}>
              <div className="flex items-start gap-3">
                <input type="checkbox" className="mt-1 appearance-none w-4 h-4 border border-zinc-500 checked:bg-zinc-100 checked:border-zinc-100 rounded-sm" />
                <span className={`text-sm ${isHighPriority ? 'text-red-400' : 'text-zinc-200'}`}>
                  {item.task}
                </span>
              </div>
              <div className="flex flex-col sm:items-end gap-1 font-mono text-xs text-zinc-500">
                {item.deadline && <span className={isHighPriority ? 'text-red-400/80' : ''}>DUE: {item.deadline}</span>}
                <span>PRIORITY: {item.priority.toUpperCase()}</span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
