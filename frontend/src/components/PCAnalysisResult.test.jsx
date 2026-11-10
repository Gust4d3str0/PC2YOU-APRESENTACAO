import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import PCAnalysisResult from './PCAnalysisResult';
import saved from '../presentation/savedAnalysis.json';

describe('human technical resolution', () => {
  it('distinguishes derived, family, SKU and unresolved components', () => {
    const result = { ...saved.response, analysis: { ...saved.response.analysis, missing_information: [] }, components: [
      { name: '650W', category: 'psu', source: 'derived', resolution_scope: 'generic', specifications: { wattage: 650 }, compatibility: {} },
      { name: 'RTX 4060 Ti', category: 'gpu', source: 'catalog', resolution_scope: 'family', specifications: {}, compatibility: {} },
      { name: 'Gigabyte B550M K', category: 'motherboard', source: 'catalog', resolution_scope: 'sku', specifications: {}, compatibility: {} },
      { name: 'Unknown', category: 'case', source: 'user', resolution_scope: 'unresolved', specifications: {}, compatibility: {} },
    ] };
    const html = renderToStaticMarkup(<PCAnalysisResult result={result} />);
    expect(html).toContain('Informação técnica reconhecida');
    expect(html).toContain('Potência: 650W');
    expect(html).toContain('Modelo/família reconhecido');
    expect(html).toContain('Não identificado');
    expect(html).not.toContain('especificações não verificadas');
  });
});
