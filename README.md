# OpenCode Stats

Analisador local e somente leitura das estatísticas persistidas pelo OpenCode.

## Uso

```bash
python -m opencode_stats --date today
python -m opencode_stats --date 2026-11-19 --json

# Filtros combináveis: provedor, modelo e intervalo de horário local
python -m opencode_stats --date today --provider anthropic
python -m opencode_stats --date today --model claude-sonnet-4-5
python -m opencode_stats --date 2026-11-19 --start-time 09:00 --end-time 12:30
python -m opencode_stats --date 2026-11-19 --provider openai --model gpt-5 --start-time 14:00 --end-time 18:00 --json

# Janela atravessando a meia-noite: 19/11 22:00 até 20/11 02:00
python -m opencode_stats --date 2026-11-19 --start-time 22:00 --end-time 02:00
```

Por padrão, o CLI lê `~/.local/share/opencode/opencode.db`. Use `--database`
para informar outro banco SQLite. Os identificadores `--model` e `--provider`
exigem correspondência exata com os IDs do OpenCode (por exemplo, `openai`,
`anthropic`, e o ID do modelo efetivamente usado).

`--start-time` (`--from-time`) é inclusivo e `--end-time` (`--to-time`) é exclusivo.
Ambos aceitam `HH:MM` em **horário local do computador** que executa o comando.
Na ausência de um limite, usa-se o início ou fim do dia selecionado. Se o fim
informado for igual ou anterior ao início, o fim passa a ser no dia seguinte.

## Como os filtros funcionam

**Sem os novos filtros:** conserva o comportamento original: seleciona sessões
pela data de criação (`session_v2.time_created` ou `session.time_created`) e
soma os **totais acumulados por sessão**. Uma sessão com atividades em vários
dias entra inteira no dia em que foi criada, portanto não é um consumo
diário preciso.

**Com qualquer filtro de modelo, provedor ou horário:** usa o schema v2 e calcula
o consumo por **mensagens do assistente** em `session_message`. Os filtros de
data e horário usam `session_message.time_created`, mesmo quando a sessão foi
criada antes da data selecionada. São somados apenas tokens e custos das
mensagens correspondentes, e não da sessão inteira.

O relatório retorna uma linha por sessão com atividade selecionada; o
`session_count` não aumenta quando há vários modelos na mesma sessão. Os
campos `model` e `provider` da sessão são `null` quando há múltiplos valores
(ou valores desconhecidos) entre as mensagens selecionadas. O JSON apresenta
`aggregation` (`session`/`message`) e `filters`, incluindo os limites em
milissegundos desde a época Unix, com limite final exclusivo.

Os filtros dependem das tabelas `session_v2` e `session_message` do OpenCode v2.
No schema legado, o programa mostra um erro explicativo em vez de atribuir
consumo ao modelo ou provedor errado. A seleção por hora usa a criação da
mensagem do assistente, não o horário de conclusão da resposta. Custos de
compactação registrados apenas como eventos, sem mensagem correspondente,
não podem ser atribuídos a provedor/modelo por este relatório filtrado.

O banco é aberto em modo somente leitura, sem alterações nem migrações. A taxa
de cache hit usa `cache_read / (cache_read + input)`, quando o denominador é
maior que zero.
