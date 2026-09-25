import {
  CHAT_STATUSES,
  type ChatResponse,
  type ClaimStatus,
  type LegalClaim,
  type LegalSource,
} from '../types/chat.ts';

const CLAIM_STATUSES: ClaimStatus[] = [
  'supported',
  'partially_supported',
  'unsupported',
];

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const asString = (value: unknown): string | undefined =>
  typeof value === 'string' ? value : undefined;

const asNullableString = (value: unknown): string | null | undefined =>
  value === null || typeof value === 'string' ? value : undefined;

const asNumber = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) ? value : undefined;

const asStringArray = (value: unknown): string[] =>
  Array.isArray(value)
    ? value
        .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
        .map((item) => item.trim())
    : [];

const normalizeClaim = (value: unknown): LegalClaim | null => {
  const claim = asRecord(value);
  if (!claim) return null;

  const claimId = asString(claim.claim_id)?.trim();
  const text = asString(claim.text)?.trim();
  if (!claimId || !text) return null;

  const status = CLAIM_STATUSES.find((candidate) => candidate === claim.status);

  return {
    claim_id: claimId,
    text,
    evidence_chunk_ids: asStringArray(claim.evidence_chunk_ids),
    question_part: asString(claim.question_part),
    answerable: typeof claim.answerable === 'boolean' ? claim.answerable : undefined,
    status,
    score: asNumber(claim.score),
    reason: asString(claim.reason),
  };
};

const normalizeSource = (value: unknown): LegalSource | null => {
  const source = asRecord(value);
  if (!source) return null;

  const provisionId = asString(source.provision_id)?.trim();
  if (!provisionId) return null;

  return {
    provision_id: provisionId,
    provision_key: asString(source.provision_key),
    breadcrumb: asString(source.breadcrumb),
    doc_id: asString(source.doc_id),
    text: asString(source.text),
    valid_from: asNullableString(source.valid_from),
    valid_to: asNullableString(source.valid_to),
    temporal_warning: asNullableString(source.temporal_warning),
    rrf_score: asNumber(source.rrf_score),
    retriever_sources: asStringArray(source.retriever_sources),
  };
};

export const normalizeChatResponse = (value: unknown): ChatResponse => {
  const response = asRecord(value);
  if (!response) {
    throw new Error('Phản hồi từ máy chủ không đúng định dạng.');
  }

  const status = CHAT_STATUSES.find((candidate) => candidate === response.status);
  const answer = asString(response.answer);
  if (!status || answer === undefined) {
    throw new Error('Phản hồi từ máy chủ thiếu trạng thái hoặc nội dung trả lời.');
  }

  return {
    status,
    answer,
    claims: Array.isArray(response.claims)
      ? response.claims.map(normalizeClaim).filter((claim): claim is LegalClaim => claim !== null)
      : [],
    sources: Array.isArray(response.sources)
      ? response.sources.map(normalizeSource).filter((source): source is LegalSource => source !== null)
      : [],
    retrieved_sources: Array.isArray(response.retrieved_sources)
      ? response.retrieved_sources
          .map(normalizeSource)
          .filter((source): source is LegalSource => source !== null)
      : [],
    warnings: asStringArray(response.warnings),
  };
};
