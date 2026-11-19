# OpenCode Stats

Analisador local e somente leitura das estatísticas persistidas pelo OpenCode.

## Uso

```bash
python -m opencode_stats --date today
python -m opencode_stats --date 2026-08-22 --json
```

Por padrão, o CLI lê `~/.local/share/opencode/opencode.db`. Use `--database`
para informar outro banco SQLite.

O relatório usa os totais agregados por sessão e calcula a taxa de cache hit
como `cache_read / (cache_read + input)`, quando o denominador é maior que zero.

## Compatibilidade de schema

O leitor detecta automaticamente o schema do OpenCode v2 (`session_v2`) ou o
schema anterior (`session`). Quando as duas tabelas existem, usa somente
`session_v2`, evitando a contagem dupla de sessões migradas. O banco é aberto
em modo somente leitura, sem alterações nem migrações.

**Importante:** o filtro `--date` seleciona sessões pela data de criação
(`time_created`), e o resultado apresenta os totais acumulados dessas sessões.
Uma sessão com atividades em vários dias entra inteira no dia em que foi criada;
portanto, este não é um relatório de consumo estritamente diário.
