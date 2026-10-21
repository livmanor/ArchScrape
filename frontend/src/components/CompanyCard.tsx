// frontend/src/components/CompanyCard.tsx
import React, { useState } from 'react';
import {
  ExternalLink,
  MapPin,
  Building,
  ArrowRight,
  BookmarkPlus,
  Check,
  Compass,
} from 'lucide-react';
import { SearchHit } from '../types';
import { VerificationBadge } from './VerificationBadge';

interface CompanyCardProps {
  company: SearchHit;
  onInspect: (company: SearchHit) => void;
  onSaveQuick?: (company: SearchHit) => Promise<void>;
  isAnalyzing?: boolean;
}

export const CompanyCard: React.FC<CompanyCardProps> = ({
  company,
  onInspect,
  onSaveQuick,
  isAnalyzing,
}) => {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleSave = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onSaveQuick || saved) return;
    try {
      setSaving(true);
      await onSaveQuick(company);
      setSaved(true);
    } catch (err) {
      console.error('Failed to save company', err);
    } finally {
      setSaving(false);
    }
  };

  const domain = company.domain || (company.url ? new URL(company.url).hostname : '');
  const isVerified = company.verification_status === 'verified';
  const isCandidate = company.verification_status === 'candidate';

  return (
    <div className="bg-white rounded-xl border border-slate-200 hover:border-slate-300 shadow-xs hover:shadow-md transition p-5 flex flex-col justify-between">
      {/* Top Header Row */}
      <div>
        <div className="flex items-start justify-between gap-3 mb-2.5">
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-slate-900 truncate">
              {company.name}
            </h3>
            {/* Meta Tags */}
            <div className="flex flex-wrap items-center gap-2 mt-1">
              {company.city && (
                <span className="inline-flex items-center text-xs text-slate-500 font-medium">
                  <MapPin className="h-3 w-3 mr-1 text-slate-400" />
                  {company.city}
                </span>
              )}
              {company.category && (
                <span className="inline-flex items-center text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium capitalize">
                  <Building className="h-2.5 w-2.5 mr-1 text-slate-400" />
                  {company.category}
                </span>
              )}
            </div>
          </div>

          {/* Verification Badge */}
          <VerificationBadge
            status={company.verification_status || (company.verified ? 'verified' : 'candidate')}
            size="sm"
          />
        </div>

        {/* Website & Domain Row */}
        <div className="mb-3">
          {isVerified && company.url ? (
            <a
              href={company.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center text-xs font-semibold text-emerald-700 hover:text-emerald-800 hover:underline"
            >
              <span>{domain || company.url}</span>
              <ExternalLink className="h-3 w-3 ml-1" />
            </a>
          ) : isCandidate && (company.url || company.domain) ? (
            <div className="flex items-center space-x-1.5 text-xs text-amber-700">
              <span className="font-mono text-[11px] bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200 truncate max-w-[240px]">
                {company.url || `https://${company.domain}`}
              </span>
              <span className="text-[11px] text-amber-600 italic">
                (Candidate domain)
              </span>
            </div>
          ) : (
            <span className="text-xs text-slate-400 italic">
              No official website identified
            </span>
          )}
        </div>

        {/* Snippet / Description */}
        {company.snippet && (
          <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed mb-4">
            {company.snippet}
          </p>
        )}
      </div>

      {/* Action Footer */}
      <div className="pt-3 border-t border-slate-100 flex items-center justify-between gap-2 mt-auto">
        <div className="text-[11px] text-slate-400 flex items-center">
          <Compass className="h-3 w-3 mr-1 text-slate-400" />
          <span>
            {company.source === 'firecrawl'
              ? 'Firecrawl Live'
              : 'Curated Registry'}
          </span>
        </div>

        <div className="flex items-center space-x-2">
          {onSaveQuick && (
            <button
              type="button"
              onClick={handleSave}
              disabled={saved || saving}
              className={`p-2 rounded-lg text-xs font-medium border transition flex items-center ${
                saved
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-white hover:bg-slate-50 text-slate-600 border-slate-200'
              }`}
              title={saved ? 'Saved to leads' : 'Quick save to leads'}
            >
              {saved ? (
                <Check className="h-3.5 w-3.5 text-emerald-600" />
              ) : (
                <BookmarkPlus className="h-3.5 w-3.5" />
              )}
            </button>
          )}

          <button
            type="button"
            onClick={() => onInspect(company)}
            disabled={isAnalyzing}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 text-white hover:bg-indigo-600 transition flex items-center space-x-1 shadow-xs"
          >
            <span>Deep Crawl & Extract</span>
            <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
};
