import { useContext, useState } from 'react';
import { EDGES, FLOWS, NODES, NODE_H, NODE_W } from './data';
import { PresentationContext } from './context';

const byId = Object.fromEntries(NODES.map((node) => [node.id, node]));
const key = (a, b) => [a, b].sort().join('|');
const center = (node) => [node.x + NODE_W / 2, node.y + NODE_H / 2];

function pathEdges(path) {
  return new Set(path.slice(1).map((id, index) => key(path[index], id)));
}

export function ArchDiagram({ path = null, selected, onSelect }) {
  const activeNodes = path ? new Set(path) : null;
  const activeEdges = path ? pathEdges(path) : null;
  return (
    <svg className="pz-arch" viewBox="0 0 1060 580" role="img" aria-label="Arquitetura interativa do PC2YOU">
      {EDGES.map(([a, b]) => {
        const [x1, y1] = center(byId[a]);
        const [x2, y2] = center(byId[b]);
        const on = activeEdges ? activeEdges.has(key(a, b)) : false;
        return <line key={key(a, b)} x1={x1} y1={y1} x2={x2} y2={y2}
          className={`pz-edge${on ? ' on' : ''}${activeEdges && !on ? ' dim' : ''}`} />;
      })}
      {NODES.map((node) => {
        const on = activeNodes ? activeNodes.has(node.id) : true;
        return (
          <g key={node.id} className={`pz-node g-${node.group}${on ? '' : ' dim'}${selected === node.id ? ' sel' : ''}`}
            transform={`translate(${node.x} ${node.y})`} tabIndex={0} role="button" aria-label={node.label}
            onClick={() => onSelect?.(node.id)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect?.(node.id)}>
            <rect width={NODE_W} height={NODE_H} rx="14" />
            <text x={NODE_W / 2} y="23" className="pz-node-title">{node.label}</text>
            <text x={NODE_W / 2} y="40" className="pz-node-sub">{node.sub}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function NodePanel({ nodeId }) {
  const { openCode } = useContext(PresentationContext);
  const node = byId[nodeId];
  if (!node) return <aside className="pz-panel"><p className="pz-muted">Clique em um bloco do diagrama para ver responsabilidade, arquivo, entrada, processamento e saída.</p></aside>;
  return (
    <aside className="pz-panel">
      <h3>{node.label}</h3>
      <p>{node.role}</p>
      <dl>
        <dt>Arquivo / função</dt><dd><code>{node.file}</code></dd>
        <dt>Porta</dt><dd>{node.port}</dd>
        <dt>Entrada</dt><dd>{node.input}</dd>
        <dt>Processamento</dt><dd>{node.process}</dd>
        <dt>Saída</dt><dd>{node.output}</dd>
        <dt>Dependências</dt><dd>{node.deps.length ? node.deps.join(' · ') : '—'}</dd>
      </dl>
      {node.snippet && <button type="button" className="pz-btn" onClick={() => openCode(node.snippet)}>Ver código</button>}
    </aside>
  );
}

export function ArchitectureSection() {
  const [selected, setSelected] = useState('api_ia');
  const [flowId, setFlowId] = useState(null);
  const flow = FLOWS.find((f) => f.id === flowId);
  return (
    <>
      <p className="pz-lead">Clique em qualquer bloco. Escolha uma funcionalidade para destacar somente o caminho percorrido.</p>
      <div className="pz-chips">
        <button type="button" className={`pz-chip${!flowId ? ' on' : ''}`} onClick={() => setFlowId(null)}>Visão geral</button>
        {FLOWS.map((f) => (
          <button type="button" key={f.id} className={`pz-chip${flowId === f.id ? ' on' : ''}`} onClick={() => setFlowId(f.id)}>{f.label}</button>
        ))}
      </div>
      <div className="pz-split">
        <ArchDiagram path={flow?.path} selected={selected} onSelect={setSelected} />
        <NodePanel nodeId={selected} />
      </div>
      <p className="pz-note">* Na versão de apresentação a autenticação (API de usuários) fica oculta; PostgreSQL permanece apenas porque a API IA o exige no boot.</p>
    </>
  );
}

export function FlowSection() {
  const { openCode } = useContext(PresentationContext);
  const [flowId, setFlowId] = useState('analyze');
  const [selected, setSelected] = useState(null);
  const flow = FLOWS.find((f) => f.id === flowId);
  return (
    <>
      <p className="pz-lead">O que acontece quando o usuário clica? Escolha a ação e acompanhe UI → API → regras → banco/serviço → resposta.</p>
      <div className="pz-chips">
        {FLOWS.map((f) => (
          <button type="button" key={f.id} className={`pz-chip${flowId === f.id ? ' on' : ''}`} onClick={() => setFlowId(f.id)}>{f.label}</button>
        ))}
      </div>
      <div className="pz-split">
        <ArchDiagram path={flow.path} selected={selected} onSelect={setSelected} />
        <ol className="pz-steps">
          {flow.steps.map(([where, what, snippet], index) => (
            <li key={where + index}>
              <b>{where}</b>
              <span>{what}</span>
              <button type="button" className="pz-link" onClick={() => openCode(snippet)}>ver código</button>
            </li>
          ))}
        </ol>
      </div>
      {selected && <NodePanel nodeId={selected} />}
    </>
  );
}
