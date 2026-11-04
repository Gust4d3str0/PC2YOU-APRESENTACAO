import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import snippets from './snippets.json';
import guides from './snippetGuides.json';
import { getSnippetGuide } from './snippetGuides';
import Code from './highlight';

describe('Guias do código real', () => {
  it.each(snippets)('$id tem explicações para a versão exata de todas as linhas', snippet => {
    const guide = getSnippetGuide(snippet);
    expect(guide).not.toBeNull();
    expect(guide.sourceCode).toBe(snippet.code);
    expect(guide.lines).toHaveLength(snippet.code.split('\n').length);
    expect(guide.lines.every(line => typeof line === 'string' && line.trim().length > 15)).toBe(true);
    expect([guide.summary, guide.purpose, guide.example].every(text => text.length > 30)).toBe(true);
  });

  it('não associa um guia a código que mudou', () => {
    expect(getSnippetGuide({ ...snippets[0], code: `${snippets[0].code}\nreturn null;` })).toBeNull();
  });

  it('não inventa guia para um trecho desconhecido', () => {
    expect(getSnippetGuide({ id: 'unknown', code: 'pass' })).toBeNull();
    expect(Object.keys(guides).sort()).toEqual(snippets.map(s => s.id).sort());
  });

  it('mostra explicações associadas às linhas originais e escapa texto HTML', () => {
    const html = renderToStaticMarkup(<Code code={'<script>\nreturn value;'} start={32} annotations={['Recebe um texto com marcação.', 'Devolve o valor calculado.']} />);
    expect(html).toContain('data-source-line="32"');
    expect(html).toContain('data-source-line="33"');
    expect(html).toContain('Devolve o valor calculado.');
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
  });

  it('mantém o modo original sem explicações adicionadas', () => {
    const snippet = snippets.find(s => s.id === 'ai-cache');
    const html = renderToStaticMarkup(<Code code={snippet.code} start={snippet.start} />);
    expect(html).not.toContain('pz-line-note');
    expect(html).toContain('run_cached');
    expect(html).toContain(`>${snippet.start}</span>`);
  });
});
