import React from 'react';

interface StatCardProps {
  title: string;
  value: string | number;
  subValue?: string;
  icon?: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  badge?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subValue,
  icon,
  trend,
  badge,
}) => {
  const getTrendColor = () => {
    if (trend === 'up') return 'text-emerald-400';
    if (trend === 'down') return 'text-rose-500';
    return 'text-white';
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 flex flex-col justify-between hover:border-gray-700 transition-colors">
      <div className="flex items-center justify-between text-gray-400 mb-2">
        <span className="text-xs font-medium uppercase tracking-wider">{title}</span>
        {icon && <div className="text-gray-400">{icon}</div>}
      </div>

      <div className="flex items-baseline justify-between mt-1">
        <div className={`text-xl font-bold font-mono ${getTrendColor()}`}>{value}</div>
        {badge && (
          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/30">
            {badge}
          </span>
        )}
      </div>

      {subValue && <div className="text-xs text-gray-500 mt-1 font-mono">{subValue}</div>}
    </div>
  );
};
