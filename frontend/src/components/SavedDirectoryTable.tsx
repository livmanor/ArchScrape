// frontend/src/components/SavedDirectoryTable.tsx
import React, { useState } from 'react';
import {
  Download,
  Search,
  MapPin,
  ExternalLink,
  User,
  Mail,
  Phone,
  FileSpreadsheet,
  Filter,
  Eye,
} from 'lucide-react';
import type { SavedCompanyLead, PresetsResponse, CompanyLead } from '../types';
import { VerificationBadge } from './VerificationBadge';
import { getExportUrl, getCompanyDetail } from '../services/api';

interface SavedDirectoryTableProps {
  companies: SavedCompanyLead[];
  total: number;
  isLoading: boolean;
  presets: PresetsResponse | null;
  onRefresh: (filters: {
    search: string;
    city: string;
    category: string;
    status: string;
  }) => void;
  onInspectLead: (lead: CompanyLead) => void;
}

export const SavedDirectoryTable: React.FC<SavedDirectoryTableProps> = ({
  companies,
  total,
  isLoading,
  presets,
  onRefresh,
  onInspectLead,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCity, setSelectedCity] = useState('All');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('All');
  const [inspectingId, setInspectingId] = useState<number | null>(null);

  const handleFilterChange = (
    newSearch = searchTerm,
    newCity = selectedCity,
    newCategory = selectedCategory,
    newStatus = selectedStatus
  ) => {
    onRefresh({
      search: newSearch,
      city: newCity,
      category: newCategory,
      status: newStatus,
    });
  };

  const handleInspect = async (item: SavedCompanyLead) => {
    try {
      setInspectingId(item.id);
      const res = await getCompanyDetail(item.id);
      const company = res.company;
      const evidence = res.evidence || [];

      // Convert saved company and evidence into CompanyLead format
      const leadObj: CompanyLead = {
        company_name: item.organisation,
        website: item.website || (company ? company.seed_url : '') || '',
        verification_status:
          item.owner_status === 'Extracted' || item.city_status === 'Extracted'
            ? 'Verified'
            : 'Needs Review',
        city: item.city,
        owner_name: item.owner_name,
        designation: item.designation,
        org_size: item.org_size,
        email: item.email !== 'Not found' ? item.email : undefined,
        phone: item.mobile !== 'Not found' ? item.mobile : undefined,
        social_links: item.social_links || {},
        source_urls: item.source_urls_list || [],
        resolution_info: {
          original_url: item.website,
          verified_url: item.website,
          pages_scraped: item.source_urls_list || [],
          verification_notes: [
            `Persisted record #${item.id} in SQLite database`,
            `Team size basis: ${item.org_size_basis || 'default'}`,
          ],
        },
        field_evidence: evidence.map((e) => ({
          field_name: e.field_name,
          extracted_value: e.extracted_value,
          verification_status: e.verification_status,
          source_url: e.source_url,
          context_text: e.context_text,
        })),
      };

      onInspectLead(leadObj);
    } catch (err) {
      console.error('Failed to load company details', err);
    } finally {
      setInspectingId(null);
    }
  };

  const exportUrl = getExportUrl(
    searchTerm,
    selectedCity,
    selectedCategory,
    selectedStatus
  );

  return (
    <div className="space-y-4">
      {/* Top Filter & Export Bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        {/* Search & Selectors */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-2.5 flex-1">
          {/* Text search */}
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                handleFilterChange(e.target.value);
              }}
              placeholder="Filter by name, owner, or email..."
              className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-300 text-xs text-slate-900 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {/* City */}
          <div className="relative">
            <MapPin className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <select
              value={selectedCity}
              onChange={(e) => {
                setSelectedCity(e.target.value);
                handleFilterChange(undefined, e.target.value);
              }}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-slate-300 text-xs text-slate-900 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="All">All Cities</option>
              {presets?.cities.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          {/* Category */}
          <div className="relative">
            <Filter className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <select
              value={selectedCategory}
              onChange={(e) => {
                setSelectedCategory(e.target.value);
                handleFilterChange(undefined, undefined, e.target.value);
              }}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-slate-300 text-xs text-slate-900 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="all">All Disciplines</option>
              {presets?.categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          {/* Verification Status */}
          <div className="relative">
            <select
              value={selectedStatus}
              onChange={(e) => {
                setSelectedStatus(e.target.value);
                handleFilterChange(undefined, undefined, undefined, e.target.value);
              }}
              className="w-full px-3 py-1.5 rounded-lg border border-slate-300 text-xs text-slate-900 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="All">All Statuses</option>
              <option value="Extracted">Extracted</option>
              <option value="Needs Review">Needs Review</option>
              <option value="Not found">Not found</option>
            </select>
          </div>
        </div>

        {/* Export CSV Button */}
        <div className="flex items-center space-x-2 shrink-0">
          <a
            href={exportUrl}
            download="leads_export.csv"
            className="px-3.5 py-2 rounded-lg text-xs font-medium bg-slate-900 text-white hover:bg-slate-800 transition flex items-center space-x-1.5 shadow-xs"
          >
            <Download className="h-3.5 w-3.5" />
            <span>Export CSV</span>
          </a>
        </div>
      </div>

      {/* Leads Count Banner */}
      <div className="flex items-center justify-between text-xs text-slate-500 px-1">
        <span>
          Showing <strong>{companies.length}</strong> of{' '}
          <strong>{total}</strong> verified company leads
        </span>
        <span>Stored in SQLite (`data/archscale.db`)</span>
      </div>

      {/* Leads Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        {isLoading ? (
          <div className="p-12 text-center text-xs text-slate-500">
            Loading directory...
          </div>
        ) : companies.length === 0 ? (
          <div className="p-12 text-center">
            <FileSpreadsheet className="h-10 w-10 text-slate-300 mx-auto mb-3" />
            <h4 className="text-sm font-semibold text-slate-800 mb-1">
              No company leads found
            </h4>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              No saved companies match the active filters. Try searching for a
              different city or discover new companies via the Discover tab.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 text-slate-700 font-semibold uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="px-4 py-3">Company & Domain</th>
                  <th className="px-4 py-3">Executive Leader</th>
                  <th className="px-4 py-3">Location</th>
                  <th className="px-4 py-3">Contact Details</th>
                  <th className="px-4 py-3">Team</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {companies.map((c) => {
                  const hasOwner = c.owner_name && c.owner_name !== 'Not found';
                  const hasEmail = c.email && c.email !== 'Not found';
                  const hasPhone = c.mobile && c.mobile !== 'Not found';

                  return (
                    <tr key={c.id} className="hover:bg-slate-50/60 transition">
                      {/* Company & Domain */}
                      <td className="px-4 py-3">
                        <div className="font-semibold text-slate-900">
                          {c.organisation}
                        </div>
                        {c.website ? (
                          <a
                            href={c.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-500 hover:text-indigo-600 flex items-center space-x-1 text-[11px] truncate max-w-[180px] mt-0.5"
                          >
                            <span className="truncate">{c.website}</span>
                            <ExternalLink className="h-2.5 w-2.5 shrink-0" />
                          </a>
                        ) : (
                          <span className="text-slate-400 text-[11px] italic">
                            No website recorded
                          </span>
                        )}
                      </td>

                      {/* Executive Leader */}
                      <td className="px-4 py-3">
                        {hasOwner ? (
                          <div>
                            <div className="font-medium text-slate-900 flex items-center">
                              <User className="h-3 w-3 mr-1 text-slate-400" />
                              <span>{c.owner_name}</span>
                            </div>
                            {c.designation && c.designation !== 'Not found' && (
                              <div className="text-[11px] text-slate-500">
                                {c.designation}
                              </div>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-400 italic">Not found</span>
                        )}
                      </td>

                      {/* Location */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        {c.city && c.city !== 'Not found' ? (
                          <span className="inline-flex items-center text-slate-700">
                            <MapPin className="h-3 w-3 mr-1 text-slate-400" />
                            {c.city}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic">Not found</span>
                        )}
                      </td>

                      {/* Contact Details */}
                      <td className="px-4 py-3">
                        <div className="space-y-1">
                          {hasEmail ? (
                            <div className="flex items-center space-x-1 text-slate-700">
                              <Mail className="h-3 w-3 text-slate-400 shrink-0" />
                              <span className="font-mono text-[11px] truncate max-w-[160px]">
                                {c.email}
                              </span>
                            </div>
                          ) : null}
                          {hasPhone ? (
                            <div className="flex items-center space-x-1 text-slate-700">
                              <Phone className="h-3 w-3 text-slate-400 shrink-0" />
                              <span className="font-mono text-[11px] truncate max-w-[160px]">
                                {c.mobile}
                              </span>
                            </div>
                          ) : null}
                          {!hasEmail && !hasPhone && (
                            <span className="text-slate-400 italic">
                              No public contacts
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Team Size */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        {c.org_size && c.org_size !== 'Not found' ? (
                          <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[11px] font-medium">
                            {c.org_size}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic">—</span>
                        )}
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        <VerificationBadge
                          status={hasOwner ? 'verified' : 'needs review'}
                          size="sm"
                        />
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <button
                          onClick={() => handleInspect(c)}
                          disabled={inspectingId === c.id}
                          className="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition inline-flex items-center space-x-1"
                        >
                          <Eye className="h-3 w-3 mr-1" />
                          <span>
                            {inspectingId === c.id ? 'Loading...' : 'Details'}
                          </span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
