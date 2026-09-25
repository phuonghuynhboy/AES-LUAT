import type { LegalSource } from '../types/chat';
import { getCitationLabel } from '../utils/citations';

interface CitationBadgeProps {
  provisionId: string;
  source?: LegalSource;
  onOpen: (source: LegalSource) => void;
}

export const CitationBadge = ({ provisionId, source, onOpen }: CitationBadgeProps) => {
  const label = getCitationLabel(source);

  return (
    <button
      type="button"
      className={`citation-badge${source ? '' : ' citation-badge--unavailable'}`}
      onClick={() => source && onOpen(source)}
      disabled={!source}
      aria-label={
        source
          ? `Xem nguồn pháp lý: ${label}`
          : `Không tìm thấy metadata nguồn cho ${provisionId}`
      }
      title={source ? `Xem chi tiết nguồn: ${label}` : 'Không tìm thấy metadata nguồn'}
    >
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="M4.5 5.5h8a2 2 0 0 1 2 2v8h-8a2 2 0 0 0-2 2v-12Zm10 2h1a1 1 0 0 1 1 1v7h-10" />
      </svg>
      [{label}]
      {source && <span className="citation-badge__arrow" aria-hidden="true">↗</span>}
    </button>
  );
};
