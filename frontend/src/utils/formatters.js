export const CATEGORY_LABELS = {
  cpu: 'Processador',
  cooler: 'Cooler',
  motherboard: 'Placa-mãe',
  ram: 'Memória RAM',
  'kit-ram': 'Kit de Memória',
  storage: 'Armazenamento',
  gpu: 'Placa de vídeo',
  psu: 'Fonte',
  case: 'Gabinete',
};

export const CATEGORY_BADGES = {
  cpu: 'CPU',
  cooler: 'COOL',
  motherboard: 'MB',
  ram: 'RAM',
  'kit-ram': 'KIT',
  storage: 'SSD',
  gpu: 'GPU',
  psu: 'PSU',
  case: 'CASE',
};

export const SPEC_LABELS = {
  cores: 'Núcleos',
  threads: 'Threads',
  base_clock: 'Clock base',
  boost_clock: 'Clock boost',
  tdp_watts: 'TDP',
  socket: 'Socket',
  architecture: 'Arquitetura',
  generation: 'Geração',
  integrated_graphics: 'Gráfico integrado',
  recommended_use: 'Uso recomendado',

  memory: 'Memória',
  memory_bus: 'Barramento de memória',
  interface: 'Interface',
  power_consumption_watts: 'Consumo',
  length_mm: 'Comprimento',
  recommended_resolution: 'Resolução recomendada',
  ray_tracing: 'Ray Tracing',
  dlss_fsr: 'Upscaling',

  chipset: 'Chipset',
  form_factor: 'Formato',
  memory_type: 'Tipo de memória',
  memory_slots: 'Slots de RAM',
  max_memory_gb: 'Memória máxima',
  m2_slots: 'Slots M.2',
  pcie_version: 'Versão PCIe',
  wifi: 'Wi-Fi',
  bluetooth: 'Bluetooth',

  capacity: 'Capacidade',
  speed: 'Frequência',
  latency: 'Latência',
  voltage: 'Voltagem',
  profile: 'Perfil',
  modules: 'Módulos',
  rpm: 'Rotação',

  wattage: 'Potência',
  efficiency: 'Certificação',
  modularity: 'Modularidade',
  pcie_connectors: 'Conectores PCIe',
  min_psu_watts: 'Fonte mínima',

  fans: 'Ventoinhas inclusas',
  max_gpu_length_mm: 'GPU máxima',
  supported_form_factors: 'Formatos suportados',
  radiator_support: 'Suporte a radiador',
  front_panel: 'Painel frontal',

  type: 'Tipo',
  fan_size_mm: 'Tamanho da ventoinha',
  radiator_size_mm: 'Tamanho do radiador',
  height_mm: 'Altura',
  max_tdp_watts: 'TDP máximo suportado',
  socket_support: 'Sockets suportados',

  gaming_score: 'Score em jogos',
  workstation_score: 'Score profissional',
  ai_score: 'Score IA',
};

export function getCategoryLabel(category) {
  return CATEGORY_LABELS[category] || category || 'Categoria';
}

export function getCategoryBadge(category) {
  return CATEGORY_BADGES[category] || String(category || 'PC').toUpperCase();
}

export function getSpecLabel(key) {
  return SPEC_LABELS[key] || key.replaceAll('_', ' ');
}

export function formatSpecValue(key, value) {
  if (value === null || value === undefined || value === '') return 'Não informado';
  if (Array.isArray(value)) return value.join(', ');
  if ((key.includes('watts') || key === 'wattage') && typeof value === 'number') return `${value}W`;
  if (key.includes('_mm') && typeof value === 'number') return `${value} mm`;
  if (key.includes('_gb') && typeof value === 'number') return `${value}GB`;
  if (key === 'fans' && typeof value === 'number') return `${value} ventoinhas`;
  if (typeof value === 'boolean') return value ? 'Sim' : 'Não';
  return String(value);
}

export function generateTechnicalSummary(component) {
  const specs = component?.technical_specs || {};
  const category = component?.category;

  if (category === 'gpu') {
    return `GPU com ${specs.memory || 'memória dedicada'}, interface ${specs.interface || 'PCIe'} e consumo estimado de ${formatSpecValue('power_consumption_watts', specs.power_consumption_watts)}. Indicada para ${specs.recommended_use || specs.recommended_resolution || 'jogos e workloads gráficos'}.`;
  }

  if (category === 'cpu') {
    return `Processador com ${specs.cores || 'múltiplos'} núcleos e ${specs.threads || 'múltiplas'} threads, indicado para ${specs.recommended_use || 'jogos, multitarefa e aplicações exigentes'}.`;
  }

  if (category === 'motherboard') {
    return `Placa-mãe com chipset ${specs.chipset || 'moderno'}, suporte a ${specs.memory_type || 'memória compatível'}, formato ${specs.form_factor || 'ATX'} e socket ${specs.socket || component?.compatibility?.socket || 'compatível'}.`;
  }

  if (category === 'ram') {
    return `Memória ${specs.memory_type || 'RAM'} de ${specs.capacity || 'alta capacidade'} a ${specs.speed || 'boa frequência'}, indicada para builds modernas e multitarefa.`;
  }

  if (category === 'kit-ram') {
    return `Kit de memória ${specs.memory_type || 'RAM'} de ${specs.capacity || 'alta capacidade'} (${specs.modules || '2 módulos'}) a ${specs.speed || 'boa frequência'}. Dual-channel nativo para melhor desempenho.`;
  }

  if (category === 'storage') {
    return `SSD ${specs.interface || 'NVMe'} de ${specs.capacity || 'boa capacidade'}, indicado para ${specs.recommended_use || 'sistema operacional, jogos e softwares pesados'}.`;
  }

  if (category === 'psu') {
    return `Fonte de ${formatSpecValue('wattage', specs.wattage)} com certificação ${specs.efficiency || 'eficiente'}, indicada para ${specs.recommended_use || 'builds compatíveis com a potência selecionada'}.`;
  }

  if (category === 'case') {
    return `Gabinete ${specs.form_factor || 'compatível'} com ${formatSpecValue('fans', specs.fans)}, suporte a GPUs de até ${formatSpecValue('max_gpu_length_mm', specs.max_gpu_length_mm)} e formatos ${formatSpecValue('supported_form_factors', specs.supported_form_factors)}.`;
  }

  if (category === 'cooler') {
    const isLiquid = (specs.type || '').toLowerCase().includes('liquid');
    const cooling = isLiquid
      ? `Water Cooler com radiador de ${formatSpecValue('radiator_size_mm', specs.radiator_size_mm)}`
      : `Air Cooler com ventoinha de ${formatSpecValue('fan_size_mm', specs.fan_size_mm)}`;
    return `${cooling}. Suporta até ${formatSpecValue('max_tdp_watts', specs.max_tdp_watts)} de TDP. Compatível com sockets ${formatSpecValue('socket_support', specs.socket_support || component?.compatibility?.socket_support || [])}.`;
  }

  return component?.description || 'Componente técnico do catálogo PC2YOU.';
}
