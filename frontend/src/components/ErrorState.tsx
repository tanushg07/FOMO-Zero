import React from 'react';

interface ErrorStateProps {
  message: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ message }) => {
  return (
    <div className="border border-red-500/50 bg-red-950/20 p-4 mt-2">
      <div className="text-red-400 font-mono text-xs uppercase mb-1">SYSTEM ERROR</div>
      <div className="text-zinc-200 text-sm font-mono whitespace-pre-wrap">{message}</div>
    </div>
  );
};
