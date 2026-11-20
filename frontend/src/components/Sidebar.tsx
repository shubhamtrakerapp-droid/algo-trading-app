import React, { useEffect, useState } from 'react';
import {
  Activity,
  BarChart2,
  Layers,
  Sliders,
  DollarSign,
  TrendingUp,
  History,
  PlayCircle,
  PieChart,
  Settings as SettingsIcon,
  ChevronLeft,
  ChevronRight,
  X,
  ShieldAlert,
  Zap,
  Brain,
  Scale,
} from 'lucide-react';

export interface NavItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

export const navTabs: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: Activity },
  { id: 'ai-micro-scalper', label: 'AI Micro-Scalper', icon: Brain, badge: 'V1' },
  { id: 'chart', label: 'Live Chart', icon: BarChart2 },
  { id: 'option-chain', label: 'Option Chain', icon: Layers },
  { id: 'pcr', label: 'PCR Analysis', icon: Scale, badge: 'LIVE' },
  { id: 'strategy', label: 'Strategy', icon: Sliders },
  { id: 'paper-trading', label: 'Paper Trading', icon: DollarSign },
  { id: 'open-positions', label: 'Open Positions', icon: TrendingUp },
  { id: 'trade-history', label: 'Trade History', icon: History },
  { id: 'backtesting', label: 'Backtesting', icon: PlayCircle },
  { id: 'analytics', label: 'Analytics', icon: PieChart },
  { id: 'settings', label: 'Settings', icon: SettingsIcon },
];

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isOpenMobile: boolean;
  onCloseMobile: () => void;
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean | ((prev: boolean) => boolean)) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  isOpenMobile,
  onCloseMobile,
  isCollapsed,
  setIsCollapsed,
}) => {
  const toggleCollapse = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('nextrade_sidebar_collapsed', next ? 'true' : 'false');
      return next;
    });
  };

  const handleSelectTab = (tabId: string) => {
    setActiveTab(tabId);
    onCloseMobile();
  };

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {isOpenMobile && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40 lg:hidden transition-opacity"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 lg:static lg:z-30 flex flex-col bg-surface border-r border-border transition-all duration-250 ease-in-out shrink-0 select-none ${
          /* Desktop collapsed / expanded */
          isCollapsed ? 'lg:w-[72px]' : 'lg:w-60'
        } ${
          /* Mobile slide-out drawer */
          isOpenMobile
            ? 'w-64 translate-x-0 shadow-2xl'
            : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Sidebar Header with Toggle */}
        <div className="h-14 px-3.5 flex items-center justify-between border-b border-border/60 shrink-0">
          {/* Expanded mode title or NX Logo */}
          <div className="flex items-center space-x-2.5 overflow-hidden">
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center font-extrabold text-blue-400 shrink-0 text-sm">
              NX
            </div>
            {(!isCollapsed || isOpenMobile) && (
              <div className="flex flex-col min-w-0 transition-opacity duration-200">
                <span className="font-extrabold tracking-wider text-sm text-white truncate">NEXTRADE</span>
                <span className="text-[10px] text-gray-400 font-mono -mt-0.5 truncate">NAVIGATION</span>
              </div>
            )}
          </div>

          {/* Desktop Toggle Button */}
          <button
            onClick={toggleCollapse}
            aria-label={isCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
            title={isCollapsed ? 'Expand sidebar (Ctrl/Cmd+B)' : 'Collapse to icons only'}
            className="hidden lg:flex p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-surface/80 border border-border/50 transition-colors"
          >
            {isCollapsed ? <ChevronRight className="w-4 h-4 text-blue-400" /> : <ChevronLeft className="w-4 h-4" />}
          </button>

          {/* Mobile Close Button */}
          <button
            onClick={onCloseMobile}
            aria-label="Close mobile navigation"
            className="lg:hidden p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-surface/80"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Items List */}
        <nav className="flex-1 px-2.5 py-4 space-y-1 overflow-y-auto overflow-x-hidden scrollbar-none">
          {navTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;

            return (
              <div key={tab.id} className="relative group">
                <button
                  onClick={() => handleSelectTab(tab.id)}
                  title={isCollapsed && !isOpenMobile ? tab.label : undefined}
                  className={`w-full flex items-center rounded-xl text-xs font-semibold transition-all duration-150 ${
                    isCollapsed && !isOpenMobile
                      ? 'justify-center p-2.5'
                      : 'px-3 py-2.5 space-x-3 text-left'
                  } ${
                    isActive
                      ? 'bg-blue-600/15 text-blue-400 font-bold border border-blue-500/35 shadow-sm'
                      : 'text-gray-400 hover:text-gray-100 hover:bg-white/5 border border-transparent'
                  }`}
                >
                  <Icon
                    className={`w-4 h-4 shrink-0 transition-colors ${
                      isActive ? 'text-blue-400' : 'text-gray-400 group-hover:text-gray-200'
                    }`}
                  />

                  {/* Navigation text label: hidden in collapsed mode */}
                  {(!isCollapsed || isOpenMobile) && (
                    <span className="truncate flex-1 tracking-wide font-sans">{tab.label}</span>
                  )}

                  {/* Active Indicator Pip */}
                  {isActive && (!isCollapsed || isOpenMobile) && (
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shadow-sm shadow-blue-400 shrink-0" />
                  )}
                </button>

                {/* Hover Tooltip (Only visible in collapsed mode on desktop) */}
                {isCollapsed && !isOpenMobile && (
                  <div className="absolute left-full ml-3 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center z-50 pointer-events-none">
                    <div className="bg-popover border border-border text-white text-xs font-medium px-2.5 py-1.5 rounded-lg shadow-xl whitespace-nowrap">
                      {tab.label}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Sidebar Footer info */}
        <div className="p-3 border-t border-border/60 shrink-0 bg-surface/50">
          {(!isCollapsed || isOpenMobile) ? (
            <div className="flex items-center space-x-2 px-1 text-[11px] font-mono text-gray-400">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
              <span className="truncate">KOTAK DEMO READY</span>
            </div>
          ) : (
            <div className="flex justify-center" title="System Online">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            </div>
          )}
        </div>
      </aside>
    </>
  );
};
