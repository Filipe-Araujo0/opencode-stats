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
