import { useState } from 'react';
import { imageCandidates } from '../utils/commerce';

export default function HardwareImage({ component, className = '' }) {
  const [failed, setFailed] = useState([]);
  const images = imageCandidates(component);
  const src = images.find(url => !failed.includes(url));
  return src ? <img src={src} alt={component.name || 'Hardware'} className={className} loading="lazy"
    title={src.startsWith('/images/') ? 'Foto ilustrativa do modelo ASUS; o fabricante da oferta pode variar.' : undefined}
    onError={() => setFailed(previous => [...previous, src])} /> : <span className="image-unavailable">Imagem indisponível</span>;
}
