const LABELS = {
  memory_size: 'Memória', memory_type: 'Tipo de memória', motherboard_interface: 'Interface com a placa-mãe', memory_bus: 'Barramento de memória',
  power_input: 'Conector de energia', connectivity: 'Conectividade', monitor_outputs: 'Saídas de vídeo', total_graphics_power: 'Potência da placa',
  power_requirement: 'Fonte recomendada', length: 'Comprimento', width: 'Largura', height: 'Altura', slot_size: 'Slots ocupados',
  cooling_type: 'Refrigeração', max_resolution: 'Resolução máxima', memory_speed: 'Velocidade da memória', memory_bandwidth: 'Banda da memória',
  core_count: 'Núcleos', threads: 'Threads', boost_clock: 'Clock máximo', base_clock: 'Clock base', socket: 'Soquete', tdp: 'TDP',
  integrated_graphics: 'Vídeo integrado', latency: 'Latência', modules: 'Módulos', release_year: 'Ano de lançamento',
};

/** Only trusted enrichment (the PC2YOU matcher accepted it without conflict). Never fetched from the browser: it comes with the component. */
function externalEnrichment(component) {
  const data = component?.external_enrichment?.mercado_livre;
  return data && data.match_status === 'matched' && !data.external_conflict ? data : null;
}

export default function ExternalSpecs({ component }) {
  const data = externalEnrichment(component);
  const rows = data ? Object.entries(data.specs || {}).filter(([key]) => LABELS[key]) : [];
  if (!data || (!rows.length && !data.short_description)) return null;
  const identity = [['Marca', data.brand], ['Fabricante', data.manufacturer], ['Modelo', data.model], ['Modelo detalhado', data.detailed_model]].filter(([, v]) => v);
  return <section className="summary-panel external-specs" aria-label="Especificações enriquecidas">
    <h2>Especificações enriquecidas por fonte externa</h2>
    {data.brand_variant && <p className="details-note">Imagem e dados de um modelo de parceiro compatível com {component.name}.</p>}
    {data.short_description && <p>{data.short_description}</p>}
    <dl className="kv-list">
      {[...identity, ...rows.map(([key, value]) => [LABELS[key], value])].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{String(value)}</dd></div>)}
    </dl>
  </section>;
}
