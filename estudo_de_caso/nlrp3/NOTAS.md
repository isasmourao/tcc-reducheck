# Modelo da Julia para teste: NLRP3 original x simplificado

Escrito em 04/11/2026. Testa se a biblioteca é genérica, isto é, se ela roda num modelo que não é o
de Verly et al. (2024) **sem mudar o código dela**.

> **📝 Para o texto do TCC:** o roteiro da história (desconfiança → investigação → mudança de
> critérios → resultado) está na última seção, "Para escrever no TCC".

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

## Veredito (critérios provisórios, revisados em 04/11/2026)

**REPROVADO. 19 de 24 critérios (79,2%); obrigatórios 14/16, desejáveis 5/8. As duas falhas
obrigatórias são em `IL1be`.**

Os critérios foram escolhidos pelo comportamento de cada variável **no original**, com uma regra
fixada antes de rodar (detalhes no YAML e na questão 57 de `docs/questoes-em-aberto.md`). **Ainda
são provisórios**, para revisar com a Bárbara.

| Critério | Variáveis | Limite | Tipo |
| --- | --- | --- | --- |
| NRMSE | todas | 0,05 | obrigatório |
| erro estacionário | as que terminam no pico: `NLRP3o`, `ASCb`, `C1`, `IL18e`, `IL1be` | 0,01 | obrigatório |
| erro máximo absoluto | as que voltam a ~0: `NLRP3a`, `IL18c`, `proIL1b` | 0,05 (5% da escala unitária) | obrigatório |
| MAPE, com `epsilon = 0,05` | todas | 0,05 | desejável |

| Variável | NRMSE | Erro estacionário | Erro máx. abs. | MAPE |
| --- | --- | --- | --- | --- |
| `NLRP3a` | 2,83% | — | 0,045 | *9,37%* |
| `NLRP3o` | 1,52% | 0,08% | — | 1,57% |
| `ASCb` | 0,30% | 0,004% | — | 0,83% |
| `C1` | 0,22% | 0,0001% | — | 0,74% |
| `IL18c` | 1,41% | — | 0,031 | *7,67%* |
| `IL18e` | 0,75% | 0,000002% | — | 1,34% |
| `proIL1b` | 0,78% | — | 0,032 | 1,72% |
| `IL1be` | **19,8%** | **26,3%** | — | *30,2%* |

Em negrito, as falhas obrigatórias; em itálico, as desejáveis.

Pontos de atenção:

- **O erro máximo absoluto de `NLRP3a` (0,045) passou perto do limite (0,05).** É o efeito real da
  retirada de `NLRP3i`: `NLRP3a` sobe 1,5 min antes, na subida mais íngreme. Um limite um pouco
  mais rígido o reprovaria. O limite **não** foi ajustado para passar.
- **Os MAPE de `NLRP3a` e `IL18c` continuam falhando**, mesmo ignorando os pontos pequenos. São os
  atrasos reais de 1,5 e 0,9 min (diagnóstico, item 3), pequenos o bastante para o NRMSE aceitar.

### Veredito anterior, com os critérios copiados da Verly (histórico)

**REPROVADO. 12 de 24 (50,0%); obrigatórios 12/16, desejáveis 0/8.** Com NRMSE ≤ 5%, erro
estacionário ≤ 1% e MAPE ≤ 5% em **todas** as variáveis, falhavam também o erro estacionário de
`NLRP3a` (7,84%) e de `IL18c` (6,02%), e o MAPE de todas as variáveis. O diagnóstico abaixo mostrou
que essas falhas vinham de dividir por valores perto de zero, e não de infidelidade.

## Diagnóstico das falhas

Reproduzir: `python estudo_de_caso/nlrp3/diagnostico.py`. A pergunta era se as falhas vinham da
conversão, da calibração, do tratamento de números pequenos ou de infidelidade real.

**1. Conversão: descartada.** Os dois SBML reproduzem os notebooks com erro da ordem de 1e-8
(`referencia/nlrp3/comparar_sbml.py`).

**2. Números pequenos: a maior parte das falhas do veredito anterior.** O erro estacionário e o
MAPE dividem pelo valor do original, e os dois inflam quando ele está perto de zero.

| Variável | Final no original | Final / pico | Erro estacionário | Diferença final / pico |
| --- | --- | --- | --- | --- |
| `IL18c` | 2,6e-7 | 0,00005% | 6,0% | 0,000003% |
| `NLRP3a` | 2,8e-3 | 1,3% | 7,8% | 0,10% |

| | `NLRP3o` | `ASCb` | `C1` | `IL18e` | `proIL1b` |
| --- | --- | --- | --- | --- | --- |
| MAPE, todos os pontos | 10,4% | 10,1% | 9,0% | 9,5% | 5,5% |
| MAPE, pontos > 5% do pico | 1,6% | 0,8% | 0,7% | 1,3% | 1,8% |

**3. Calibração: `novodelta1` está certo, e é essencial.** A ASC só dispara quando `NLRP3o` passa
de 1, e no original ele termina em 1,0087 (questão 55, item c). Tirar `NLRP3i` muda quanto NLRP3
oligomeriza, e o `novodelta1` compensa:

| | `NLRP3o` final | Cruza 1 em | `ASCb` a 50% em |
| --- | --- | --- | --- |
| Original | 1,00868 | 99,9 min | 117,9 min |
| Simplificado (`novodelta1 = 0,0025`) | 1,00785 | 100,2 min | 117,9 min |
| Simplificado com `delta1 = 0,002` | 1,01171 | 85,8 min | 104,4 min |

Sem a recalibração, a cascata dispararia 14 min antes. A ressalva é que o ajuste vale para esta
entrada de NF-κB, e o modelo é muito sensível perto do limiar.

**4. Efeito real e pequeno: a retirada de `NLRP3i`.** `NLRP3i` vira `NLRP3a` em ~1,4 min
(`1/(k1 + delta1)`). Sem esse passo, `NLRP3a` sobe 1,5 min antes e `IL18c`/`IL18e` 0,9 min antes.
O NRMSE fica em 2,8% e 1,4%, dentro do limite.

**5. Infidelidade real: `IL1be`.** Tem duas partes:

- **quantidade:** `j = 0,7` contra `k5·G / (k5·G + delta2) = 0,08 / 0,084 ≈ 0,952` no original.
  A razão `0,7 / 0,952 ≈ 0,735` explica o erro final de 26%: `IL1be` termina em 0,580 no original
  e em 0,428 no simplificado;
- **tempo:** no original, o IL-1β passa ~12 min dentro da célula (`IL1bc`, `1/(k5·G + delta2)`)
  antes de sair. Sem esse compartimento, `IL1be` sobe 7,2 min antes.

**Nenhuma variável está errada ou estranha** na conversão. O que é estranho é de desenho do modelo
e já está na questão 55: o degrau da ASC em `NLRP3o = 1`, com `NLRP3o` terminando só 0,9% acima.

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
   `IL18c`. Ou seja, o `0,0025` compensa outra coisa. O diagnóstico (item 3 de "Diagnóstico das
   falhas") mostrou o quê: ele mantém `NLRP3o` cruzando o limiar 1 no mesmo instante do original.
   O comentário do notebook ("j * delta1 = 1.25 * 0.002") não bate com `j = 0,7`.

Perguntas abertas: questão 56 de `docs/questoes-em-aberto.md`.

## Para escrever no TCC

Lembrete para a Isabella (04/11/2026). É o roteiro de um episódio que vale contar em **Resultados
e Discussão** (issue #25) e citar na **Conclusão** (issue #26). Mostra a biblioteca sendo usada de
verdade: o primeiro veredito levantou uma desconfiança, a investigação separou as causas, e a
mudança de critérios deixou o veredito mais correto. Os números estão nas seções acima. Este texto
é rascunho de ideias, não texto final.

### 1. A desconfiança

O primeiro veredito, com os critérios copiados do estudo de caso da Verly (NRMSE ≤ 5%, erro
estacionário ≤ 1% e MAPE ≤ 5% em **todas** as variáveis), foi **REPROVADO, 12 de 24, com 4 falhas
obrigatórias e todos os 8 MAPE falhando**. Pelo resultado, quase nada no simplificado seria fiel.

Isso não batia com as curvas: nos gráficos, a maior parte das variáveis do simplificado se sobrepõe
à do original. A desconfiança foi: **o problema é o modelo ou a forma de medir?** Havia quatro
hipóteses:

1. erro na **conversão** dos notebooks para SBML;
2. erro na **calibração** do simplificado;
3. **números pequenos** distorcendo as métricas;
4. **infidelidade real** da simplificação.

### 2. A investigação

Cada hipótese foi testada separadamente (`diagnostico.py`):

- **Conversão: descartada.** Os dois SBML reproduzem os notebooks com erro da ordem de 1e-8.
- **Números pequenos: confirmada, e explica a maior parte das falhas.** O erro estacionário e o
  MAPE **dividem pelo valor do original**, e os dois inflam quando ele está perto de zero:
  - `IL18c` reprovava com 6% de erro final. O original termina em 2,6×10⁻⁷ e o simplificado em
    2,4×10⁻⁷. A diferença real é 0,000003% do pico da variável;
  - o MAPE de cinco variáveis caía de 5,5–10,4% para 0,7–1,8% quando os pontos abaixo de 5% do pico
    (as subidas, que começam em zero) saíam da conta.
- **Calibração: não era problema, era solução.** O `novodelta1` da Julia (0,0025 no lugar de
  0,002) mantém `NLRP3o` cruzando o limiar 1 no mesmo instante do original (100,2 contra 99,9 min).
  Sem ele, toda a cascata dispararia 14 min antes.
- **Infidelidade real: confirmada, mas localizada.** Ela está em `IL1be`, em duas partes:
  - a **quantidade** (`j = 0,7` contra 0,952 implícito no original faz IL1be terminar 26% abaixo);
  - o **tempo** (tirar o compartimento `IL1bc` antecipa a secreção em 7,2 min).

  Há também um efeito real, mas pequeno: a retirada de `NLRP3i` antecipa `NLRP3a` em 1,5 min.

### 3. O que era e o que mudou

| | Antes | Depois |
| --- | --- | --- |
| Regra | as mesmas métricas em todas as variáveis | a métrica escolhida pelo **comportamento da variável no original** |
| Curva inteira | NRMSE em todas | NRMSE em todas (não mudou) |
| Valor final | erro estacionário relativo em todas | erro estacionário só nas que **terminam no pico** |
| Variáveis que voltam a zero | erro estacionário relativo (inflava) | **erro máximo absoluto** (não divide por nada) |
| MAPE | desejável em todas, ignorando só valores < 1e-6 × pico (o padrão) | desejável em todas, ignorando valores < 0,05 |
| Veredito | REPROVADO, 12/24, 4 falhas obrigatórias | REPROVADO, 19/24, **2 falhas obrigatórias, as duas em IL1be** |

A regra foi fixada **antes** de rodar de novo, e os limites não foram ajustados ao resultado.

### 4. Por que isso melhorou

- **O veredito continua REPROVADO, e isso é o certo**, porque a infidelidade de `IL1be` é real. A
  mudança não "aprovou" a simplificação: só tirou os falsos positivos.
- **As razões agora apontam a causa verdadeira.** Antes, a lista de falhas misturava `IL1be` com
  artefatos numéricos, e quem lesse o relatório iria investigar `IL18c` e `NLRP3a` à toa. Agora a
  falha que sobra leva direto ao parâmetro `j`.
- **A métrica passa a medir o que importa em cada variável.** Para uma variável que termina num
  valor (IL-18 secretada), o valor final é a pergunta biológica. Para uma que sobe e volta a zero
  (IL-18 celular), a pergunta é o pulso, e o erro relativo no fim, que divide por quase zero, não
  responde a ela.
- **Não basta usar só o NRMSE.** Ele não infla, mas é uma média e dilui erros localizados. O valor
  final de `IL1be`, 26% abaixo, é a informação mais forte da análise e precisa de um critério
  próprio.

### 5. O que isso diz sobre a biblioteca (para a discussão)

- **Escolher métricas e limites é parte da verificação, não um detalhe.** Os mesmos dois modelos
  vão de "4 falhas" a "2 falhas" só pela escolha dos critérios. Liga com a decisão pendente 7 e a
  questão 57.
- **Os avisos do relatório ajudaram.** O relatório já avisava quantos pontos do MAPE estavam perto
  de zero, e foi isso que levantou a suspeita.
- **Limitações a declarar:**
  - a separação das variáveis por comportamento é feita à mão no YAML;
  - o limite do erro máximo absoluto depende da escala do modelo (0,05 só faz sentido porque aqui
    tudo é da ordem de 1);
  - uma métrica de erro final normalizada pela amplitude resolveria isso de forma geral, mas **não
    foi implementada** (trabalho futuro, questão 57).
- **Pendente antes de escrever:**
  - decidir com a Bárbara se a mesma regra vale para o estudo de caso da Verly, onde `C1` e `C2`
    também vão a zero (questão 42). Se valer, os resultados da Verly no texto mudam;
  - confirmar a origem e o objetivo do simplificado da Julia (questão 56, item c): se ele foi feito
    para reproduzir dados do artigo, e não o original, a interpretação do "REPROVADO" muda.
