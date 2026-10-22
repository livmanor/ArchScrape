import type {
  HealthResponse,
  PresetsResponse,
  SearchResponse,
  CompanyLead,
  SavedCompanyLead,
} from '../types';

const API_BASE = '/api';

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) {
    throw new Error(`Health check failed with HTTP ${res.status}`);
  }
  return res.json();
}

export async function getPresets(): Promise<PresetsResponse> {
  const res = await fetch(`${API_BASE}/presets`);
  if (!res.ok) {
    throw new Error(`Failed to load presets: ${res.statusText}`);
  }
  return res.json();
}

export async function searchCompanies(
  query: string,
  city?: string,
  category?: string,
  live: boolean = true
): Promise<SearchResponse> {
  const params = new URLSearchParams();
  if (query) params.append('q', query);
  if (city && city !== 'All') params.append('city', city);
  if (category && category !== 'all') params.append('category', category);
  params.append('live', String(live));

  const res = await fetch(`${API_BASE}/search?${params.toString()}`);
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Search failed with HTTP ${res.status}`);
  }
  return res.json();
}

export async function analyzeCompany(
  target: string,
  category: string = 'architecture',
  deep: boolean = true
): Promise<CompanyLead> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target, category, deep }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Analysis failed with HTTP ${res.status}`);
  }
  return res.json();
}

export async function getSavedCompanies(params: {
  search?: string;
  city?: string;
  category?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<{ ok: boolean; total: number; limit: number; offset: number; companies: SavedCompanyLead[] }> {
  const query = new URLSearchParams();
  if (params.search) query.append('search', params.search);
  if (params.city && params.city !== 'All') query.append('city', params.city);
  if (params.category && params.category !== 'all') query.append('category', params.category);
  if (params.status && params.status !== 'All') query.append('status', params.status);
  if (params.limit) query.append('limit', String(params.limit));
  if (params.offset) query.append('offset', String(params.offset));

  const res = await fetch(`${API_BASE}/companies?${query.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch saved companies: HTTP ${res.status}`);
  }
  return res.json();
}

export async function getCompanyDetail(companyId: number): Promise<{
  ok: boolean;
  company: any;
  evidence: Array<{
    id: number;
    field_name: string;
    extracted_value: string;
    source_url: string;
    context_text: string;
    verification_status: string;
    is_primary: boolean;
  }>;
}> {
  const res = await fetch(`${API_BASE}/companies/${companyId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch company details: HTTP ${res.status}`);
  }
  return res.json();
}

export async function saveLead(lead: CompanyLead, category: string = 'architecture'): Promise<{ ok: boolean; company_id: number; message: string }> {
  const res = await fetch(`${API_BASE}/leads/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      company_name: lead.company_name,
      website: lead.website,
      category,
      city: lead.city || '',
      owner_name: lead.owner_name || '',
      designation: lead.designation || '',
      org_size: lead.org_size || '',
      email: lead.email || '',
      phone: lead.phone || '',
      social_links: lead.social_links || {},
      services: lead.services || [],
      description: lead.description || '',
      source_urls: lead.source_urls || [],
      field_evidence: lead.field_evidence || [],
    }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Save failed: HTTP ${res.status}`);
  }
  return res.json();
}

export function getExportUrl(search?: string, city?: string, category?: string, status?: string): string {
  const params = new URLSearchParams();
  if (search) params.append('search', search);
  if (city && city !== 'All') params.append('city', city);
  if (category && category !== 'all') params.append('category', category);
  if (status && status !== 'All') params.append('status', status);
  return `${API_BASE}/export?${params.toString()}`;
}

export async function lookupCompany(name: string, refresh: boolean = false): Promise<any> {
  const res = await fetch(`${API_BASE}/lookup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, refresh }),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Lookup failed with HTTP ${res.status}`);
  }
  return res.json();
}

