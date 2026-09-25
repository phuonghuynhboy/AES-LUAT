import type { LegalClaim, LegalSource } from '../types/chat';

export type LegalSourceIndex = ReadonlyMap<string, LegalSource>;

const isDevelopment = import.meta.env?.DEV === true;

export const buildSourceIndex = (sources: LegalSource[]): LegalSourceIndex => {
  const index = new Map<string, LegalSource>();

  for (const source of sources) {
    if (index.has(source.provision_id)) {
      if (isDevelopment) {
        console.warn(
          `Duplicate citation source metadata for provision_id=${source.provision_id}; keeping first occurrence.`,
        );
      }
      continue;
    }
    index.set(source.provision_id, source);
  }

  return index;
};

export const findSourceByProvisionId = (
  provisionId: string,
  sourceIndex: LegalSourceIndex,
): LegalSource | undefined => {
  const source = sourceIndex.get(provisionId);
  if (!source && isDevelopment) {
    console.warn(`Citation source metadata missing for provision_id=${provisionId}`);
  }
  return source;
};

export const getCitableClaims = (claims: LegalClaim[]): LegalClaim[] =>
  claims.filter(
    (claim) =>
      (claim.status === 'supported' || claim.status === 'partially_supported') &&
      claim.answerable !== false &&
      claim.evidence_chunk_ids.length > 0,
  );

export const uniqueEvidenceIds = (claim: LegalClaim): string[] =>
  [...new Set(claim.evidence_chunk_ids)];

export const splitBreadcrumb = (breadcrumb?: string): string[] =>
  breadcrumb?.split('>').map((part) => part.trim()).filter(Boolean) ?? [];

export const getCitationLabel = (source?: LegalSource): string => {
  if (!source) return 'Nguồn chưa khả dụng';

  const parts = splitBreadcrumb(source.breadcrumb);
  const provisions = parts.filter((part) => /^(Điều|Khoản|Điểm)(?:\s|$)/i.test(part));

  return provisions.length > 0
    ? provisions.join(', ')
    : parts.at(-1) || 'Nguồn pháp lý';
};

export const formatBackendDate = (value: string | null | undefined): string => {
  if (value === undefined) return 'Backend chưa cung cấp';
  if (value === null) return 'Chưa ghi nhận';

  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;

  const [, year, month, day] = match;
  const date = new Date(`${value}T00:00:00Z`);
  if (
    Number.isNaN(date.getTime()) ||
    date.getUTCFullYear() !== Number(year) ||
    date.getUTCMonth() + 1 !== Number(month) ||
    date.getUTCDate() !== Number(day)
  ) {
    return value;
  }

  return `${day}/${month}/${year}`;
};

export const getValidityDisplay = (source: LegalSource) => ({
  validFrom: formatBackendDate(source.valid_from),
  validTo:
    source.valid_to === null
      ? 'Chưa ghi nhận ngày hết hiệu lực'
      : formatBackendDate(source.valid_to),
});
