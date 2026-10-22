import React from 'react';
import {
  Building2,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  ArrowRight,
  Globe2,
  MapPin,
  Cpu,
  Layers,
  ChevronRight,
} from 'lucide-react';

interface LandingPageProps {
  onExploreFinder: () => void;
  onOpenDirectory: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onExploreFinder,
  onOpenDirectory,
}) => {
  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-800">
      {/* ─── Hero Section ────────────────────────────────────────────── */}
      <section className="relative overflow-hidden pt-16 pb-20 md:pt-24 md:pb-28 border-b border-slate-200 bg-gradient-to-b from-white via-indigo-50/20 to-[#f8fafc]">
        {/* Subtle Decorative Background Circles */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl h-full pointer-events-none overflow-hidden">
          <div className="absolute -top-24 left-1/4 w-96 h-96 bg-indigo-100/60 rounded-full blur-3xl opacity-70" />
          <div className="absolute top-12 right-1/4 w-96 h-96 bg-sky-100/60 rounded-full blur-3xl opacity-70" />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Hero Headlines */}
          <div className="text-center max-w-4xl mx-auto">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-slate-900 leading-[1.15] mb-5 font-heading">
              The <span className="text-indigo-600">Zero-Noise</span> Intelligence Engine for Design Practices
            </h1>
            <p className="text-base sm:text-lg text-slate-600 leading-relaxed max-w-2xl mx-auto mb-8">
              Stop settling for broken aggregator links and hallucinated executive names. ArchGuild Scrape verifies physical businesses, deep-crawls team subpages, and extracts verbatim-verified CEOs and authentic socials.
            </p>

            {/* CTAs */}
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={onExploreFinder}
                className="px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold shadow-sm hover:shadow transition-all flex items-center gap-2 group cursor-pointer"
              >
                <span>Launch Practice Finder</span>
                <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
              </button>

              <button
                onClick={onOpenDirectory}
                className="px-6 py-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 font-semibold shadow-xs transition-all flex items-center gap-2 cursor-pointer"
              >
                <Layers className="h-4 w-4 text-slate-500" />
                <span>Saved SQLite Directory</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Metrics Bar ─────────────────────────────────────────────── */}
      <section className="py-12 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
              <div className="text-3xl sm:text-4xl font-extrabold text-indigo-600 font-heading">
                100%
              </div>
              <div className="text-xs text-slate-700 mt-1 uppercase tracking-wider font-bold">
                Verbatim Verification
              </div>
              <p className="text-xs text-slate-500 mt-0.5">Separate Name & Title Validation</p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
              <div className="text-3xl sm:text-4xl font-extrabold text-emerald-600 font-heading">
                0 Noise
              </div>
              <div className="text-xs text-slate-700 mt-1 uppercase tracking-wider font-bold">
                Anti-Aggregator Shield
              </div>
              <p className="text-xs text-slate-500 mt-0.5">Blocks NoBroker, WallsToWonder, Houzz</p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
              <div className="text-3xl sm:text-4xl font-extrabold text-purple-600 font-heading">
                &lt; 3.0s
              </div>
              <div className="text-xs text-slate-700 mt-1 uppercase tracking-wider font-bold">
                OpenRouter 2.0 Flash
              </div>
              <p className="text-xs text-slate-500 mt-0.5">Parallel subpage extraction</p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
              <div className="text-3xl sm:text-4xl font-extrabold text-sky-600 font-heading">
                15+
              </div>
              <div className="text-xs text-slate-700 mt-1 uppercase tracking-wider font-bold">
                Enriched Attributes
              </div>
              <p className="text-xs text-slate-500 mt-0.5">Stored with full source attribution</p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── The 4-Pillar Pipeline Architecture ─────────────────────── */}
      <section className="py-16 md:py-24 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-14">
          <div className="text-xs font-bold uppercase tracking-widest text-indigo-600 mb-2">
            Engine Architecture
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold text-slate-900 mb-3 font-heading">
            How ArchGuild Scrape Delivers Truth, Not Hallucinations
          </h2>
          <p className="text-slate-600 text-sm sm:text-base">
            Every step is mathematically bounded. If a field cannot be verified in the raw HTML or Places record, it is strictly marked "not found" with source null.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Pillar 1 */}
          <div className="p-7 rounded-2xl border border-slate-200 bg-white hover:border-indigo-300 hover:shadow-md transition">
            <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mb-5">
              <MapPin className="h-6 w-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">
              1. Google Places Whole-Word Gate
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed mb-4">
              Physical existence is validated via Google Places API (New). Every searched word must match as a complete word. Misspellings and non-existent firms are dropped immediately. Multi-branch practices are flagged as ambiguous instead of silently guessed.
            </p>
            <div className="text-xs font-mono text-indigo-700 bg-indigo-50/70 p-2.5 rounded-lg border border-indigo-100">
              rule: city derived ONLY from addressComponents, never from search query.
            </div>
          </div>

          {/* Pillar 2 */}
          <div className="p-7 rounded-2xl border border-slate-200 bg-white hover:border-sky-300 hover:shadow-md transition">
            <div className="w-12 h-12 rounded-xl bg-sky-50 border border-sky-100 text-sky-600 flex items-center justify-center mb-5">
              <Globe2 className="h-6 w-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">
              2. Firecrawl Parallel Subpage Discovery
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed mb-4">
              From the verified Places website, Firecrawl maps internal subpages using search terms: <code className="text-sky-700 font-semibold">about, team, leadership, founder, people, story, guild, management, contact</code>. The homepage and top relevant pages are scraped in parallel with 4000ms JS render wait.
            </p>
            <div className="text-xs font-mono text-sky-700 bg-sky-50/70 p-2.5 rounded-lg border border-sky-100">
              rule: parse JSON-LD &lt;Person&gt; and &lt;founder&gt; schema tags before LLM pass.
            </div>
          </div>

          {/* Pillar 3 */}
          <div className="p-7 rounded-2xl border border-slate-200 bg-white hover:border-purple-300 hover:shadow-md transition">
            <div className="w-12 h-12 rounded-xl bg-purple-50 border border-purple-100 text-purple-600 flex items-center justify-center mb-5">
              <Cpu className="h-6 w-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">
              3. OpenRouter Strict Schema Extraction
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed mb-4">
              Powered by <code className="text-purple-700 font-semibold">google/gemini-2.0-flash-001</code> at temperature 0 with automatic retry and backoff. Page text is truncated to 30,000 characters and stripped of scripts/styles. Treated strictly as untrusted data—completely immune to prompt injection attacks.
            </p>
            <div className="text-xs font-mono text-purple-700 bg-purple-50/70 p-2.5 rounded-lg border border-purple-100">
              rule: output JSON only. If a detail is missing, emit null or [].
            </div>
          </div>

          {/* Pillar 4 */}
          <div className="p-7 rounded-2xl border border-slate-200 bg-white hover:border-emerald-300 hover:shadow-md transition">
            <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-100 text-emerald-600 flex items-center justify-center mb-5">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">
              4. Verbatim Guard & Anti-Aggregator Shield
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed mb-4">
              Every extracted string is checked verbatim in the source text. Names and designations are verified <em>separately</em>. Leader roles are gated by executive keywords (CEO, Founder, Principal, Partner, Director). Third-party directory links (WallsToWonder, NoBroker) are discarded.
            </p>
            <div className="text-xs font-mono text-emerald-700 bg-emerald-50/70 p-2.5 rounded-lg border border-emerald-100">
              rule: social handles matching aggregator domains are dropped immediately.
            </div>
          </div>
        </div>
      </section>

      {/* ─── Comparison Matrix: Legacy vs ArchGuild ─────────────────── */}
      <section className="py-16 md:py-24 bg-white border-t border-slate-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 mb-3 font-heading">
              Why Generic Web Scrapers Fail on Design Practices
            </h2>
            <p className="text-slate-600 text-sm max-w-xl mx-auto">
              Design studios have complex websites with designer credits, awards, portfolio showcases, and aggregator directory listings.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 overflow-hidden bg-white shadow-sm">
            <div className="grid grid-cols-2 text-xs font-bold uppercase tracking-wider text-slate-600 border-b border-slate-200 bg-slate-50 px-6 py-4">
              <div>Legacy Web Scrapers</div>
              <div className="text-indigo-600 flex items-center gap-1.5">
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
                className="grid grid-cols-2 p-6 border-b border-slate-100 text-sm gap-6 items-start hover:bg-slate-50/50 transition"
              >
                <div className="flex gap-2.5 text-slate-600">
                  <XCircle className="h-4 w-4 text-rose-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <strong className="text-slate-800 block mb-0.5 font-medium">{row.issue}</strong>
                    <span>{row.legacy}</span>
                  </div>
                </div>

                <div className="flex gap-2.5 text-slate-800">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <strong className="text-indigo-700 block mb-0.5 font-semibold">ArchGuild Precision</strong>
                    <span>{row.archguild}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Final CTA Section ──────────────────────────────────────── */}
      <section className="py-16 md:py-24 bg-[#f8fafc]">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <div className="p-8 sm:p-12 rounded-3xl border border-indigo-200 bg-gradient-to-br from-indigo-50 via-white to-white shadow-md">
            <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 mb-4 font-heading">
              Ready to Enrich Architecture & Design Leads?
            </h2>
            <p className="text-slate-600 text-sm sm:text-base max-w-xl mx-auto mb-8">
              Explore practices by city and discipline, inspect full source attribution evidence, and export confirmed leads directly to CSV.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={onExploreFinder}
                className="px-7 py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl transition shadow-sm hover:shadow flex items-center gap-2 cursor-pointer"
              >
                <span>Launch Practice Finder</span>
                <ChevronRight className="h-4 w-4" />
              </button>
              <button
                onClick={onOpenDirectory}
                className="px-7 py-3.5 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold rounded-xl transition cursor-pointer shadow-xs"
              >
                <span>Browse Saved Leads</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Footer ─────────────────────────────────────────────────── */}
      <footer className="border-t border-slate-200 bg-white py-8 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-slate-600">
            <Building2 className="h-4 w-4 text-indigo-600" />
            <span className="font-bold text-slate-900">ArchGuild Scrape</span>
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
