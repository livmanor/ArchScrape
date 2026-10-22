import React, { useState } from 'react';
import { Search, MapPin, Tag, RefreshCw, Sparkles } from 'lucide-react';
import type { PresetsResponse } from '../types';

interface SearchBarProps {
  onSearch: (params: {
    query: string;
    city: string;
    category: string;
    live: boolean;
  }) => void;
  isLoading: boolean;
  presets: PresetsResponse | null;
  firecrawlAvailable?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  onSearch,
  isLoading,
  presets,
}) => {
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('All');
  const [category, setCategory] = useState('all');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch({ query: query.trim(), city, category, live: true });
  };

  const handleQuickSearch = (item: {
    query: string;
    city: string;
    category: string;
  }) => {
    setQuery(item.query);
    setCity(item.city);
    setCategory(item.category);
    onSearch({
      query: item.query,
      city: item.city,
      category: item.category,
      live: true,
    });
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 sm:p-6 mb-8">
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Main Input Row */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
          {/* Query Input */}
          <div className="relative md:col-span-6">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
              <Search className="h-5 w-5" />
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter company name, practice type, or keywords (e.g. interior designers)..."
              className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-300 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm transition"
            />
          </div>

          {/* City Selector */}
          <div className="relative md:col-span-3">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              <MapPin className="h-4 w-4" />
            </div>
            <select
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className="w-full pl-9 pr-8 py-2.5 rounded-lg border border-slate-300 text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm transition"
            >
              <option value="All">All Locations</option>
              {presets?.cities.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          {/* Category Selector */}
          <div className="relative md:col-span-3">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              <Tag className="h-4 w-4" />
            </div>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full pl-9 pr-8 py-2.5 rounded-lg border border-slate-300 text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm transition"
            >
              {presets?.categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Action Controls Row */}
        <div className="flex justify-end pt-2 border-t border-slate-100">
          <button
            type="submit"
            disabled={isLoading}
            className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-indigo-600 text-white font-medium text-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition shadow-sm flex items-center justify-center space-x-2 disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                <span>Discovering Companies...</span>
              </>
            ) : (
              <>
                <Search className="h-4 w-4" />
                <span>Discover Companies</span>
              </>
            )}
          </button>
        </div>

        {/* Quick Search Preset Chips */}
        {presets?.quick_searches && presets.quick_searches.length > 0 && (
          <div className="pt-2">
            <div className="flex items-center space-x-2 text-xs text-slate-500 mb-2">
              <Sparkles className="h-3.5 w-3.5 text-indigo-500" />
              <span>Suggested quick searches:</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {presets.quick_searches.map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleQuickSearch(item)}
                  className="px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 hover:bg-indigo-50 hover:text-indigo-700 hover:border-indigo-200 text-slate-700 border border-slate-200 transition"
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </form>
    </div>
  );
};
