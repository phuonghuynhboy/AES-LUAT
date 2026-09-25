import type { LegalSource } from '../types/chat';
import { splitBreadcrumb } from '../utils/citations';

interface CitationSourceInfoProps {
  source: LegalSource;
}

export const CitationSourceInfo = ({ source }: CitationSourceInfoProps) => {
  const parts = splitBreadcrumb(source.breadcrumb);
  const firstPart = parts[0];
  const hasDocumentName = firstPart && !/^(Điều|Khoản|Điểm)(?:\s|$)/i.test(firstPart);
  const documentName = hasDocumentName ? firstPart : undefined;
  const locationParts = hasDocumentName ? parts.slice(1) : parts;

  return (
    <section className="citation-section citation-source-info">
      <p className="citation-section__eyebrow">NGUỒN PHÁP LÝ</p>
      <h3>{documentName || 'Tên văn bản chưa được backend cung cấp'}</h3>
      {locationParts.length > 0 ? (
        <div className="citation-source-info__path" aria-label="Vị trí trong văn bản">
          {locationParts.map((part, index) => (
            <span key={`${part}-${index}`}>{part}</span>
          ))}
        </div>
      ) : (
        <p className="citation-muted">Chưa có thông tin Điều/Khoản/Điểm.</p>
      )}
      {source.breadcrumb && (
        <p className="citation-source-info__breadcrumb">{source.breadcrumb}</p>
      )}
    </section>
  );
};
