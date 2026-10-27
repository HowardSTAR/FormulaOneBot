import { useState, type ReactNode } from 'react';
import { GlossaryText } from './GlossaryText';
import { cleanBiography } from '../helpers/presentation';

export type BiographyImage = {
  url: string;
  source_url: string;
  author: string;
  license: string;
  license_url: string;
  caption?: string;
  width?: number;
  height?: number;
};

export function EntrantBiography({ title, text, source, image, facts }: { title: string; text: string; source?: string; image?: BiographyImage | null; facts?: ReactNode }) {
  const [photoFailed, setPhotoFailed] = useState(false);
  const paragraphs = cleanBiography(text).split(/\n\s*\n|\n/).map(paragraph => paragraph.trim()).filter(Boolean);
  const showPhoto = image && !photoFailed;
  return <section className={`entrant-biography${showPhoto ? ' entrant-biography--illustrated' : ''}`} aria-labelledby="entrant-bio-title">
    <h2 id="entrant-bio-title">{title}</h2>
    <div className="entrant-biography-flow">
      {showPhoto && <figure className="entrant-biography-photo">
        <img src={image.url} alt={image.caption || title} width={image.width || 1200} height={image.height || 800} loading="lazy" decoding="async" onError={() => setPhotoFailed(true)} />
        <figcaption>
          {image.caption && <span className="entrant-photo-caption">{image.caption}</span>}
          <span><a href={image.source_url} target="_blank" rel="noopener noreferrer">Фото: {image.author}</a><span aria-hidden="true"> · </span><a href={image.license_url} target="_blank" rel="noopener noreferrer">{image.license}</a></span>
        </figcaption>
      </figure>}
      <div className="entrant-biography-intro">
        {facts && <dl className="entrant-bio-facts">{facts}</dl>}
        <p className="entrant-biography-lead"><GlossaryText>{paragraphs[0] || 'Биография пока недоступна.'}</GlossaryText></p>
      </div>
      {paragraphs.length > 1 && <div className="entrant-biography-body">{paragraphs.slice(1).map((paragraph, index) => <p key={index}><GlossaryText>{paragraph}</GlossaryText></p>)}</div>}
    </div>
    {source && <footer className="entrant-biography-source"><a className="entrant-source" href={source} target="_blank" rel="noopener noreferrer">Читать в Wikipedia<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M14 4h6v6m0-6L10 14M20 14v6H4V4h6" /></svg></a><a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">Текст: CC BY-SA 4.0</a></footer>}
  </section>;
}
