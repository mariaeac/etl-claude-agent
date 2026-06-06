
# ETL Automatizado — Pipeline Dinâmico

## Objetivo
Pipeline ETL que aceita qualquer CSV colocado em data/raw/.
Para cada arquivo novo, o agente detecta automaticamente o schema,
limpa os dados, carrega no DuckDB e gera um relatório de métricas.
O pipeline é agnóstico ao dataset — nunca assuma nomes de colunas.

## Estrutura de pastas
data/raw/        → CSVs originais. NUNCA modificar ou apagar.
data/processed/  → CSVs limpos gerados pelo pipeline.
scripts/         → scripts Python do pipeline.
reports/         → relatórios Markdown, um por execução.
etl.duckdb       → banco DuckDB local (criado automaticamente).

## Regras universais de qualidade
Aplicar a qualquer dataset, sem exceção:
- Nomes de colunas: lowercase, espaços → underscore, sem caracteres especiais
- Linhas com mais de 30% de campos nulos: descartar e logar no relatório
- Strings numéricas com vírgula brasileira (ex: "1.234,56"): converter pra float
- Datas em qualquer formato reconhecível: normalizar pra ISO 8601 (YYYY-MM-DD)
- Espaços em branco no início/fim de strings: remover automaticamente
- Colunas com nome duplicado: renomear com sufixo _2, _3 etc.
- Nunca dropar colunas — apenas logar quando tiver mais de 80% de nulos

## Regras do agente
- Nunca modificar arquivos em data/raw/
- Sempre confirmar ações destrutivas antes de executar
- Nomear a tabela no DuckDB com o nome do arquivo sem extensão
  Exemplo: vendas.csv → tabela "vendas"
- Processar apenas arquivos que ainda não existem como tabela no DuckDB

## Como rodar o pipeline
python scripts/pipeline.py data/raw/<arquivo.csv>

## Formato do relatório (reports/relatorio_<nome>_<data>.md)
Deve conter obrigatoriamente:
- Linhas recebidas, processadas e descartadas
- Problemas detectados e corrigidos por coluna
- Schema final da tabela gravada no DuckDB
- Tempo total de execução
EOF