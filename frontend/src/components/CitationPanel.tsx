import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { LegalSource } from '../types/chat';
import { CitationSourceInfo } from './CitationSourceInfo';
import { CitationValidity } from './CitationValidity';

interface CitationPanelProps {
  source: LegalSource;
  onClose: () => void;
}

export const CitationPanel = ({ source, onClose }: CitationPanelProps) => {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;

    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        event.preventDefault();
        closeRef.current?.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [onClose]);

  return createPortal(
    <div className="citation-modal">
      <div className="citation-backdrop" onClick={onClose} aria-hidden="true" />
      <aside
        className="citation-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="citation-panel-title"
      >
        <header className="citation-panel__header">
          <div>
            <span>CHI TIẾT TRÍCH DẪN</span>
            <h2 id="citation-panel-title">Nguồn pháp lý</h2>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Đóng thông tin nguồn">
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M4 4l12 12M16 4 4 16" />
            </svg>
          </button>
        </header>

        <div className="citation-panel__scroll">
          <CitationSourceInfo source={source} />

          <section className="citation-section">
            <p className="citation-section__eyebrow">NỘI DUNG QUY ĐỊNH</p>
            {source.text?.trim() ? (
              <blockquote className="citation-source-text">{source.text}</blockquote>
            ) : (
              <p className="citation-empty-text">Nội dung nguồn chưa được backend cung cấp.</p>
            )}
          </section>

          <section className="citation-section">
            <p className="citation-section__eyebrow">THÔNG TIN VĂN BẢN</p>
            <dl className="citation-meta-grid">
              <div>
                <dt>Mã văn bản nguồn</dt>
                <dd>{source.doc_id || 'Backend chưa cung cấp'}</dd>
              </div>
            </dl>
          </section>

          <CitationValidity source={source} />

          <section className="citation-section citation-section--ids">
            <p className="citation-section__eyebrow">ĐỊNH DANH NGUỒN</p>
            <dl className="citation-meta-grid">
              <div>
                <dt>provision_id · ID chunk thực tế</dt>
                <dd><code>{source.provision_id}</code></dd>
              </div>
              <div>
                <dt>provision_key · Điều khoản logic</dt>
                <dd><code>{source.provision_key || 'Backend chưa cung cấp'}</code></dd>
              </div>
            </dl>
          </section>
        </div>
      </aside>
    </div>,
    document.body,
  );
};
