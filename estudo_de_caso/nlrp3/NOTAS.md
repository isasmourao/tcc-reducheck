# Modelo da Julia para teste: NLRP3 original x simplificado

Escrito em 04/11/2026. Testa se a biblioteca é genérica, isto é, se ela roda num modelo que não é o
de Verly et al. (2024) **sem mudar o código dela**.

| | |
| --- | --- |
| Modelo original | `modelos/nlrp3_original.xml` (13 variáveis) |
| Modelo simplificado | `modelos/nlrp3_simp.xml` (8 variáveis) |
| Fonte | notebooks do Colab da Julia, copiados sem alteração em `referencia/nlrp3/` |
| Tradução conferida | erro relativo máximo de 2,9e-8 (original) e 4,0e-8 (simplificado) contra os notebooks (`referencia/nlrp3/comparar_sbml.py`) |
| Configuração | `nlrp3_simp.yaml` |
| Condições | 0 a 300 min, 1001 pontos, CVODE, tol. relativa 1e-8 e absoluta 1e-10, iguais nos dois modelos |
| Ruído numérico de referência | 1,39e-05 (NRMSE máximo, em `IL18c`) |

Reproduzir:

```bash
python modelos/build_sbml.py
reducheck verificar estudo_de_caso/nlrp3/nlrp3_simp.yaml
```

## Resultado sobre a generalidade

**A biblioteca rodou no modelo novo sem nenhuma mudança de código.** O que foi preciso:

- escrever os dois modelos em Antimony, como no caso da Verly;
- escrever `nfkbn` sem `piecewise`, por causa de uma limitação do CVODE e não da biblioteca
  (`referencia/nlrp3/duvidas.md`, item 1);
- mapear duas variáveis com nomes diferentes (`proIL1b` → `proIL1B`, `IL1be` → `IL1Be`), o que o
  mapeamento 1:1 já cobre.

**Limitação encontrada:** três variáveis saem do simplificado por conservação (`ASCf = 1 - ASCb`,
`proC1 = 1 - C1`, `proIL18 = 1 - IL18c - IL18e`). Compará-las exigiria um mapeamento por expressão,
que está fora do escopo. Elas entram no YAML como eliminadas (`simplificado: null`). Na prática
nada se perde: o erro delas é o mesmo, em valor absoluto, das variáveis de que dependem (`ASCb`,
`C1`, `IL18c + IL18e`), que são comparadas.

## O que o simplificado muda (lido do código)

| O quê | Original | Simplificado |
| --- | --- | --- |
| `NLRP3i` | variável; NF-κB → `NLRP3i` → `NLRP3a` (`k1 = 0,7`) | removida: NF-κB alimenta `NLRP3a` direto |
| Degradação de `NLRP3a` | `delta1 = 0,002` | `novodelta1 = 0,0025` |
| `ASCf`, `proC1`, `proIL18` | variáveis | substituídas pelas leis de conservação |
| `IL1bc` | variável; vai para `IL1be` com taxa `k5·G = 0,08` e degrada com `delta2 = 0,004` | removida: uma fração `j = 0,7` do pró-IL-1β clivado vai direto para `IL1Be` |
| Nomes | `G`, `proIL1b`, `IL1be` | `Gnovo` (mesmo valor), `proIL1B`, `IL1Be` |

## Veredito (critérios provisórios)

**REPROVADO. 12 de 24 critérios (50,0%); obrigatórios 12/16, desejáveis 0/8.**

Os critérios são os do estudo de caso da Verly (NRMSE ≤ 5% e erro estacionário ≤ 1% obrigatórios,
MAPE ≤ 5% desejável), e todas as variáveis com contrapartida são core. **São provisórios:** quais
variáveis importam neste modelo e com quais limites ainda precisa ser decidido com a Bárbara.

| Variável | NRMSE | Erro estacionário | MAPE |
| --- | --- | --- | --- |
| `NLRP3a` | 2,83% | **7,84%** | 12,3% |
| `NLRP3o` | 1,52% | 0,08% | 10,4% |
| `ASCb` | 0,30% | 0,004% | 10,1% |
| `C1` | 0,22% | 0,0001% | 9,0% |
| `IL18c` | 1,41% | **6,02%** | 15,6% |
| `IL18e` | 0,75% | 0,000002% | 9,5% |
| `proIL1b` | 0,78% | 0,001% | 5,5% |
| `IL1be` | **19,8%** | **26,3%** | 106% |

Em negrito, as falhas obrigatórias. Os MAPE altos de `ASCb`, `C1`, `IL18c`, `IL18e` e `proIL1b` vêm,
em boa parte, de pontos perto de zero (o relatório avisa: de 6% a 44% dos pontos entram no cálculo
com o original abaixo de 1% do máximo). O NRMSE dessas variáveis fica abaixo de 1,5%.

### Por que falha

- **`IL1be` (a falha principal).** No original, a fração do IL-1β celular que chega ao meio
  extracelular é `k5·G / (k5·G + delta2) = 0,08 / 0,084 ≈ 0,952`; o simplificado usa `j = 0,7`. A
  razão `0,7 / 0,952 ≈ 0,735` explica o erro estacionário de 26%: `IL1be` final é 0,580 no original
  e 0,428 no simplificado.
- **`NLRP3a` no fim.** `novodelta1 = 0,0025` faz `NLRP3a` decair mais rápido que no original, no
  trecho final em que ele é pequeno.
- **`IL18c` no fim.** `IL18c` vai a quase zero; o erro estacionário de 6% é relativo a um valor
  pequeno.

### Exploração (não muda o modelo nem o veredito)

Para entender as falhas, o simplificado foi rodado de novo trocando um parâmetro de cada vez.
**Isso não é uma proposta de correção:** os parâmetros são os da Julia, e mudá-los é decisão dela e
da Bárbara.

| Rodada | Erro est. `NLRP3a` | Erro est. `IL18c` | Erro est. `IL1be` | NRMSE `IL1be` |
| --- | --- | --- | --- | --- |
| simplificado como está | 7,84% | 6,07% | 26,3% | 19,8% |
| `j = 0,08/0,084` | 7,84% | 6,07% | 0,34% | 11,8% |
| `novodelta1 = 0,002` | 0,76% | 56,0% | 23,5% | 21,5% |
| os dois | 0,76% | 56,0% | 4,08% | 21,3% |

(Tolerâncias 1e-10/1e-12, fora da biblioteca, por isso `IL18c` difere na terceira casa do
relatório.)

Leitura:

1. **`j = 0,952` acerta o valor final de `IL1be`, mas não a curva** (NRMSE de 11,8%). Tirar `IL1bc`
   também tira o atraso entre a clivagem e a secreção, e isso o fator `j` não compensa.
2. **`novodelta1` parece calibrado.** Voltar ao `delta1` do original melhora `NLRP3a` e piora muito
   `IL18c`. Ou seja, o `0,0025` compensa outra coisa (provavelmente o atraso perdido com `NLRP3i`).
   O comentário do notebook ("j * delta1 = 1.25 * 0.002") não bate com `j = 0,7`.

Perguntas abertas: questão 56 de `docs/questoes-em-aberto.md`.
