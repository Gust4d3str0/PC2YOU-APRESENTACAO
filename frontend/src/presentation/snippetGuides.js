import guides from './snippetGuides.json';

// Explanations are tied to the exact source so an outdated guide cannot describe changed lines.
export function getSnippetGuide(snippet) {
  const guide = guides[snippet.id];
  return guide?.sourceCode === snippet.code && guide.lines.length === snippet.code.split('\n').length ? guide : null;
}
