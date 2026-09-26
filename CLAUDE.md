# CLAUDE.md — tcc-reducheck

Este repositório é o TCC II de Ciência da Computação (UFJF) da Isabella Mourão: uma **biblioteca Python
(nome provisório `reducheck`) que verifica se um modelo de EDOs simplificado é fiel ao original**.
O estudo de caso é o modelo de remodelação óssea na menopausa de Verly et al. (2024).

Prazo final: **29/11/2026**. O maior risco é o escopo crescer. Não adicione nada fora do escopo sem perguntar.

## Leia antes de qualquer tarefa

| Arquivo | O que tem |
| --- | --- |
| `docs/produto.md` | Documento de produto: escopo, **formato do input (YAML)**, **formato do output e regra do veredito**, pipeline, capacidades (F1, E1, …) e critérios de pronto |
| `docs/questoes-em-aberto.md` | Decisões tomadas e pendentes, questões técnicas, trabalhos relacionados, diferença para Frøysa et al. (2018) |
| `docs/tcc1.pdf` | Texto do TCC I: modelo, simplificações 1 e 2, métricas usadas até agora |
| Issues do GitHub | As tarefas. Cada uma tem contexto, critérios de aceite e uma seção "Instrução para o Claude" |

Código original do modelo: https://github.com/isasmourao/TCC-bone_estradiol, arquivo
`original_Model/bone_estradiol.py` (função `bonerepair`). Variáveis:
`D, Mo, M1, M2, C1, C2, Cm, Cb, Mc, Mb, E2` (atenção: `Mo` com a letra o; M1 começa em 0).

## Como executar uma tarefa (issue)

1. Leia a issue inteira: `gh issue view <N>`. Siga a seção "Instrução para o Claude".
2. Confira as dependências listadas em "Depende de". Se alguma estiver aberta, avise antes de começar.
3. Crie um branch: `git checkout -b issue-<N>-<resumo-curto>`.
4. Se faltar informação (por exemplo, uma equação ou uma decisão da orientadora), **pergunte**. Não invente.
5. Trabalhe em passos pequenos, com testes. Rode `pytest` e `ruff check .` antes de concluir.
6. No fim, percorra os critérios de aceite um a um e diga, para cada um, a evidência (teste, arquivo,
   comando). Não marque como feito o que não verificou.
7. Faça commit e abra um PR com `Closes #<N>` na descrição e a lista de critérios de aceite marcada.

## Pipeline e módulos

entrada (config) → simulação (simulation) → mapeamento (mapping) → métricas (metrics) e qualitativo
(qualitative) → veredito (verdict) → relatório (report); mais cli.
Motor de simulação: libRoadRunner. Modelos escritos em Antimony e exportados para SBML.

### Árvore de pastas

```
tcc-reducheck/
├── .github/workflows/ci.yml   # ruff + pytest em Python 3.11 e 3.12, a cada push e PR
├── CLAUDE.md
├── README.md
├── pyproject.toml             # metadados, dependências e config do pytest/ruff
├── docs/                      # produto.md, questoes-em-aberto.md, tcc1.pdf
├── planejamento/              # tarefas.yaml (fonte das issues) e criar_issues.py
├── src/reducheck/
│   ├── __init__.py            # __version__
│   ├── config.py              # ler e validar o YAML
│   ├── simulation.py          # simular os dois modelos nas mesmas condições
│   ├── mapping.py             # casar variáveis (1:1, soma, soma ponderada)
│   ├── metrics.py             # métricas plugáveis
│   ├── qualitative.py         # equilíbrio e estabilidade local
│   ├── verdict.py             # critérios e veredito
│   ├── report.py              # JSON, HTML e gráficos
│   └── cli.py                 # linha de comando
└── tests/
    ├── test_skeleton.py
    └── fixtures/              # modelos SBML de teste
```

### Comandos

```bash
pip install -e .[dev]   # instalação para desenvolvimento (Python 3.11+)
pytest                  # testes
ruff check .            # lint
ruff check . --fix      # lint com correção automática
```

## Convenções

- Python 3.11+, layout `src/reducheck/`, type hints em tudo, pytest, ruff.
- Identificadores e docstrings em inglês; **chaves do YAML, mensagens de erro e textos do relatório em português**.
- Toda função pública com teste. Testes primeiro quando o comportamento esperado é conhecido.
- Os dois modelos sempre simulados com o mesmo vetor de tempo, solver e tolerâncias.
- Não afrouxe tolerâncias nem ajuste limites para fazer um teste ou uma simplificação passar.
- Não adicione dependências além das do pyproject sem justificar.

## Fora do escopo (não implementar)

CellML e outros formatos; mapeamentos por expressão arbitrária; busca de todos os equilíbrios;
estabilidade global; incerteza de parâmetros; interface gráfica; geração automática de simplificações.

## Tarefas de escrita (issues com label `escrita`)

A Isabella escreve a versão final; o seu papel é rascunhar, pesquisar e revisar. Texto em LaTeX no
template SBC (o mesmo do `docs/tcc1.pdf`), em `texto/`. Nunca invente referências: onde faltar fonte,
escreva `[CITAR: o que precisa ser sustentado]`. Confira cada referência na fonte original antes de citar.
