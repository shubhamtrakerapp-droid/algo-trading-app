import React from 'react';
import {
  Activity,
  Brain,
  BarChart2,
  TrendingUp,
  Menu,
} from 'lucide-react';

interface BottomNavProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  onToggleMore: () => void;
  hasActivePosition?: boolean;
}

export const BottomNav: React.FC<BottomNavProps> = ({
  activeTab,
  setActiveTab,
  onToggleMore,
  hasActivePosition = false,
}) => {
  const primaryTabs = [
    { id: 'dashboard', label: 'Dashboard', icon: Activity },
    { id: 'ai-micro-scalper', label: 'AI Scalper', icon: Brain },
    { id: 'chart', label: 'Charts', icon: BarChart2 },
    {
      id: 'open-positions',
      label: 'Positions',
      icon: TrendingUp,
      hasDot: hasActivePosition,
    },
  ];

  const isMoreActive = !primaryTabs.some((t) => t.id === activeTab);

  return (
    <nav
      aria-label="Mobile navigation bar"
      className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-slate-900/95 backdrop-blur-lg border-t border-slate-800 shadow-2xl select-none"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
    >
      <div className="flex items-center justify-around h-16 px-1">
        {primaryTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex flex-col items-center justify-center h-full min-w-0 py-1 transition-all relative ${
                isActive
                  ? 'text-emerald-400 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <div className="relative">
                <Icon
                  className={`w-5 h-5 transition-transform ${
                    isActive ? 'scale-110 text-emerald-400' : 'text-slate-400'
                  }`}
                />
                {tab.hasDot && (
                  <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-emerald-400 ring-2 ring-slate-900 animate-pulse" />
                )}
              </div>
              <span className="text-[10px] mt-1 font-mono tracking-tight truncate max-w-[64px]">
                {tab.label}
              </span>
              {isActive && (
                <span className="absolute top-0 w-8 h-0.5 rounded-full bg-emerald-400" />
              )}
            </button>
          );
        })}

        {/* More Menu Drawer Trigger */}
        <button
          onClick={onToggleMore}
          aria-label="Open full menu"
          className={`flex-1 flex flex-col items-center justify-center h-full min-w-0 py-1 transition-all relative ${
            isMoreActive
              ? 'text-indigo-400 font-bold'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <div className="relative">
            <Menu
              className={`w-5 h-5 transition-transform ${
                isMoreActive ? 'scale-110 text-indigo-400' : 'text-slate-400'
              }`}
            />
          </div>
          <span className="text-[10px] mt-1 font-mono tracking-tight truncate max-w-[64px]">
            More
          </span>
          {isMoreActive && (
            <span className="absolute top-0 w-8 h-0.5 rounded-full bg-indigo-400" />
          )}
        </button>
      </div>
    </nav>
  );
};
