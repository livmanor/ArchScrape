// frontend/src/types/index.ts

export type VerificationStatus =
  | 'verified'
  | 'candidate'
  | 'needs_review'
  | 'not_found';

export interface SearchHit {
  name: string;
  domain?: string;
  url?: string;
  city?: string;
  category?: string;
  snippet?: string;
  source?: 'firecrawl' | 'curated_seed' | string;
  verified?: boolean;
  verification_status?: 'verified' | 'candidate' | 'not_found';
}

export interface FieldEvidence {
  field_name: string;
  extracted_value: string;
  verification_status: string;
  source_url?: string;
  context_text?: string;
}

export interface ResolutionInfo {
  resolution_source?: string;
  original_url?: string;
  verified_url?: string;
  pages_scraped?: string[];
  verification_notes?: string[];
  scrape_errors?: string[];
}

export interface CompanyLead {
  company_name: string;
  website: string;
  verification_status: string;
  verification_score?: number;
  city?: string;
  owner_name?: string;
  designation?: string;
  org_size?: string;
  email?: string;
  phone?: string;
  social_links?: Record<string, string>;
  services?: string[];
  description?: string;
  source_urls?: string[];
  resolution_info?: ResolutionInfo;
  field_evidence?: FieldEvidence[];
}

export interface SavedCompanyLead {
  id: number;
  organisation: string;
  owner_name: string;
  designation: string;
  org_size: string;
  mobile: string;
  email: string;
  city: string;
  website?: string;
  domain_key?: string;
  category?: string;
  source_urls?: string;
  source_urls_list?: string[];
  social_links?: Record<string, string>;
  social_links_str?: string;
  owner_status?: string;
  email_status?: string;
  mobile_status?: string;
  city_status?: string;
  org_size_basis?: string;
}

export interface HealthResponse {
  status: string;
  database_connected: boolean;
  firecrawl_available: boolean;
  metrics: {
    total_companies: number;
    total_evidence: number;
    needs_review: number;
    not_found: number;
    last_run?: {
      started_at: string;
      status: string;
    } | null;
    errors_last_run: number;
  };
}

export interface PresetsResponse {
  cities: string[];
  categories: Array<{ id: string; label: string }>;
  quick_searches: Array<{
    label: string;
    query: string;
    city: string;
    category: string;
  }>;
  sample_companies: Array<{
    name: string;
    city: string;
    domain: string;
  }>;
}

export interface SearchResponse {
  ok: boolean;
  query: string;
  city: string;
  source: 'firecrawl' | 'local_directory';
  count: number;
  results: SearchHit[];
  warnings?: string[];
}
