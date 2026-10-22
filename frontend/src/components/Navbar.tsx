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
    <header className="sticky top-0 z-30 bg-white border-b border-slate-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Brand */}
          <div
            onClick={() => onTabChange('landing')}
            className="flex items-center space-x-3 cursor-pointer group"
          >
            <div className="h-10 w-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white shadow-sm group-hover:bg-indigo-500 transition-colors">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-lg sm:text-xl font-bold tracking-tight text-slate-900 font-heading">
                  ArchGuild <span className="text-indigo-600">Scrape</span>
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 hidden sm:inline-block">
                  v2.0
                </span>
              </div>
              <p className="text-xs text-slate-500 hidden sm:block">
                Places · Firecrawl · OpenRouter Engine
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex space-x-1 sm:space-x-2">
            <button
              onClick={() => onTabChange('landing')}
              className={`px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-colors flex items-center space-x-1.5 cursor-pointer ${
                activeTab === 'landing'
                  ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <Sparkles className="h-4 w-4" />
              <span>Overview</span>
            </button>

            <button
              onClick={() => onTabChange('search')}
              className={`px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-colors flex items-center space-x-1.5 cursor-pointer ${
                activeTab === 'search'
                  ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <Globe2 className="h-4 w-4" />
              <span>Practice Finder</span>
            </button>

            <button
              onClick={() => onTabChange('directory')}
              className={`px-3 py-1.5 sm:px-3.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-colors flex items-center space-x-1.5 cursor-pointer ${
                activeTab === 'directory'
                  ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <BookOpen className="h-4 w-4" />
              <span>Saved Leads</span>
              <span className="ml-1 px-1.5 py-0.2 rounded-full text-xs bg-slate-200 text-slate-700 font-semibold">
                {savedCount}
              </span>
            </button>
          </nav>
        </div>
      </div>
    </header>
  );
};
