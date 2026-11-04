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

function SourceLine({ line, language }) {
  return language === 'text' ? line : tokenize(line).map((part, i) => (
    <Fragment key={i}>{part.type ? <span className={`tk-${part.type}`}>{part.text}</span> : part.text}</Fragment>
  ));
}

export default function Code({ id, code, start = 1, language = 'python', annotations }) {
  const lines = String(code || '').split('\n');
  if (annotations) {
    return (
      <div id={id} className={`pz-code pz-code-explained lang-${language}`} tabIndex={0} role="region" aria-label="Código com explicações linha por linha">
        {lines.map((line, index) => (
          <div className={`pz-annotated-line${line.trim() ? '' : ' blank'}`} data-source-line={start + index} key={index}>
            <div className="pz-line"><span className="pz-ln" aria-label={`Linha ${start + index}`}>{start + index}</span><code className="pz-src"><SourceLine line={line || ' '} language={language} /></code></div>
            {line.trim() && <p className="pz-line-note"><span className="pz-note-label">EXPLICAÇÃO</span>{annotations[index]}</p>}
          </div>
        ))}
      </div>
    );
  }
  return (
    <pre id={id} className={`pz-code lang-${language}`} tabIndex={0}>
      <code>{lines.map((line, index) => (
        <div className="pz-line" key={index}>
          <span className="pz-ln">{start + index}</span>
          <span className="pz-src"><SourceLine line={line} language={language} />{'\n'}</span>
        </div>
      ))}</code>
    </pre>
  );
}
