import React from 'react';
import { Building2, Globe2, BookOpen, Sparkles } from 'lucide-react';
import type { HealthResponse } from '../types';

interface NavbarProps {
  activeTab: 'landing' | 'search' | 'directory';
  onTabChange: (tab: 'landing' | 'search' | 'directory') => void;
  health?: HealthResponse | null;
  savedCount: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  savedCount,
}) => {
  return (
    <header className="sticky top-0 z-30 bg-[#070b14]/90 border-b border-slate-800/80 backdrop-blur-md shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Brand */}
          <div
            onClick={() => onTabChange('landing')}
            className="flex items-center space-x-3 cursor-pointer group"
          >
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center text-white shadow-md shadow-indigo-600/30 group-hover:scale-105 transition-transform">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-lg sm:text-xl font-bold tracking-tight text-white font-heading">
                  ArchGuild <span className="text-indigo-400">Scrape</span>
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800/60 hidden sm:inline-block">
                  v2.0
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">
                Places · Firecrawl · OpenRouter Engine
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex space-x-1 sm:space-x-2">
            <button
              onClick={() => onTabChange('landing')}
              className={`px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-all flex items-center space-x-1.5 cursor-pointer ${
                activeTab === 'landing'
                  ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/40 shadow-inner'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Sparkles className="h-4 w-4" />
              <span>Overview</span>
            </button>

            <button
              onClick={() => onTabChange('search')}
              className={`px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-all flex items-center space-x-1.5 cursor-pointer ${
                activeTab === 'search'
                  ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/40 shadow-inner'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Globe2 className="h-4 w-4" />
              <span>Practice Finder</span>
            </button>

            <button
              onClick={() => onTabChange('directory')}
              className={`px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-all flex items-center space-x-1.5 cursor-pointer ${
                activeTab === 'directory'
                  ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/40 shadow-inner'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <BookOpen className="h-4 w-4" />
              <span>Saved Leads</span>
              <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-slate-800 text-indigo-300 font-mono font-bold border border-slate-700">
                {savedCount}
              </span>
            </button>
          </nav>
        </div>
      </div>
    </header>
  );
};
