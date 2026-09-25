import React from 'react';

export const EmptyState: React.FC = () => {
  return (
    <div className="border border-zinc-800 p-12 flex flex-col items-center justify-center text-center bg-zinc-900/50">
      <div className="font-mono text-zinc-500 mb-4">NO NOTICES IN SYSTEM</div>
      <p className="text-zinc-400 mb-6 max-w-md">
        The dashboard requires notices to extract deadlines and required actions.
      </p>
      <button 
        onClick={() => { window.location.hash = '#input'; }}
        className="px-6 py-2 bg-zinc-100 text-black uppercase font-bold tracking-wider hover:bg-white transition-colors border border-transparent"
      >
        Input New Notice
      </button>
    </div>
  );
};
