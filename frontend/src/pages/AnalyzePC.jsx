import { useEffect, useRef, useState } from 'react';
import { Cpu, LoaderCircle, Sparkles } from 'lucide-react';
import Header from '../components/Header';
import PCAnalysisResult from '../components/PCAnalysisResult';
import UpgradeRecommendations from '../components/UpgradeRecommendations';
import { budgetsApi, getApiErrorMessage } from '../api';
import './AnalyzePC.css';

const fields = [
  ['cpu', 'Processador', 'Ryzen 5 5600'], ['gpu', 'Placa de vídeo', 'RTX 3060 12 GB'],
  ['motherboard', 'Placa-mãe', 'B550M'], ['ram', 'Memória RAM', '16 GB DDR4 3200'],
  ['storage', 'Armazenamento', 'SSD NVMe 1 TB'], ['psu', 'Fonte', 'Marca, modelo e potência'],
  ['case', 'Gabinete (opcional)', 'Marca e modelo'], ['monitor', 'Monitor (opcional)', 'Marca e modelo'],
];
const usages = [
  ['gaming', 'Jogos'], ['programming', 'Programação'], ['general', 'Uso geral'],
  ['editing', 'Edição'], ['streaming', 'Streaming'], ['3d_rendering', '3D'], ['ai_ml', 'IA / ML'],
];

export default function AnalyzePC() {
  const [values, setValues] = useState(Object.fromEntries(fields.map(([key]) => [key, ''])));
  const [usage, setUsage] = useState(['gaming']);
  const [resolution, setResolution] = useState('1080p');
  const [refreshRate, setRefreshRate] = useState('');
  const [games, setGames] = useState('');
  const [budget, setBudget] = useState('');
  const [result, setResult] = useState(null);
  const [submittedPayload, setSubmittedPayload] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const request = useRef(null);

  useEffect(() => () => request.current?.abort(), []);

  const submit = async (event) => {
    event.preventDefault();
    if (request.current) return;
    if (!usage.length) { setError('Selecione pelo menos um objetivo de uso.'); return; }
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError('');
    setResult(null);
    setSubmittedPayload(null);
    const components = Object.fromEntries(fields.filter(([key]) => key !== 'monitor').map(([key]) => [
      key, key === 'storage' ? values[key].split(';').map((v) => v.trim()).filter(Boolean) : values[key].trim() || null,
    ]));
    try {
      const analysisPayload = {
        components, usage, resolution,
        refresh_rate: refreshRate === '' ? null : Number(refreshRate),
        monitor: values.monitor.trim() || null,
        games: games.split(';').map((game) => game.trim()).filter(Boolean),
        upgrade_budget: budget === '' ? null : Number(budget),
      };
      const { data } = await budgetsApi.post('/ai/analyze-pc', analysisPayload, { signal: controller.signal, timeout: 130000 });
      if (!controller.signal.aborted) { setResult(data); setSubmittedPayload(analysisPayload); }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err?.response?.status === 422
          ? 'Revise os campos: informe apenas dados técnicos, sem dados pessoais ou instruções. CPU e um objetivo são obrigatórios.'
          : getApiErrorMessage(err, 'Não foi possível concluir a análise. Confira a conexão e tente novamente.'));
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
      request.current = null;
    }
  };

  return <>
    <Header />
    <main className="main-container analyze-page">
      <section className="page-heading">
        <div><span className="eyebrow">Seu próximo upgrade começa aqui</span><h1>Analisar meu PC</h1></div>
        <p>Conte como você usa seu computador. Receba uma análise e prioridades de melhoria.</p>
      </section>
      <div className="analyze-intro"><Sparkles size={23} /><p>Uma orientação para decidir com mais clareza.
        A compatibilidade é verificada pelas regras do PC2YOU antes da análise por IA.</p></div>
      <form onSubmit={submit} className="analyze-form" aria-busy={loading}>
        <fieldset disabled={loading} className="summary-panel analyze-section">
          <legend><Cpu size={20} /> Configuração atual</legend>
          <p className="analyze-hint">Use o nome completo da peça para facilitar a identificação no catálogo.
            Se não souber algum dado, deixe em branco. Não inclua dados pessoais.</p>
          <div className="analyze-fields">
            {fields.map(([key, label, placeholder]) => <label key={key}>
              {label}{key === 'cpu' ? ' *' : ''}
              <input name={key} required={key === 'cpu'} maxLength={key === 'storage' ? 967 : 120}
                placeholder={placeholder} value={values[key]} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />
            </label>)}
          </div>
          <small className="analyze-hint">Para vários dispositivos de armazenamento, separe os nomes por ponto e vírgula.</small>
        </fieldset>
        <fieldset disabled={loading} className="summary-panel analyze-section">
          <legend>Meu uso</legend>
          <p className="analyze-hint">Selecione na ordem de prioridade. O primeiro objetivo terá maior peso.</p>
          <div className="analyze-usages">
            {usages.map(([key, label]) => <label key={key} className={usage.includes(key) ? 'selected' : ''}>
              <input type="checkbox" checked={usage.includes(key)} onChange={() => setUsage((current) =>
                current.includes(key) ? current.filter((item) => item !== key) : [...current, key])} />
              {label}{usage.includes(key) && <span className="usage-order">{usage.indexOf(key) + 1}</span>}
            </label>)}
          </div>
          <div className="analyze-fields">
            <label>Resolução<select value={resolution} onChange={(e) => setResolution(e.target.value)}>
              <option>1080p</option><option>1440p</option><option>4K</option>
            </select></label>
            <label>Taxa de atualização (Hz, opcional)<input type="number" min="24" max="1000" step="1"
              placeholder="144" value={refreshRate} onChange={(e) => setRefreshRate(e.target.value)} /></label>
            <label>Jogos (opcional)<input maxLength="1814" placeholder="Valorant; Minecraft; Cyberpunk 2077"
              value={games} onChange={(e) => setGames(e.target.value)} /><small>Separe por ponto e vírgula. Até 15 jogos.</small></label>
            <label>Orçamento para upgrade (R$, opcional)<input type="number" min="0" max="1000000" step="0.01"
              placeholder="2000" value={budget} onChange={(e) => setBudget(e.target.value)} /></label>
          </div>
        </fieldset>
        {error && <div className="error-msg" role="alert">{error}</div>}
        <div className="analyze-submit">
          <button className="btn-primary" disabled={loading} type="submit">
            {loading ? <LoaderCircle size={20} className="analysis-spinner" /> : <Sparkles size={20} />}
            {loading ? 'Analisando sua configuração...' : 'Analisar meu PC'}
          </button>
          <span role="status">{loading ? 'Pode levar alguns instantes. Aguarde a conclusão.' : 'Recomendação qualitativa, sem estimativa exata de FPS.'}</span>
        </div>
      </form>
      {result && <PCAnalysisResult result={result} />}
      {submittedPayload && <UpgradeRecommendations key={JSON.stringify(submittedPayload)} payload={submittedPayload} />}
      <p className="analysis-disclaimer">Esta análise é uma recomendação. O desempenho depende do jogo, aplicação,
        configurações e carga. Sem benchmarks externos, não há previsão exata de FPS. Preços vêm de ofertas anunciadas
        em fontes reais (como o Telegram), podem mudar ou exigir condições, e não são confirmados. A compatibilidade depende das regras e dos dados disponíveis;
        confirme BIOS, conectores e medidas antes de comprar.</p>
    </main>
  </>;
}
