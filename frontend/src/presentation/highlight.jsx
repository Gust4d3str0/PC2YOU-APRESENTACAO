import { Fragment } from 'react';

// Tiny dependency-free highlighter for the Code Explorer (python / js / jsx / plain text).
const KEYWORDS = new Set(('def class return if elif else for while in not and or is None True False import from as with try except finally ' +
  'raise lambda yield async await pass break continue const let var function export default new null undefined true false ' +
  'typeof throw catch this').split(' '));

const TOKEN = /(#.*|\/\/.*)|("""[\s\S]*?"""|'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`)|(@\w+)|\b(\d[\d_.]*)\b|([A-Za-z_]\w*)/g;

function tokenize(line) {
  const parts = [];
  let last = 0;
  line.replace(TOKEN, (match, comment, string, decorator, number, word, offset) => {
    if (offset > last) parts.push({ text: line.slice(last, offset) });
    let type = null;
    if (comment) type = 'comment';
    else if (string) type = 'string';
    else if (decorator) type = 'decorator';
    else if (number) type = 'number';
    else if (word && KEYWORDS.has(word)) type = 'keyword';
    else if (word && /^[A-Z]/.test(word)) type = 'type';
    parts.push({ text: match, type });
    last = offset + match.length;
    return match;
  });
  if (last < line.length) parts.push({ text: line.slice(last) });
  return parts;
}

export default function Code({ code, start = 1, language = 'python' }) {
  const lines = String(code || '').split('\n');
  return (
    <pre className={`pz-code lang-${language}`} tabIndex={0}>
      <code>
        {lines.map((line, index) => (
          <div className="pz-line" key={index}>
            <span className="pz-ln">{start + index}</span>
            <span className="pz-src">
              {language === 'text' ? line : tokenize(line).map((part, i) => (
                <Fragment key={i}>{part.type ? <span className={`tk-${part.type}`}>{part.text}</span> : part.text}</Fragment>
              ))}
              {'\n'}
            </span>
          </div>
        ))}
      </code>
    </pre>
  );
}

