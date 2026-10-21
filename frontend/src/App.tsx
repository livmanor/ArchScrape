// frontend/src/App.tsx
import React, { useState, useEffect } from 'react';
import {
  Globe2,
  Building,
  CheckCircle,
  AlertCircle,
  FileSearch,
  Sparkles,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react';
import {
  HealthResponse,
  PresetsResponse,
  SearchHit,
  CompanyLead,
  SavedCompanyLead,
} from './types';
import {
  getHealth,
  getPresets,
  searchCompanies,
  analyzeCompany,
  getSavedCompanies,
  saveLead,
} from './services/api';
import { Navbar } from './components/Navbar';
import { SearchBar } from './components/SearchBar';
import { CompanyCard } from './components/CompanyCard';
import { CompanyDetailsModal } from './components/CompanyDetailsModal';
import { SavedDirectoryTable } from './components/SavedDirectoryTable';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'search' | 'directory'>('search');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [presets, setPresets] = useState<PresetsResponse | null>(null);

  // Search screen states
  const [searchResults, setSearchResults] = useState<SearchHit[]>([]);
  const [searchSource, setSearchSource] = useState<'firecrawl' | 'local_directory' | null>(null);
  const [searchMeta, setSearchMeta] = useState<{ query: string; city: string; count: number } | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Deep Crawl & Modal states
  const [selectedLead, setSelectedLead] = useState<CompanyLead | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // Directory screen states
  const [savedCompanies, setSavedCompanies] = useState<SavedCompanyLead[]>([]);
  const [savedTotal, setSavedTotal] = useState(0);
  const [isLoadingSaved, setIsLoadingSaved] = useState(false);

  // Initial load
  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    try {
      const [healthData, presetsData] = await Promise.all([
        getHealth().catch(() => null),
        getPresets().catch(() => null),
      ]);
      if (healthData) setHealth(healthData);
      if (presetsData) setPresets(presetsData);

      loadSavedDirectory({});
    } catch (err) {
      console.error('Initialization error:', err);
    }
  };

  const loadSavedDirectory = async (filters: {
    search?: string;
    city?: string;
    category?: string;
    status?: string;
  }) => {
    try {
      setIsLoadingSaved(true);
      const res = await getSavedCompanies({
        search: filters.search,
        city: filters.city,
        category: filters.category,
        status: filters.status,
        limit: 100,
      });
      if (res && res.companies) {
        setSavedCompanies(res.companies);
        setSavedTotal(res.total);
      }
    } catch (err) {
      console.error('Failed to load saved directory:', err);
    } finally {
      setIsLoadingSaved(false);
    }
  };

  // Screen A: Handle Search
  const handleSearch = async (params: {
    query: string;
    city: string;
    category: string;
    live: boolean;
  }) => {
    try {
      setIsSearching(true);
      setSearchError(null);
      const res = await searchCompanies(
        params.query,
        params.city,
        params.category,
        params.live
      );

      setSearchResults(res.results || []);
      setSearchSource(res.source);
      setSearchMeta({
        query: params.query || 'All firms',
        city: params.city || 'All locations',
        count: res.count || 0,
      });
    } catch (err: any) {
      setSearchError(err.message || 'Discovery search failed.');
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  // Screen B -> Screen C: Deep Crawl & Inspect Company
  const handleInspectCompany = async (company: SearchHit) => {
    try {
      setIsAnalyzing(true);
      setAnalysisError(null);

      // Target can be URL or domain or name
      const target = company.url || company.domain || company.name;
      const category = company.category || 'architecture';

      const lead = await analyzeCompany(target, category, true);
      setSelectedLead(lead);
      setIsModalOpen(true);
    } catch (err: any) {
      setAnalysisError(`Crawling error for ${company.name}: ${err.message}`);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Quick save from Search Result Card
  const handleQuickSave = async (company: SearchHit) => {
    const leadToSave: CompanyLead = {
      company_name: company.name,
      website: company.url || (company.domain ? `https://${company.domain}` : ''),
      verification_status: company.verified ? 'Verified' : 'Needs Review',
      city: company.city || '',
      description: company.snippet || '',
      source_urls: company.url ? [company.url] : [],
    };
    await saveLead(leadToSave, company.category || 'architecture');
    loadSavedDirectory({});
  };

  // Save from Modal
  const handleSaveFromModal = async (lead: CompanyLead) => {
    await saveLead(lead, 'architecture');
    loadSavedDirectory({});
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900 font-sans">
      {/* Top Navbar */}
      <Navbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        health={health}
        savedCount={savedTotal}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Error Banners */}
        {analysisError && (
          <div className="mb-6 p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <AlertCircle className="h-4 w-4 text-amber-600 shrink-0" />
              <span>{analysisError}</span>
            </div>
            <button
              onClick={() => setAnalysisError(null)}
              className="text-amber-600 hover:text-amber-800 font-bold ml-4"
            >
              ✕
            </button>
          </div>
        )}

        {/* Tab 1: Discover Companies (Screen A & Screen B) */}
        {activeTab === 'search' && (
          <div>
            {/* Screen A: Search & Presets */}
            <div className="mb-6">
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 mb-1">
                Company Discovery & Verification
              </h1>
              <p className="text-sm text-slate-500">
                Discover architecture firms, interior studios, and design practices with real-time domain verification and structured intelligence.
              </p>
            </div>

            <SearchBar
              onSearch={handleSearch}
              isLoading={isSearching}
              presets={presets}
              firecrawlAvailable={Boolean(health?.firecrawl_available)}
            />

            {/* Screen B: Search Results */}
            {searchError && (
              <div className="p-6 rounded-xl bg-red-50 border border-red-200 text-sm text-red-800 mb-6">
                <div className="font-semibold mb-1">Search Execution Error</div>
                <div>{searchError}</div>
              </div>
            )}

            {searchMeta && !isSearching && (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4 px-1">
                <div className="flex items-center space-x-2 text-sm text-slate-700">
                  <span className="font-semibold text-slate-900">
                    {searchMeta.count} companies found
                  </span>
                  <span className="text-slate-400">•</span>
                  <span>Query: &ldquo;{searchMeta.query}&rdquo;</span>
                  {searchMeta.city !== 'All' && (
                    <>
                      <span className="text-slate-400">•</span>
                      <span>Location: {searchMeta.city}</span>
                    </>
                  )}
                </div>

                <div className="text-xs text-slate-500 flex items-center space-x-1.5">
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                  <span>
                    Source:{' '}
                    <strong>
                      {searchSource === 'firecrawl'
                        ? '🔥 Firecrawl Live Web Search'
                        : '🗄️ Curated Registry Directory'}
                    </strong>
                  </span>
                </div>
              </div>
            )}

            {/* Results Grid */}
            {isSearching ? (
              <div className="p-16 text-center bg-white rounded-xl border border-slate-200">
                <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-indigo-600 border-r-transparent mb-3" />
                <h3 className="text-sm font-semibold text-slate-900 mb-1">
                  Discovering candidate companies...
                </h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Searching public web registries, querying domain records, and resolving candidate official websites.
                </p>
              </div>
            ) : searchResults.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {searchResults.map((company, idx) => (
                  <CompanyCard
                    key={`${company.name}-${idx}`}
                    company={company}
                    onInspect={handleInspectCompany}
                    onSaveQuick={handleQuickSave}
                    isAnalyzing={isAnalyzing}
                  />
                ))}
              </div>
            ) : searchMeta ? (
              <div className="p-12 text-center bg-white rounded-xl border border-slate-200">
                <FileSearch className="h-10 w-10 text-slate-300 mx-auto mb-3" />
                <h3 className="text-sm font-semibold text-slate-800 mb-1">
                  No companies found for this query
                </h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Try broadening your search keywords or switching locations.
                </p>
              </div>
            ) : (
              /* Initial State: Featured Suggestions */
              <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
                <div className="h-12 w-12 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-4">
                  <Globe2 className="h-6 w-6" />
                </div>
                <h3 className="text-base font-semibold text-slate-900 mb-1">
                  Ready to discover design practices
                </h3>
                <p className="text-xs text-slate-500 max-w-md mx-auto mb-6">
                  Use the search bar above to query by practice name, discipline, or city, or select one of the suggested sample practices below.
                </p>

                {presets?.sample_companies && (
                  <div className="max-w-2xl mx-auto text-left">
                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                      Featured Pre-Validated Practices
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {presets.sample_companies.map((s, idx) => (
                        <button
                          key={idx}
                          onClick={() =>
                            handleInspectCompany({
                              name: s.name,
                              domain: s.domain,
                              url: `https://${s.domain}`,
                              city: s.city,
                              category: 'architecture',
                              verified: true,
                              verification_status: 'verified',
                            })
                          }
                          className="p-3 rounded-lg border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/40 text-left transition flex items-center justify-between group"
                        >
                          <div>
                            <div className="text-xs font-semibold text-slate-900 group-hover:text-indigo-600">
                              {s.name}
                            </div>
                            <div className="text-[11px] text-slate-400">
                              {s.city} • {s.domain}
                            </div>
                          </div>
                          <ArrowRight className="h-4 w-4 text-slate-300 group-hover:text-indigo-600 transition" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Saved Leads Directory */}
        {activeTab === 'directory' && (
          <div>
            <div className="mb-6">
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 mb-1">
                Saved Leads Directory
              </h1>
              <p className="text-sm text-slate-500">
                Explore confirmed company leads, verified executive leadership, contact channels, and field-level evidence stored in SQLite.
              </p>
            </div>

            <SavedDirectoryTable
              companies={savedCompanies}
              total={savedTotal}
              isLoading={isLoadingSaved}
              presets={presets}
              onRefresh={loadSavedDirectory}
              onInspectLead={(lead) => {
                setSelectedLead(lead);
                setIsModalOpen(true);
              }}
            />
          </div>
        )}
      </main>

      {/* Screen C: Company Details Modal with Diagnostics */}
      <CompanyDetailsModal
        lead={selectedLead}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSaveLead={handleSaveFromModal}
      />
    </div>
  );
};
export default App;
