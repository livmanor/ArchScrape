import React from 'react';
import { Building2, Globe2, BookOpen } from 'lucide-react';
import type { HealthResponse } from '../types';

interface NavbarProps {
  activeTab: 'search' | 'directory';
  onTabChange: (tab: 'search' | 'directory') => void;
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
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm">
              <Building2 className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xl font-bold tracking-tight text-slate-900">
                  ArchScrape
                </span>
              </div>
              <p className="text-xs text-slate-500 hidden sm:block">
                Company Discovery & Verified Intelligence
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex space-x-1 sm:space-x-2">
            <button
              onClick={() => onTabChange('search')}
              className={`px-3.5 py-2 rounded-md text-sm font-medium transition-colors flex items-center space-x-1.5 ${
                activeTab === 'search'
                  ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <Globe2 className="h-4 w-4" />
              <span>Discover Companies</span>
            </button>

            <button
              onClick={() => onTabChange('directory')}
              className={`px-3.5 py-2 rounded-md text-sm font-medium transition-colors flex items-center space-x-1.5 ${
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
