// frontend/src/components/VerificationBadge.tsx
import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, HelpCircle } from 'lucide-react';

interface VerificationBadgeProps {
  status?: string | null;
  score?: number | null;
  size?: 'sm' | 'md';
}

export const VerificationBadge: React.FC<VerificationBadgeProps> = ({
  status,
  score,
  size = 'md',
}) => {
  const normalized = (status || '').toLowerCase().trim();

  const isVerified =
    normalized.includes('verified') ||
    normalized === 'extracted' ||
    normalized === 'confirmed';

  const isCandidate =
    normalized.includes('candidate') ||
    normalized.includes('needs review') ||
    normalized.includes('review');

  const isNotFound =
    normalized.includes('not found') ||
    normalized === 'not_found' ||
    normalized === 'missing' ||
    normalized === 'failed';

  const sizeClasses =
    size === 'sm'
      ? 'px-2 py-0.5 text-xs'
      : 'px-2.5 py-1 text-xs sm:text-sm font-medium';

  if (isVerified) {
    return (
      <span
        className={`inline-flex items-center space-x-1.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 ${sizeClasses}`}
        title="Official company website confirmed via verification rules"
      >
        <CheckCircle2 className={size === 'sm' ? 'h-3 w-3 text-emerald-600' : 'h-3.5 w-3.5 text-emerald-600'} />
        <span>Verified Official Website</span>
        {typeof score === 'number' && score > 0 && (
          <span className="opacity-75 font-mono">({Math.round(score * 100)}%)</span>
        )}
      </span>
    );
  }

  if (isCandidate) {
    return (
      <span
        className={`inline-flex items-center space-x-1.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 ${sizeClasses}`}
        title="Candidate website discovered; requires domain or content verification"
      >
        <AlertTriangle className={size === 'sm' ? 'h-3 w-3 text-amber-600' : 'h-3.5 w-3.5 text-amber-600'} />
        <span>Candidate • Needs Verification</span>
      </span>
    );
  }

  if (isNotFound) {
    return (
      <span
        className={`inline-flex items-center space-x-1.5 rounded-md bg-slate-100 text-slate-600 border border-slate-200 ${sizeClasses}`}
        title="No official website found or verified for this firm"
      >
        <XCircle className={size === 'sm' ? 'h-3 w-3 text-slate-400' : 'h-3.5 w-3.5 text-slate-400'} />
        <span>Website Not Found</span>
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center space-x-1.5 rounded-md bg-slate-50 text-slate-600 border border-slate-200 ${sizeClasses}`}
    >
      <HelpCircle className={size === 'sm' ? 'h-3 w-3 text-slate-400' : 'h-3.5 w-3.5 text-slate-400'} />
      <span>{status || 'Unverified'}</span>
    </span>
  );
};
