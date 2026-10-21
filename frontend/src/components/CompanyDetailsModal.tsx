import React, { useState } from 'react';
import {
  X,
  ExternalLink,
  MapPin,
  Mail,
  Phone,
  User,
  Users,
  BookmarkCheck,
  Check,
  Copy,
  Share2,
} from 'lucide-react';
import type { CompanyLead } from '../types';
import { VerificationBadge } from './VerificationBadge';
import { DiagnosticsPanel } from './DiagnosticsPanel';

interface CompanyDetailsModalProps {
  lead: CompanyLead | null;
  isOpen: boolean;
  onClose: () => void;
  onSaveLead: (lead: CompanyLead) => Promise<void>;
}

export const CompanyDetailsModal: React.FC<CompanyDetailsModalProps> = ({
  lead,
  isOpen,
  onClose,
  onSaveLead,
}) => {
  const [isSaved, setIsSaved] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!isOpen || !lead) return null;

  const handleSave = async () => {
    if (isSaved || isSaving) return;
    try {
      setIsSaving(true);
      await onSaveLead(lead);
      setIsSaved(true);
    } catch (err) {
      console.error('Save failed:', err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(lead, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isVerified =
    (lead.verification_status || '').toLowerCase().includes('verified') ||
    (lead.verification_status || '').toLowerCase() === 'extracted';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-900/60 backdrop-blur-xs overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-4xl my-8 overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-slate-200 flex items-start justify-between bg-slate-50/50">
          <div>
            <div className="flex items-center space-x-3 mb-1.5">
              <h2 className="text-xl font-bold text-slate-900">
                {lead.company_name}
              </h2>
              <VerificationBadge
                status={lead.verification_status}
                score={lead.verification_score}
                size="md"
              />
            </div>

            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
              {lead.city && (
                <span className="flex items-center">
                  <MapPin className="h-3.5 w-3.5 mr-1 text-slate-400" />
                  {lead.city}
                </span>
              )}
              {lead.website && (
                <a
                  href={lead.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`flex items-center font-medium ${
                    isVerified
                      ? 'text-emerald-700 hover:text-emerald-800'
                      : 'text-amber-700 hover:text-amber-800'
                  } hover:underline`}
                >
                  <span>{lead.website}</span>
                  <ExternalLink className="h-3 w-3 ml-1" />
                </a>
              )}
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleCopy}
              className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition"
              title="Copy JSON data"
            >
              {copied ? (
                <Check className="h-4 w-4 text-emerald-600" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </button>
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Modal Scrollable Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {/* Executive Leadership & Company Vitals */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* Leadership Box */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
              <div className="flex items-center space-x-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                <User className="h-3.5 w-3.5 text-indigo-600" />
                <span>Executive Leader</span>
              </div>
              <div className="text-sm font-semibold text-slate-900">
                {lead.owner_name && lead.owner_name !== 'Not found' ? (
                  lead.owner_name
                ) : (
                  <span className="text-slate-400 font-normal italic">
                    Not found on website
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">
                {lead.designation && lead.designation !== 'Not found' ? (
                  lead.designation
                ) : (
                  <span className="text-slate-400 italic">No designation extracted</span>
                )}
              </div>
            </div>

            {/* Team Size Box */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
              <div className="flex items-center space-x-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                <Users className="h-3.5 w-3.5 text-indigo-600" />
                <span>Headcount / Team</span>
              </div>
              <div className="text-sm font-semibold text-slate-900">
                {lead.org_size && lead.org_size !== 'Not found' ? (
                  `${lead.org_size} members`
                ) : (
                  <span className="text-slate-400 font-normal italic">
                    Not specified on website
                  </span>
                )}
              </div>
            </div>

            {/* Location & City Box */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
              <div className="flex items-center space-x-2 text-slate-500 text-xs font-semibold uppercase tracking-wider mb-1">
                <MapPin className="h-3.5 w-3.5 text-indigo-600" />
                <span>Operating City</span>
              </div>
              <div className="text-sm font-semibold text-slate-900">
                {lead.city && lead.city !== 'Not found' ? (
                  lead.city
                ) : (
                  <span className="text-slate-400 font-normal italic">
                    Not specified
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Contact Details & Socials */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Direct Contact */}
            <div className="p-4 rounded-xl border border-slate-200">
              <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
                Direct Contact Channels
              </h4>
              <div className="space-y-2.5 text-xs">
                <div className="flex items-center space-x-2">
                  <Mail className="h-4 w-4 text-slate-400 shrink-0" />
                  {lead.email && lead.email !== 'Not found' ? (
                    <a
                      href={`mailto:${lead.email}`}
                      className="text-indigo-600 hover:underline font-mono"
                    >
                      {lead.email}
                    </a>
                  ) : (
                    <span className="text-slate-400 italic">
                      No public email found
                    </span>
                  )}
                </div>

                <div className="flex items-center space-x-2">
                  <Phone className="h-4 w-4 text-slate-400 shrink-0" />
                  {lead.phone && lead.phone !== 'Not found' ? (
                    <span className="text-slate-800 font-mono">
                      {lead.phone}
                    </span>
                  ) : (
                    <span className="text-slate-400 italic">
                      No public telephone found
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Social Media Links */}
            <div className="p-4 rounded-xl border border-slate-200">
              <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
                Official Profiles & Socials
              </h4>
              {lead.social_links && Object.keys(lead.social_links).length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {Object.entries(lead.social_links).map(([platform, url]) => (
                    <a
                      key={platform}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 capitalize flex items-center space-x-1"
                    >
                      <Share2 className="h-3 w-3 mr-1 text-slate-400" />
                      <span>{platform}</span>
                      <ExternalLink className="h-2.5 w-2.5" />
                    </a>
                  ))}
                </div>
              ) : (
                <span className="text-xs text-slate-400 italic">
                  No social profiles verified on site
                </span>
              )}
            </div>
          </div>

          {/* Description & Overview */}
          {lead.description && (
            <div className="p-4 rounded-xl border border-slate-200">
              <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                Firm Description
              </h4>
              <p className="text-xs text-slate-700 leading-relaxed">
                {lead.description}
              </p>
            </div>
          )}

          {/* Services Offered */}
          {lead.services && lead.services.length > 0 && (
            <div className="p-4 rounded-xl border border-slate-200">
              <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                Services & Capabilities
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {lead.services.map((svc, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-100"
                  >
                    {svc}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Diagnostics Panel: Scraping Provenance & Failure Visibility */}
          <DiagnosticsPanel
            resolutionInfo={lead.resolution_info}
            fieldEvidence={lead.field_evidence}
            verifiedWebsite={lead.website}
            verificationStatus={lead.verification_status}
          />
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-slate-200 bg-slate-50/50 flex items-center justify-between">
          <div className="text-xs text-slate-500">
            {lead.source_urls && lead.source_urls.length > 0
              ? `${lead.source_urls.length} verified evidence sources`
              : 'Direct extraction'}
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
            >
              Close
            </button>

            <button
              onClick={handleSave}
              disabled={isSaved || isSaving}
              className={`px-5 py-2 rounded-lg text-xs font-medium transition flex items-center space-x-2 ${
                isSaved
                  ? 'bg-emerald-600 text-white cursor-default'
                  : 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs'
              }`}
            >
              {isSaved ? (
                <>
                  <BookmarkCheck className="h-4 w-4" />
                  <span>Saved in Leads DB</span>
                </>
              ) : isSaving ? (
                <span>Saving...</span>
              ) : (
                <>
                  <BookmarkCheck className="h-4 w-4" />
                  <span>Save to Leads Directory</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
