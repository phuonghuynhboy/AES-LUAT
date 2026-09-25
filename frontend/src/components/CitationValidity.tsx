import type { LegalSource } from '../types/chat';
import { getValidityDisplay } from '../utils/citations';

interface CitationValidityProps {
  source: LegalSource;
}

export const CitationValidity = ({ source }: CitationValidityProps) => {
  const validity = getValidityDisplay(source);

  return (
    <section className="citation-section">
      <p className="citation-section__eyebrow">HIỆU LỰC THEO METADATA</p>
      <dl className="citation-meta-grid">
        <div>
          <dt>Có hiệu lực từ</dt>
          <dd>{validity.validFrom}</dd>
        </div>
        <div>
          <dt>Hiệu lực đến</dt>
          <dd>{validity.validTo}</dd>
        </div>
      </dl>
      {source.temporal_warning?.trim() && (
        <div className="citation-temporal-warning" role="alert">
          <strong>Lưu ý về hiệu lực</strong>
          <p>{source.temporal_warning}</p>
        </div>
      )}
    </section>
  );
};
