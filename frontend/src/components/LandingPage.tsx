import React, { useState } from 'react';
import {
  Building2,
  Sparkles,
  ShieldCheck,
  Search,
  CheckCircle2,
  XCircle,
  ArrowRight,
  Globe2,
  Users,
  MapPin,
  Mail,
  Phone,
  Share2,
  Cpu,
  Layers,
  Terminal,
  ExternalLink,
  ChevronRight,
  AlertTriangle,
} from 'lucide-react';
import { lookupCompany } from '../services/api';

interface LandingPageProps {
  onExploreFinder: () => void;
  onOpenDirectory: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onExploreFinder,
  onOpenDirectory,
}) => {
  const [lookupQuery, setLookupQuery] = useState('Archscale Guild');
  const [isLookingUp, setIsLookingUp] = useState(false);
  const [lookupResult, setLookupResult] = useState<any | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState<number>(0);

  const samplePresets = [
    { label: 'Archscale Guild', query: 'Archscale Guild' },
    { label: 'Design Cafe', query: 'design cafe' },
    { label: 'Morphogenesis', query: 'morphogenesis' },
    { label: 'Architecture Discipline', query: 'architecture discipline' },
  ];

  const handleTestLookup = async (queryToRun?: string) => {
    const q = (queryToRun || lookupQuery).trim();
    if (!q) return;

    setLookupQuery(q);
    setIsLookingUp(true);
    setLookupError(null);
    setLookupResult(null);
    setActiveStep(1);

    try {
      // Step simulation for visual feedback
      const timer1 = setTimeout(() => setActiveStep(2), 600);
      const timer2 = setTimeout(() => setActiveStep(3), 1400);

      const res = await lookupCompany(q, true);

      clearTimeout(timer1);
      clearTimeout(timer2);
      setActiveStep(4);
      setLookupResult(res);
    } catch (err: any) {
      setLookupError(err.message || 'Lookup failed');
    } finally {
      setIsLookingUp(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#070b14] text-slate-100 selection:bg-indigo-500 selection:text-white">
      {/* ─── Hero Glow Effects ────────────────────────────────────────── */}
      <div className="relative overflow-hidden pt-12 pb-24 md:pt-20 md:pb-32">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl h-[500px] pointer-events-none">
          <div className="absolute top-10 left-1/4 w-96 h-96 bg-indigo-600/20 rounded-full blur-3xl animate-pulse-glow" />
          <div className="absolute top-20 right-1/4 w-96 h-96 bg-cyan-500/15 rounded-full blur-3xl animate-pulse-glow" style={{ animationDelay: '3s' }} />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Top Pill */}
          <div className="flex justify-center mb-6">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 backdrop-blur-md text-xs font-medium text-indigo-300 shadow-inner">
              <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
              <span>ArchGuild Scrape 2.0 • Powered by Google Places, Firecrawl & OpenRouter</span>
            </div>
          </div>

          {/* Main Hero Header */}
          <div className="text-center max-w-4xl mx-auto">
            <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-white leading-[1.1] mb-6">
              The <span className="bg-gradient-to-r from-indigo-400 via-sky-300 to-teal-300 bg-clip-text text-transparent">Zero-Noise</span> Intelligence Engine for Design Practices
            </h1>
            <p className="text-lg sm:text-xl text-slate-400 leading-relaxed max-w-2xl mx-auto mb-10">
              Stop settling for broken aggregator links and hallucinated agency leaders. ArchGuild Scrape verifies physical businesses, deep-crawls team subpages, and extracts verbatim-verified CEOs and authentic socials.
            </p>

            {/* CTAs */}
            <div className="flex flex-wrap items-center justify-center gap-4 mb-16">
              <button
                onClick={onExploreFinder}
                className="px-6 py-3.5 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white font-semibold shadow-lg shadow-indigo-600/30 transition-all flex items-center gap-2 group cursor-pointer"
              >
                <span>Launch Practice Finder</span>
                <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
              </button>

              <button
                onClick={onOpenDirectory}
                className="px-6 py-3.5 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700/80 text-slate-200 font-semibold transition-all flex items-center gap-2 cursor-pointer backdrop-blur-sm"
              >
                <Layers className="h-4 w-4 text-slate-400" />
                <span>Saved SQLite Directory</span>
              </button>
            </div>
          </div>

          {/* ─── Interactive Live Lookup Widget ─────────────────────────── */}
          <div className="max-w-4xl mx-auto">
            <div className="relative rounded-2xl border border-slate-800 bg-slate-900/90 shadow-2xl backdrop-blur-xl p-5 sm:p-7">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-4 mb-5">
                <div className="flex items-center gap-2.5">
                  <div className="flex gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-red-500/80" />
                    <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
                    <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
                  </div>
                  <span className="text-xs font-mono text-slate-400 ml-2 flex items-center gap-1.5">
                    <Terminal className="h-3.5 w-3.5 text-indigo-400" />
                    archguild-lookup-pipeline :: live runner
                  </span>
                </div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded-md">
                  Active Endpoint: /api/lookup
                </span>
              </div>

              {/* Input Bar */}
              <div className="flex flex-col sm:flex-row gap-3 mb-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-400" />
                  <input
                    type="text"
                    value={lookupQuery}
                    onChange={(e) => setLookupQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleTestLookup()}
                    placeholder="Enter practice name (e.g. Archscale Guild, Design Cafe)"
                    className="w-full pl-10 pr-4 py-3 bg-slate-950/90 border border-slate-800 rounded-xl text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
                  />
                </div>
                <button
                  onClick={() => handleTestLookup()}
                  disabled={isLookingUp}
                  className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition flex items-center justify-center gap-2 shadow-md cursor-pointer flex-shrink-0"
                >
                  {isLookingUp ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      <span>Inspecting...</span>
                    </>
                  ) : (
                    <>
                      <Cpu className="h-4 w-4" />
                      <span>Execute Lookup</span>
                    </>
                  )}
                </button>
              </div>

              {/* Presets Chips */}
              <div className="flex flex-wrap items-center gap-2 mb-6">
                <span className="text-xs text-slate-500">Quick Test Cases:</span>
                {samplePresets.map((preset, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleTestLookup(preset.query)}
                    className="text-xs px-2.5 py-1 rounded-lg border border-slate-800 hover:border-indigo-500/50 bg-slate-950/60 hover:bg-indigo-950/30 text-slate-400 hover:text-indigo-300 transition cursor-pointer"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>

              {/* Pipeline Step Progress Visualizer */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-6">
                {[
                  { step: 1, title: 'Places Check', desc: 'Whole-word matching' },
                  { step: 2, title: 'Firecrawl /map', desc: 'Subpage discovery' },
                  { step: 3, title: 'OpenRouter AI', desc: 'Gemini 2.0 Flash' },
                  { step: 4, title: 'Verbatim Guard', desc: 'Aggregator filter' },
                ].map((item) => (
                  <div
                    key={item.step}
                    className={`p-2.5 rounded-lg border text-left transition ${
                      activeStep === item.step
                        ? 'border-indigo-500/80 bg-indigo-950/40 text-indigo-300 ring-1 ring-indigo-500/40'
                        : activeStep > item.step
                        ? 'border-emerald-500/50 bg-emerald-950/20 text-emerald-300'
                        : 'border-slate-800/80 bg-slate-950/40 text-slate-500'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 text-xs font-semibold mb-0.5">
                      {activeStep > item.step ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 flex-shrink-0" />
                      ) : (
                        <span className="w-3.5 h-3.5 rounded-full border border-current text-[9px] flex items-center justify-center">
                          {item.step}
                        </span>
                      )}
                      <span>{item.title}</span>
                    </div>
                    <div className="text-[10px] text-slate-400 pl-5">{item.desc}</div>
                  </div>
                ))}
              </div>

              {/* Lookup Result Box */}
              {lookupResult && (
                <div className="p-4 sm:p-5 rounded-xl border border-slate-800 bg-slate-950/80 text-left">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3 mb-4">
                    <div>
                      <div className="text-base font-bold text-white flex items-center gap-2">
                        <span>{lookupResult.organisation_name?.value || lookupQuery}</span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-medium ${
                            lookupResult.match_status === 'matched'
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60'
                              : lookupResult.match_status === 'ambiguous'
                              ? 'bg-amber-950 text-amber-400 border border-amber-800/60'
                              : 'bg-rose-950 text-rose-400 border border-rose-800/60'
                          }`}
                        >
                          Status: {lookupResult.match_status}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {lookupResult.city?.value && lookupResult.city.value !== 'not found' && (
                          <span className="mr-3">📍 {lookupResult.city.value} (Places addressComponents)</span>
                        )}
                        <span>Sourced via: {lookupResult.match_status === 'matched' ? 'Google Places + OpenRouter' : 'Strict Match Gate'}</span>
                      </div>
                    </div>
                  </div>

                  {/* Ambiguity Candidates Handling */}
                  {lookupResult.match_status === 'ambiguous' && lookupResult.candidates && (
                    <div className="mb-4 p-3 rounded-lg bg-amber-950/30 border border-amber-800/40 text-xs text-amber-300">
                      <div className="font-semibold flex items-center gap-1.5 mb-2">
                        <AlertTriangle className="h-4 w-4 text-amber-400" />
                        Ambiguity Detected: Multiple plausible branches exist. We never pick silently:
                      </div>
                      <div className="space-y-1.5 pl-5">
                        {lookupResult.candidates.map((cand: any, cidx: number) => (
                          <div key={cidx} className="text-slate-300">
                            • <strong>{cand.name}</strong> — {cand.address}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Core Intelligence Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs mb-3">
                    {/* CEO / Leader */}
                    <div className="p-3 rounded-lg border border-slate-800/80 bg-slate-900/60">
                      <div className="text-[11px] text-slate-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                        <Users className="h-3.5 w-3.5 text-indigo-400" />
                        Verified Executive
                      </div>
                      <div className="font-semibold text-slate-100 text-sm">
                        {lookupResult.ceo?.name?.value || 'Not stated'}
                      </div>
                      <div className="text-slate-400 text-[11px]">
                        {lookupResult.ceo?.designation?.value || 'No leader title'}
                      </div>
                      {lookupResult.ceo?.name?.source && (
                        <div className="text-[10px] text-indigo-400 mt-1 truncate">
                          src: {lookupResult.ceo.name.source}
                        </div>
                      )}
                    </div>

                    {/* Contact Channels */}
                    <div className="p-3 rounded-lg border border-slate-800/80 bg-slate-900/60">
                      <div className="text-[11px] text-slate-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                        <Mail className="h-3.5 w-3.5 text-indigo-400" />
                        Contact Channels
                      </div>
                      <div className="text-slate-200 truncate">
                        ✉️ {lookupResult.email?.value !== 'not found' ? lookupResult.email.value : 'No email'}
                      </div>
                      <div className="text-slate-200 truncate mt-0.5">
                        📞 {lookupResult.mobile?.value !== 'not found' ? lookupResult.mobile.value : 'No phone'}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1">
                        Team Size: {lookupResult.company_size?.value || 'Unstated'}
                      </div>
                    </div>

                    {/* Official Verified Socials */}
                    <div className="p-3 rounded-lg border border-slate-800/80 bg-slate-900/60">
                      <div className="text-[11px] text-slate-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                        <Share2 className="h-3.5 w-3.5 text-indigo-400" />
                        Verified Socials (Anti-Aggregator)
                      </div>
                      {lookupResult.socials && Object.keys(lookupResult.socials).length > 0 ? (
                        <div className="flex flex-wrap gap-1.5 mt-1">
                          {Object.entries(lookupResult.socials).map(([plat, sobj]: [string, any]) => (
                            <a
                              key={plat}
                              href={sobj.value}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-950/70 border border-indigo-800/60 text-[10px] text-indigo-300 hover:text-white"
                            >
                              <span>{plat}</span>
                              <ExternalLink className="h-2.5 w-2.5" />
                            </a>
                          ))}
                        </div>
                      ) : (
                        <div className="text-slate-500 text-[11px] mt-1">No verified official handles</div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Error Notice */}
              {lookupError && (
                <div className="p-4 rounded-xl border border-rose-800/50 bg-rose-950/30 text-rose-300 text-xs flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
                  <span>{lookupError}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ─── Metrics Bar ─────────────────────────────────────────────── */}
      <div className="border-y border-slate-800/80 bg-slate-950/60 backdrop-blur-md py-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            <div>
              <div className="text-3xl sm:text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-sky-300">
                100%
              </div>
              <div className="text-xs text-slate-400 mt-1 uppercase tracking-wider font-semibold">
                Verbatim Verification
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">Separate Name & Title Validation</p>
            </div>

            <div>
              <div className="text-3xl sm:text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-teal-400 to-emerald-300">
                0 Noise
              </div>
              <div className="text-xs text-slate-400 mt-1 uppercase tracking-wider font-semibold">
                Anti-Aggregator Shield
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">Blocks NoBroker, WallsToWonder, Houzz</p>
            </div>

            <div>
              <div className="text-3xl sm:text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-300">
                &lt; 3.0s
              </div>
              <div className="text-xs text-slate-400 mt-1 uppercase tracking-wider font-semibold">
                OpenRouter 2.0 Flash
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">Parallel subpage extraction</p>
            </div>

            <div>
              <div className="text-3xl sm:text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-orange-300">
                15+
              </div>
              <div className="text-xs text-slate-400 mt-1 uppercase tracking-wider font-semibold">
                Enriched Attributes
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">Stored with full source attribution</p>
            </div>
          </div>
        </div>
      </div>

      {/* ─── The 4-Pillar Pipeline Architecture ─────────────────────── */}
      <div className="py-20 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-xs font-bold uppercase tracking-widest text-indigo-400 mb-2">
            Engine Architecture
          </h2>
          <h3 className="text-3xl sm:text-4xl font-bold text-white mb-4">
            How ArchGuild Scrape Delivers Truth, Not Hallucinations
          </h3>
          <p className="text-slate-400 text-sm sm:text-base">
            Every step is mathematically bounded. If a field cannot be verified in the raw HTML or Places record, it is strictly marked "not found" with source null.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Pillar 1 */}
          <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40 hover:border-indigo-500/40 transition">
            <div className="w-12 h-12 rounded-xl bg-indigo-950/80 border border-indigo-800/60 text-indigo-400 flex items-center justify-center mb-5">
              <MapPin className="h-6 w-6" />
            </div>
            <h4 className="text-lg font-bold text-white mb-2">
              1. Google Places Whole-Word Gate
            </h4>
            <p className="text-sm text-slate-400 leading-relaxed mb-4">
              Physical existence is validated via Google Places API (New). Every searched word must match as a complete word. Misspellings and non-existent firms are dropped immediately. Multi-branch practices are flagged as ambiguous instead of silently guessed.
            </p>
            <div className="text-xs font-mono text-indigo-300 bg-indigo-950/40 p-2.5 rounded-lg border border-indigo-900/40">
              rule: city derived ONLY from addressComponents, never from search query.
            </div>
          </div>

          {/* Pillar 2 */}
          <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40 hover:border-indigo-500/40 transition">
            <div className="w-12 h-12 rounded-xl bg-sky-950/80 border border-sky-800/60 text-sky-400 flex items-center justify-center mb-5">
              <Globe2 className="h-6 w-6" />
            </div>
            <h4 className="text-lg font-bold text-white mb-2">
              2. Firecrawl Parallel Subpage Discovery
            </h4>
            <p className="text-sm text-slate-400 leading-relaxed mb-4">
              From the verified Places website, Firecrawl maps internal subpages using search terms: <code className="text-sky-300">about, team, leadership, founder, people, story, guild, management, contact</code>. The homepage and top relevant pages are scraped in parallel with 4000ms JS render wait.
            </p>
            <div className="text-xs font-mono text-sky-300 bg-sky-950/40 p-2.5 rounded-lg border border-sky-900/40">
              rule: parse JSON-LD &lt;Person&gt; and &lt;founder&gt; schema tags before LLM pass.
            </div>
          </div>

          {/* Pillar 3 */}
          <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40 hover:border-indigo-500/40 transition">
            <div className="w-12 h-12 rounded-xl bg-purple-950/80 border border-purple-800/60 text-purple-400 flex items-center justify-center mb-5">
              <Cpu className="h-6 w-6" />
            </div>
            <h4 className="text-lg font-bold text-white mb-2">
              3. OpenRouter Strict Schema Extraction
            </h4>
            <p className="text-sm text-slate-400 leading-relaxed mb-4">
              Powered by <code className="text-purple-300">google/gemini-2.0-flash-001</code> at temperature 0 with automatic retry and backoff. Page text is truncated to 30,000 characters and stripped of scripts/styles. Treated strictly as untrusted data—completely immune to prompt injection attacks.
            </p>
            <div className="text-xs font-mono text-purple-300 bg-purple-950/40 p-2.5 rounded-lg border border-purple-900/40">
              rule: output JSON only. If a detail is missing, emit null or [].
            </div>
          </div>

          {/* Pillar 4 */}
          <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/40 hover:border-indigo-500/40 transition">
            <div className="w-12 h-12 rounded-xl bg-emerald-950/80 border border-emerald-800/60 text-emerald-400 flex items-center justify-center mb-5">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <h4 className="text-lg font-bold text-white mb-2">
              4. Verbatim Guard & Anti-Aggregator Shield
            </h4>
            <p className="text-sm text-slate-400 leading-relaxed mb-4">
              Every extracted string is checked verbatim in the source text. Names and designations are verified <em>separately</em>. Leader roles are gated by executive keywords (CEO, Founder, Principal, Partner, Director). Third-party directory links (WallsToWonder, NoBroker) are discarded.
            </p>
            <div className="text-xs font-mono text-emerald-300 bg-emerald-950/40 p-2.5 rounded-lg border border-emerald-900/40">
              rule: social handles matching aggregator domains are dropped immediately.
            </div>
          </div>
        </div>
      </div>

      {/* ─── Comparison Matrix: Legacy vs ArchGuild ─────────────────── */}
      <div className="py-20 bg-slate-950/80 border-t border-slate-800">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h3 className="text-2xl sm:text-3xl font-bold text-white mb-3">
              Why Generic Web Scrapers Fail on Design Practices
            </h3>
            <p className="text-slate-400 text-sm max-w-xl mx-auto">
              Design studios have complex websites with designer credits, awards, portfolio showcases, and aggregator directory listings.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 overflow-hidden bg-slate-900/60 shadow-xl">
            <div className="grid grid-cols-2 text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-slate-800 bg-slate-900/90 px-6 py-4">
              <div>Legacy Web Scrapers</div>
              <div className="text-indigo-400 flex items-center gap-1.5">
                <Sparkles className="h-4 w-4" />
                ArchGuild Scrape Engine
              </div>
            </div>

            {[
              {
                issue: 'Aggregator Traps (e.g. Anand Nivash)',
                legacy: 'Crawls wallstowonder.com or nobroker.in, extracts directory phone and footer socials.',
                archguild: 'Aggregator Domain Guard rejects directory platforms. Verified socials only.',
              },
              {
                issue: 'Founder / CEO Discovery',
                legacy: 'Pulls random team bios or website theme authors as "Founder".',
                archguild: 'Verbatim checks name and title separately; requires CEO/Founder/Principal role keywords.',
              },
              {
                issue: 'Misspelled Searches',
                legacy: 'Guesses or autocorrects query, scraping wrong company data.',
                archguild: 'Whole-word Places match check returns "not found" — zero guessing.',
              },
              {
                issue: 'Multi-Branch Ambiguity (e.g. Design Cafe)',
                legacy: 'Silently picks the first pin regardless of city/branch.',
                archguild: 'Flags "ambiguous", stops scraping, and returns candidates list for human review.',
              },
              {
                issue: 'Hallucination & Prompt Injection',
                legacy: 'LLM extrapolates or succumbs to [SYSTEM OVERRIDE] injection.',
                archguild: 'Temperature 0, untrusted data policy, non-verbatim strings dropped and logged.',
              },
            ].map((row, idx) => (
              <div
                key={idx}
                className="grid grid-cols-2 p-6 border-b border-slate-800/80 text-sm gap-6 items-start"
              >
                <div className="flex gap-2.5 text-slate-400">
                  <XCircle className="h-4 w-4 text-rose-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <strong className="text-slate-300 block mb-0.5">{row.issue}</strong>
                    <span>{row.legacy}</span>
                  </div>
                </div>

                <div className="flex gap-2.5 text-slate-200">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <strong className="text-indigo-300 block mb-0.5">ArchGuild Precision</strong>
                    <span>{row.archguild}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── Final CTA Section ──────────────────────────────────────── */}
      <div className="py-20 relative overflow-hidden">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <div className="p-8 sm:p-12 rounded-3xl border border-indigo-500/30 bg-gradient-to-b from-indigo-950/40 to-slate-950/80 backdrop-blur-xl shadow-2xl">
            <h3 className="text-3xl sm:text-4xl font-extrabold text-white mb-4">
              Ready to Enrich Architecture & Design Leads?
            </h3>
            <p className="text-slate-400 text-sm sm:text-base max-w-xl mx-auto mb-8">
              Explore practices by city and discipline, inspect full source attribution evidence, and export confirmed leads directly to CSV.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-4">
              <button
                onClick={onExploreFinder}
                className="px-7 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl transition shadow-lg shadow-indigo-600/30 flex items-center gap-2 cursor-pointer"
              >
                <span>Launch Practice Finder</span>
                <ChevronRight className="h-4 w-4" />
              </button>
              <button
                onClick={onOpenDirectory}
                className="px-7 py-3.5 bg-slate-900 border border-slate-700 hover:border-slate-600 text-slate-300 font-semibold rounded-xl transition cursor-pointer"
              >
                <span>Browse Saved Leads</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ─── Footer ─────────────────────────────────────────────────── */}
      <footer className="border-t border-slate-900 bg-slate-950 py-8 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-slate-400">
            <Building2 className="h-4 w-4 text-indigo-400" />
            <span className="font-bold text-slate-200">ArchGuild Scrape</span>
            <span>• Architecture Intelligence & Lead Enrichment</span>
          </div>
          <div>
            Built with Google Places (New) · Firecrawl · OpenRouter 2.0 Flash · SQLite
          </div>
        </div>
      </footer>
    </div>
  );
};
