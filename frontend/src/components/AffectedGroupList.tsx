import React from 'react';

interface AffectedGroupListProps {
  group: string;
}

export const AffectedGroupList: React.FC<AffectedGroupListProps> = ({ group }) => {
  return (
    <div className="border border-zinc-800 mt-4">
      <div className="bg-zinc-900 px-4 py-2 border-b border-zinc-800 text-xs font-mono uppercase tracking-widest text-zinc-400">
        Target Audience
      </div>
      <div className="p-4 text-sm text-zinc-200">
        {group || "Not clearly specified."}
      </div>
    </div>
  );
};
