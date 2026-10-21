// frontend/src/components/DiagnosticsPanel.tsx
import React from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  Globe,
  FileText,
  AlertTriangle,
  ExternalLink,
  HelpCircle,
  CheckCircle,
} from 'lucide-react';
import type { ResolutionInfo, FieldEvidence } from '../types';

interface DiagnosticsPanelProps {
  resolutionInfo?: ResolutionInfo;
  fieldEvidence?: FieldEvidence[];
  verifiedWebsite?: string;
  verificationStatus?: string;
}

export const DiagnosticsPanel: React.FC<DiagnosticsPanelProps> = ({
  resolutionInfo,
  fieldEvidence = [],
  verifiedWebsite,
  verificationStatus,
}) => {
  const isVerified =
    (verificationStatus || '').toLowerCase().includes('verified') ||
    (verificationStatus || '').toLowerCase() === 'extracted';

  const pagesScraped = resolutionInfo?.pages_scraped || [];
  const errors = resolutionInfo?.scrape_errors || [];
  const notes = resolutionInfo?.verification_notes || [];

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-6">
      {/* Panel Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
        <div className="flex items-center space-x-2">
          {isVerified ? (
            <ShieldCheck className="h-5 w-5 text-emerald-600" />
          ) : (
            <ShieldAlert className="h-5 w-5 text-amber-600" />
          )}
          <h4 className="text-sm font-semibold text-slate-900">
            Scraping & Verification Diagnostics
          </h4>
        </div>
        <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-slate-200 text-slate-700">
          Source Transparency
        </span>
      </div>

      {/* Domain Verification Comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Candidate Target */}
        <div className="p-3.5 bg-white rounded-lg border border-slate-200">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
            Candidate Website / Input Target
          </span>
          <div className="text-xs font-mono text-slate-800 break-all">
            {resolutionInfo?.original_url || 'N/A (Derived directly)'}
          </div>
        </div>

        {/* Verified Official Website */}
        <div className="p-3.5 bg-white rounded-lg border border-slate-200">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1">
            Confirmed Official Domain
          </span>
          {verifiedWebsite ? (
            <a
              href={verifiedWebsite}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-mono text-emerald-700 hover:underline flex items-center space-x-1 break-all"
            >
              <span>{verifiedWebsite}</span>
              <ExternalLink className="h-3 w-3 shrink-0" />
            </a>
          ) : (
            <span className="text-xs text-amber-700 italic">
              Verification pending or no authoritative site confirmed
            </span>
          )}
        </div>
      </div>

      {/* Pages Scraped List */}
      <div>
        <div className="flex items-center space-x-1.5 text-xs font-semibold text-slate-700 mb-2">
          <FileText className="h-4 w-4 text-slate-500" />
          <span>Internal Website Pages Crawled ({pagesScraped.length})</span>
        </div>

        {pagesScraped.length > 0 ? (
          <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100 max-h-36 overflow-y-auto">
            {pagesScraped.map((page, idx) => (
              <div
                key={idx}
                className="px-3 py-1.5 flex items-center justify-between text-xs"
              >
                <span className="font-mono text-slate-700 truncate mr-2">
                  {page}
                </span>
                <a
                  href={page}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-600 hover:text-indigo-800 shrink-0 flex items-center"
                >
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-slate-500 italic bg-white p-3 rounded-lg border border-slate-200">
            Only homepage analyzed or sub-pages were unreachable.
          </div>
        )}
      </div>

      {/* Diagnostic Errors or Warnings */}
      {(errors.length > 0 || notes.length > 0) && (
        <div>
          <div className="flex items-center space-x-1.5 text-xs font-semibold text-amber-800 mb-2">
            <AlertTriangle className="h-4 w-4 text-amber-600" />
            <span>Crawler Notes & Potential Gaps</span>
          </div>
          <div className="bg-amber-50 rounded-lg border border-amber-200 p-3 space-y-1.5 text-xs text-amber-900">
            {notes.map((note, idx) => (
              <div key={`note-${idx}`} className="flex items-start space-x-1.5">
                <span className="text-amber-500">•</span>
                <span>{note}</span>
              </div>
            ))}
            {errors.map((err, idx) => (
              <div key={`err-${idx}`} className="flex items-start space-x-1.5 text-red-700">
                <span className="text-red-500">✕</span>
                <span>{err}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Field Provenance Table */}
      {fieldEvidence.length > 0 && (
        <div>
          <div className="flex items-center justify-between text-xs font-semibold text-slate-700 mb-2">
            <div className="flex items-center space-x-1.5">
              <Globe className="h-4 w-4 text-slate-500" />
              <span>Extracted Fields & Source Provenance</span>
            </div>
            <span className="text-[11px] text-slate-400">
              Click source URLs to verify directly on the website
            </span>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 font-semibold">
                <tr>
                  <th className="px-3 py-2">Field</th>
                  <th className="px-3 py-2">Extracted Value</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Source URL</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {fieldEvidence.map((ev, idx) => {
                  const isExtracted =
                    ev.extracted_value &&
                    ev.extracted_value.toLowerCase() !== 'not found' &&
                    ev.extracted_value.toLowerCase() !== 'none';

                  return (
                    <tr key={idx} className="hover:bg-slate-50/50">
                      <td className="px-3 py-2 font-medium text-slate-900 whitespace-nowrap capitalize">
                        {ev.field_name.replace('_', ' ')}
                      </td>
                      <td className="px-3 py-2 text-slate-700 max-w-xs truncate">
                        {isExtracted ? (
                          <span className="font-medium text-slate-900">
                            {ev.extracted_value}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic">
                            Not found on the website
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {isExtracted ? (
                          <span className="inline-flex items-center text-emerald-700 text-[11px] font-medium">
                            <CheckCircle className="h-3 w-3 mr-1 text-emerald-500" />
                            Extracted
                          </span>
                        ) : (
                          <span className="inline-flex items-center text-slate-400 text-[11px]">
                            <HelpCircle className="h-3 w-3 mr-1 text-slate-300" />
                            Not Found
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-500 truncate max-w-xs">
                        {ev.source_url ? (
                          <a
                            href={ev.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-indigo-600 hover:underline flex items-center space-x-1"
                            title={ev.source_url}
                          >
                            <span className="truncate max-w-[180px]">
                              {ev.source_url}
                            </span>
                            <ExternalLink className="h-3 w-3 shrink-0" />
                          </a>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
