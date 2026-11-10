# Dados externos utilizados pelo PC2YOU

Os importadores e o código do PC2YOU têm licenciamento independente dos dados.
Este arquivo não relicencia o código nem atribui ao PC2YOU a autoria dos dados externos.
Snapshots, adaptações do banco e proveniência identificam a licença de cada fonte.

## BuildCores OpenDB

- Autoria/fonte: BuildCores OpenDB e seus contribuidores.
- Repositório: https://github.com/buildcores/buildcores-open-db
- Versão utilizada: `e4838129c57b26d4f0711871d5ae68f3a9c848a9`.
- Licença: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
- [Texto preservado](third-party-data/BuildCores-LICENSE.txt) e [NOTICE preservado](third-party-data/BuildCores-NOTICE.md).
- Manifesto/checksum: [external-data/manifests/buildcores.json](external-data/manifests/buildcores.json).

Utilização: catálogo técnico para o projeto acadêmico PC2YOU, na finalidade não comercial
informada pelo responsável. Mudanças: seleção de sete categorias, exclusão de itens fora
do escopo desktop, normalização de unidades, resolução conservadora de identidades,
remoção de dados comerciais, mapeamento de campos e registro de conflitos/proveniência.
Não há endosso do BuildCores ao PC2YOU.

Ao compartilhar publicamente adaptações do banco que dependam dos direitos licenciados,
preservar atribuição, notices, identificação das mudanças e as condições ShareAlike e
NonCommercial. A documentação do upstream esclarece que o caráter acadêmico, isoladamente,
não determina a finalidade não comercial. Uso comercial que dependa de autorização exige
uma licença própria dos titulares aplicáveis. Fotografias, logos, manuais e outros materiais
de terceiros têm direitos separados e não são importados pelo pipeline.

## PC Part Dataset

- Autoria/fonte: Doc Oliver, dataset de componentes publicado a partir de PCPartPicker.
- Repositório: https://github.com/docyx/pc-part-dataset
- Versão utilizada: `c52a04ca9465c83997ed335f7767b09a2005dd26`.
- Atualização dos dados informada no README dessa versão: 23 de julho de 2025.
- Licença do repositório: MIT, copyright (c) 2021–2025 Doc Oliver.
- [Texto completo preservado](third-party-data/PC-Part-Dataset-LICENSE.txt).
- Manifesto/checksum: [external-data/manifests/pc_part_dataset.json](external-data/manifests/pc_part_dataset.json).

Utilização: consumo dos JSONs publicados em `data/json`, com filtros, validação,
normalização, deduplicação e proveniência. O scraper não é baixado nem executado.
Preços e `price_per_gb` são descartados; esses valores não são ofertas comerciais atuais.
A atribuição MIT é mantida também em adaptações que incorporem registros dessa fonte.

## Separação das fontes

Os IDs externos ficam em `external_ids`, e cada campo importado mantém fonte, ID,
commit, licença e data em `spec_provenance`. As chaves de proveniência usam `__`
no lugar de `.` para seguir a convenção existente do projeto e preservar compatibilidade
com ferramentas MongoDB. O atributo `field` mantém o caminho canônico com pontos.
Confirmações de outra fonte acrescentam evidências sem apagar a origem principal.

Mercado Livre continua sendo a integração comercial existente; estes datasets não
substituem preços, disponibilidade ou validações das ofertas do Mercado Livre.
