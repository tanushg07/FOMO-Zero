import React from 'react';

interface ValidationBadgeProps {
  status: "Verified" | "Needs Review" | "Blocked";
}

export const ValidationBadge: React.FC<ValidationBadgeProps> = ({ status }) => {
  const getStyles = () => {
    switch (status) {
      case "Verified":
        return "text-emerald-400 border-emerald-400";
      case "Needs Review":
        return "text-amber-400 border-amber-400";
      case "Blocked":
        return "text-red-400 border-red-400";
      default:
        return "text-zinc-400 border-zinc-400";
    }
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 border text-xs font-mono uppercase tracking-widest ${getStyles()}`}>
      {status}
    </span>
  );
};
