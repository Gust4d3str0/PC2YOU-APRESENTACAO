# Snapshots externos

Os diretórios `buildcores/` e `pc_part_dataset/` são locais e ignorados pelo Git.
`manifests/` registra commits, checksums dos arquivos compactados, schemas e notices.
O `snapshot.json` completo de cada download contém o checksum de cada arquivo extraído.
O leitor verifica cada arquivo utilizado, o commit e a licença antes do processamento.

Recrie os snapshots com os comandos documentados em
[`docs/EXTERNAL_CATALOG_IMPORT.md`](../docs/EXTERNAL_CATALOG_IMPORT.md).
Dados e licenças: [`THIRD_PARTY_DATA_NOTICES.md`](../THIRD_PARTY_DATA_NOTICES.md).
