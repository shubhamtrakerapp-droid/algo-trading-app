import React from 'react';

interface StatCardProps {
  title: string;
  value: string | number;
  subValue?: string;
  icon?: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  badge?: string;
  onClick?: () => void;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subValue,
  icon,
  trend,
  badge,
  onClick,
}) => {
  const getTrendColor = () => {
    if (trend === 'up') return 'text-emerald-400';
    if (trend === 'down') return 'text-rose-400';
    return 'text-slate-100';
  };

  return (
    <div
      onClick={onClick}
      className={`bg-card border border-border rounded-xl p-3 sm:p-4 flex flex-col justify-between hover:border-slate-700 transition-colors ${
        onClick ? 'cursor-pointer hover:bg-surface/50' : ''
      }`}
    >
      <div className="flex items-center justify-between text-slate-400 mb-1.5 gap-1.5">
        <span className="text-[10px] sm:text-xs font-medium uppercase tracking-wider truncate text-slate-400" title={title}>
          {title}
        </span>
        {icon && <div className="text-slate-500 shrink-0">{icon}</div>}
      </div>

      <div className="flex items-baseline justify-between gap-1.5 mt-0.5">
        <div
          className={`text-base sm:text-xl font-bold font-mono tabular-nums tracking-tight truncate ${getTrendColor()}`}
          title={typeof value === 'string' ? value : String(value)}
        >
          {value}
        </div>
        {badge && (
          <span className="text-[9px] sm:text-[10px] font-semibold px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 shrink-0">
            {badge}
          </span>
        )}
      </div>

      {subValue && (
        <div className="text-[10px] sm:text-xs text-slate-500 mt-1 font-mono truncate" title={subValue}>
          {subValue}
        </div>
      )}
    </div>
  );
};
