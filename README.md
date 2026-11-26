# reducheck

O **reducheck** é uma biblioteca em Python que verifica se um modelo de equações diferenciais
ordinárias (EDOs) simplificado ainda se comporta como o original.

Simplificar um modelo é abrir mão de parte dele, e cada trabalho costuma avaliar o resultado com
a sua própria métrica e o seu próprio limite. O reducheck padroniza essa avaliação. Você entrega
três arquivos:

- o modelo original, em SBML;
- o modelo simplificado, em SBML;
- um arquivo de configuração em YAML, que diz quais variáveis comparar, como elas se
  correspondem nos dois modelos e quais critérios e limites usar.

A biblioteca simula os dois modelos nas mesmas condições, aplica cada critério e devolve um
**veredito**: APROVADO, APROVADO COM RESSALVAS ou REPROVADO. Cada critério vem com a sua razão,
e o relatório traz os arquivos necessários para refazer a análise.

> Trabalho de Conclusão de Curso em Ciência da Computação (UFJF), de Isabella Mourão Dias.
> Versão `0.3.0`.

## Como funciona

Uma verificação passa por seis etapas:

1. **Leitura da configuração.** O YAML é conferido antes de qualquer simulação. Um nome errado,
   um campo faltando ou uma variável que não existe no modelo param a execução com uma mensagem
   que diz qual é o campo.
2. **Simulação.** Os dois modelos são simulados com o libRoadRunner, com os **mesmos** instantes
   de tempo, integrador e tolerâncias. Uma simulação extra do original mede o erro do próprio
   integrador (o ruído numérico).
3. **Mapeamento.** As variáveis dos dois modelos são casadas: uma para uma, por soma ou por soma
   ponderada.
4. **Métricas e análise qualitativa.** As métricas comparam as trajetórias. Se a configuração
   pedir, a biblioteca também compara o equilíbrio e a estabilidade local dos dois modelos.
5. **Veredito.** Cada critério é comparado com o seu limite, e os resultados viram o veredito.
6. **Relatório.** O resultado é gravado em JSON, HTML ou Markdown, junto com as séries simuladas
   e a configuração usada.

## Instalação

Requer Python 3.11 ou superior.

```bash
git clone https://github.com/isasmourao/tcc-reducheck.git
cd tcc-reducheck
python -m venv .venv
source .venv/bin/activate        # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Para conferir: `reducheck --versao` deve imprimir `reducheck 0.3.0`.

No Git Bash do Windows, se os acentos aparecerem trocados (`Crit�rios`), rode antes
`export PYTHONIOENCODING=utf-8`. No PowerShell eles saem certos.

## Exemplo de 5 minutos

O par de brinquedo `aggregation`, em [tests/fixtures/](tests/fixtures/), tem dois compartimentos
`X1` e `X2` com entrada constante e decaimento de primeira ordem, com taxas parecidas (`0,20` e
`0,22`). O simplificado junta os dois num único `X = X1 + X2`, com a taxa média. A pergunta é se
`X` do simplificado acompanha `X1 + X2` do original.

A configuração está em [exemplos/minimo.yaml](exemplos/minimo.yaml):

```yaml
versao: 1

modelos:
  original: ../tests/fixtures/aggregation_original.xml
  simplificado: ../tests/fixtures/aggregation_simplified.xml

simulacao:
  t_fim: 50
  pontos: 501

variaveis:
  - nome: X
    original: [X1, X2]
    simplificado: X

criterios:
  - metrica: nrmse
    limite: 0.05
    variaveis: [X]

relatorio:
  formatos: [html, json]
```

Em palavras: simular os dois modelos de `t = 0` a `t = 50` com 501 pontos, comparar a soma
`X1 + X2` do original com o `X` do simplificado, e aceitar se o NRMSE for no máximo 5%. Os
caminhos são relativos ao próprio YAML.

Da raiz do repositório:

```bash
reducheck verificar exemplos/minimo.yaml
```

```text
Veredito   APROVADO
Critérios  1 de 1 atendidos (100,0%) · obrigatórios 1/1 · desejáveis 0/0
  Trajetória   APROVADO · 1 de 1 · obrigatórios 1/1
  Longo prazo  não verificada
Falhas     nenhuma

Relatório  C:\...\exemplos\resultados\relatorio.html
Avisos     1 (no relatório)
```

Para abrir o relatório no navegador assim que ele for gerado, acrescente `--abrir`:

```bash
reducheck verificar exemplos/minimo.yaml --abrir
```

Sem a opção, abra o `relatorio.html` com dois cliques no Explorador de Arquivos, ou pelo terminal
(`start` no Windows, `open` no macOS, `xdg-open` no Linux).

O NRMSE medido em `X` é 0,00523 (0,5%), dez vezes abaixo do limite: a agregação não é exata
(`0,20 ≠ 0,22`), mas as escalas são próximas. Abra o `relatorio.html` para ver a tabela, o gráfico
das duas trajetórias e o aviso (o ruído numérico de referência, explicado abaixo).

Para começar o seu: copie [exemplos/config_exemplo.yaml](exemplos/config_exemplo.yaml), que tem
todos os campos comentados, e troque os modelos e as variáveis.

### Pelo Python

```python
import reducheck

resultado = reducheck.verificar("exemplos/minimo.yaml")
resultado.nivel        # 'APROVADO'
resultado.aprovado     # True só no APROVADO sem ressalvas
resultado.porcentagem  # 100.0
for item in resultado.criterios:
    print(item.metrica, item.variavel, item.valor, item.limite, item.passou)
resultado.series["X"]  # as duas séries de X, já na mesma malha, para plotar
```

`reducheck.verificar(caminho, pasta_de_saida=...)` faz o mesmo que `--saida` na linha de comando.

## Como ler o relatório

**O original é a referência de tudo.** Cada métrica mede quanto o simplificado se afasta do
original: a faixa, o valor final e o equilíbrio usados para normalizar o erro são sempre os do
original. A comparação não é simétrica (trocar os dois modelos de lugar no YAML muda os números),
e o resultado só é tão bom quanto o modelo original: a biblioteca verifica a fidelidade ao
original, não compara com dados experimentais. A única medida que não envolve o simplificado é o
ruído numérico, que compara o original com ele mesmo.

**Uma verificação responde a duas perguntas**, e o relatório mostra cada uma separada:

| Pergunta | Critérios | O que ela não vê |
| --- | --- | --- |
| **Trajetória**: o simplificado faz o mesmo caminho que o original, dentro do tempo simulado? | as métricas (`nrmse`, `mape`, `erro_estacionario`, ...) | para onde os modelos iriam depois do fim da simulação |
| **Longo prazo**: se os dois continuassem rodando, parariam no mesmo lugar, e do mesmo jeito? | `equilibrio`, `estabilidade_local` e `comportamento_longo_prazo` | o caminho; o equilíbrio pode estar muito depois do tempo simulado |

As duas ficam no mesmo YAML e saem no mesmo relatório, com um comando só. Uma pergunta sem
nenhum critério declarado aparece como "não verificada". O `relatorio.html` tem abas: **Resumo**
(o resultado de cada pergunta e uma leitura das duas juntas, que aponta, por exemplo, as
variáveis que erram o caminho e acertam o equilíbrio), **Trajetória** (critérios, razões e
gráficos), **Longo prazo** (equilíbrio e estabilidade) e **O que cada um mede** (as duas
perguntas e cada métrica usada, em palavras simples). O veredito do topo junta as duas: um
obrigatório que falha em qualquer uma reprova o modelo. O terminal mostra uma linha por pergunta,
e o `resultado.json` traz as contagens de cada uma em `por_pergunta`.

Nas abas Trajetória e Longo prazo há uma barra de filtro por variável: por padrão tudo aparece;
escolhendo uma ou mais variáveis, a tabela de critérios, as razões, os avisos de cada item e os
gráficos passam a mostrar só essas. O que vale para o modelo inteiro (a estabilidade local)
continua sempre visível.

### O veredito

Cada par (critério, variável) é um **item**. Dois critérios aplicados a três variáveis são seis
itens, e a porcentagem conta itens.

| Veredito | Regra |
| --- | --- |
| APROVADO | todos os itens passaram |
| APROVADO COM RESSALVAS | todos os obrigatórios passaram, mas algum desejável (`obrigatorio: false`) falhou |
| REPROVADO | pelo menos um item obrigatório falhou, **qualquer que seja a porcentagem** |

Com `relatorio.niveis: 2`, APROVADO COM RESSALVAS vira APROVADO; nenhuma medida muda.

Um **erro** nunca é veredito. Configuração inválida, simulação que falhou, valor `NaN` ou variável
negativa param a execução com uma mensagem que diz o campo, a variável ou o instante.

### No terminal

`reducheck verificar` imprime um resumo curto (o veredito, as contagens, até três falhas de cada
tipo, uma por linha, e o caminho do relatório) e sai com um código que pode ser usado em scripts.
Num terminal o resumo sai colorido; num arquivo, num pipe ou com a variável `NO_COLOR` definida,
sai em texto puro.

| Código | Significado |
| --- | --- |
| 0 | APROVADO |
| 1 | APROVADO COM RESSALVAS |
| 2 | REPROVADO |
| 3 | erro (configuração, mapeamento, métrica ou simulação); a mensagem vai para o stderr |

Um exemplo de reprovação, com o par `qssa_fail` (uma QSSA aplicada sem separação de escalas de
tempo):

```bash
reducheck verificar tests/fixtures/config_qssa_fail.yaml
```

```text
Veredito   REPROVADO
Critérios  1 de 2 atendidos (50,0%) · obrigatórios 1/2 · desejáveis 0/0
  Trajetória   REPROVADO · 1 de 2 · obrigatórios 1/2
  Longo prazo  não verificada

Falhas obrigatórias (1 de 2)
  × nrmse  C  52%  limite 5%  erro em t = 4,9 a 28,8 (ao longo da simulação)

Relatório  C:\...\tests\fixtures\resultados\resultado.json
Avisos     1 (no relatório)
```

A razão completa de cada falha (quanto acima do limite e o erro no transiente e no estado
estacionário) está no relatório.

### A razão de cada falha

A razão diz **quanto** o item errou (valor, limite e quanto acima do limite) e **onde** no tempo.
"Onde" é a menor janela que concentra 80% do erro acumulado. Ela é chamada de **transiente** se
cabe nos primeiros 20% do tempo simulado, de **estado estacionário** se cabe nos últimos 20%, e
de **ao longo da simulação** nos outros casos. Depois vem o valor da mesma métrica em cada ponta.
Os 20% são uma convenção, não uma detecção de equilíbrio. `erro_estacionario` não tem janela,
porque não é uma soma ponto a ponto.

### Os avisos

Um aviso não muda o veredito: ele diz quando um número merece desconfiança.

- **Ruído numérico de referência**, sempre presente. O original é simulado uma segunda vez com
  tolerâncias 100× mais frouxas, e o NRMSE entre as duas execuções é o erro que o solver produz
  sozinho. Se um limite estiver a menos de 10× desse ruído, há um aviso a mais: o critério estaria
  medindo o solver, não a simplificação.
- **Métrica inadequada.** O MAPE avisa quando descartou pontos perto de zero ou quando mais de 5%
  dos pontos usados estão abaixo de 1% do pico. O NRMSE avisa quando um único ponto responde por
  mais de 50% do erro quadrático.
- **Análise qualitativa.** Ela avisa que só um equilíbrio foi analisado e em que instante ele foi
  alcançado (ver [`equilibrio`](#equilibrio)).

### Os arquivos

Tudo vai para `relatorio.pasta` (padrão `resultados/`, ao lado do YAML), ou para a pasta de
`--saida`.

| Arquivo | Quando | Para quê |
| --- | --- | --- |
| `relatorio.html` | `html` em `formatos` | leitura: veredito, tabela (falhas primeiro), razões, avisos, gráficos e dados da execução, num arquivo só |
| `relatorio.md` | `md` em `formatos` | o mesmo relatório em Markdown, com os gráficos ligados aos PNG |
| `graficos/<variável>.png` | `html` ou `md` | original (contínua) e simplificado (tracejada) em cima, erro absoluto embaixo; 300 dpi |
| `resultado.json` | `json` em `formatos` (é o padrão) | para código: `veredito`, `porcentagem`, `obrigatorios`, `desejaveis`, `razoes`, `avisos`, `ruido_numerico`, `qualitativo`, `criterios[]` (valor, limite, razão, diagnóstico) e `execucao` (data, versões, SHA-256 dos dois SBML) |
| `series.csv` | sempre | tempo e as duas séries de cada variável **mapeada** (a soma, não `X1` e `X2` separados), com todos os dígitos |
| `config_usada.yaml` | sempre | a configuração efetiva, com os padrões preenchidos e os caminhos absolutos |

`config_usada.yaml` refaz a análise **na mesma máquina**:

```bash
reducheck verificar resultados/config_usada.yaml --saida resultados/repeticao
```

Use sempre `--saida`. Sem ela, a nova execução escreve na pasta da execução original e sobrescreve
os arquivos, inclusive o próprio `config_usada.yaml`. Em outra máquina, troque os dois caminhos de
`modelos`. O SHA-256 no bloco `execucao` do `resultado.json` confirma que os arquivos são os
mesmos.

## Referência da configuração

Regras gerais:

- uma chave desconhecida é erro, com sugestão do nome mais parecido (`simulaco` → `simulacao`);
- caminhos são relativos ao YAML;
- números aceitam notação científica (`1e-8`);
- toda mensagem de erro diz o caminho do campo, como `variaveis[2].original`.

A tabela abaixo é gerada do esquema da biblioteca. Para regenerá-la depois de mudar um campo em
[src/reducheck/config.py](src/reducheck/config.py), rode `python docs/atualizar_referencia.py`.
Um teste falha se ela ficar desatualizada.

<!-- referencia:inicio -->
| Campo | Tipo | Padrão | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `versao` | `1` | **obrigatório** | Versão do formato do arquivo. Hoje só existe a 1. | `1` |
| `modelos` | bloco | **obrigatório** | Os dois modelos comparados. | — |
| `modelos.original` | caminho | **obrigatório** | Arquivo SBML do modelo original, relativo ao YAML. | `modelos/original.xml` |
| `modelos.simplificado` | caminho | **obrigatório** | Arquivo SBML do modelo simplificado, relativo ao YAML. | `modelos/simplificado.xml` |
| `simulacao` | bloco | **obrigatório** | Condições de simulação, iguais para os dois modelos. | — |
| `simulacao.t_inicio` | número | `0` | Instante inicial, na unidade de tempo dos modelos. | `0` |
| `simulacao.t_fim` | número | **obrigatório** | Instante final, na unidade de tempo dos modelos (por exemplo, dias); tem que ser maior que `t_inicio`. | `720` |
| `simulacao.pontos` | inteiro (≥ 2) | **obrigatório** | Número de instantes salvos entre `t_inicio` e `t_fim`, igualmente espaçados e contando as duas pontas. Os dois modelos usam a mesma malha. | `1000` |
| `simulacao.solver` | texto | `cvode` | Integrador. Só `cvode` está disponível. | `cvode` |
| `simulacao.tol_relativa` | número (> 0) | `1e-08` | Tolerância relativa do solver. | `1e-8` |
| `simulacao.tol_absoluta` | número (> 0) | `1e-10` | Tolerância absoluta do solver. | `1e-10` |
| `simulacao.sobrescrever` | bloco | — | Valores que substituem os do SBML. O que está direto aqui vale para os dois modelos. | — |
| `simulacao.sobrescrever.parametros` | mapa texto → número | `{}` | Parâmetros do SBML trocados antes de simular (nome → valor). | `{k1: 0.5}` |
| `simulacao.sobrescrever.condicoes_iniciais` | mapa texto → número | `{}` | Condições iniciais de espécies trocadas antes de simular (nome → valor). | `{A: 2.0}` |
| `simulacao.sobrescrever.original` | bloco | — | Trocas só no modelo original; vencem as comuns. | — |
| `simulacao.sobrescrever.original.parametros` | mapa texto → número | `{}` | Parâmetros do SBML trocados antes de simular (nome → valor). | `{k1: 0.5}` |
| `simulacao.sobrescrever.original.condicoes_iniciais` | mapa texto → número | `{}` | Condições iniciais de espécies trocadas antes de simular (nome → valor). | `{A: 2.0}` |
| `simulacao.sobrescrever.simplificado` | bloco | — | Trocas só no modelo simplificado; vencem as comuns. | — |
| `simulacao.sobrescrever.simplificado.parametros` | mapa texto → número | `{}` | Parâmetros do SBML trocados antes de simular (nome → valor). | `{k1: 0.5}` |
| `simulacao.sobrescrever.simplificado.condicoes_iniciais` | mapa texto → número | `{}` | Condições iniciais de espécies trocadas antes de simular (nome → valor). | `{A: 2.0}` |
| `simulacao.nao_negativas` | booleano | `true` | Se `true`, uma variável negativa (além da precisão do solver) interrompe a verificação com erro. | `false` |
| `variaveis` | lista de blocos (pelo menos 1 item) | **obrigatório** | Como casar as variáveis dos dois modelos, uma por item. | — |
| `variaveis[].nome` | texto | **obrigatório** | Nome usado no relatório; pode ser diferente dos nomes nos modelos. | `M` |
| `variaveis[].original` | texto ou lista de texto ou mapa texto → número | **obrigatório** | Variável do original: um nome, uma lista (soma) ou um mapa nome → peso (soma ponderada). | `Mo`, `[Mo, M1, M2]`, `{C1: 1.0, C2: 0.5}` |
| `variaveis[].simplificado` | texto ou lista de texto ou mapa texto → número ou `null` | `null` | Contrapartida no simplificado, nas mesmas formas. `null` quando a simplificação eliminou a variável (exige `core: false`). | `M`, `null` |
| `variaveis[].core` | booleano | `true` | Se a variável é essencial ao propósito do modelo; `variaveis: core` nos critérios seleciona estas. | `false` |
| `criterios` | lista de blocos (pelo menos 1 item) | **obrigatório** | Critérios de aceitação. Cada par (critério, variável) é um item do veredito. | — |
| `criterios[].metrica` | texto | **obrigatório** | Nome de uma métrica registrada ou de uma análise qualitativa. | `nrmse`, `estabilidade_local` |
| `criterios[].limite` | número ou `null` (> 0) | `null` | Maior erro aceito, inclusivo (passa com valor igual ao limite). Obrigatório, exceto em `estabilidade_local` e `comportamento_longo_prazo`, que não o aceitam. | `0.05` |
| `criterios[].variaveis` | lista de texto ou `core` ou `null` | `null` | Nomes declarados em `variaveis`, ou `core` para todas as core. Obrigatório, exceto em `estabilidade_local` e `comportamento_longo_prazo`, que não o aceitam. | `[D, M]`, `core` |
| `criterios[].obrigatorio` | booleano | `true` | Se a falha reprova o modelo (`true`) ou só gera ressalva (`false`, desejável). | `false` |
| `criterios[].parametros` | mapa texto → número | `{}` | Opções da própria métrica (ver a seção de métricas). | `{epsilon: 1e-6}`, `{fracao_final: 0.1}` |
| `relatorio` | bloco | — | O que escrever, e onde. | — |
| `relatorio.formatos` | lista de texto | `[json]` | Quais relatórios escrever: `json`, `html` e `md`, em qualquer combinação. | `[html, json]` |
| `relatorio.pasta` | caminho | `resultados` | Pasta de saída, relativa ao YAML. `--saida` na linha de comando a substitui. | `resultados/simp1` |
| `relatorio.niveis` | `2` ou `3` | `3` | Níveis do veredito; `2` junta APROVADO COM RESSALVAS em APROVADO. | `2` |
<!-- referencia:fim -->

### Mapeamento das variáveis

| Forma | YAML | Compara |
| --- | --- | --- |
| 1:1 | `original: A` | `A` |
| soma | `original: [Mo, M1, M2]` | `Mo + M1 + M2` |
| soma ponderada | `original: {C1: 1.0, C2: 0.5}` | `1,0·C1 + 0,5·C2` |
| eliminada | `simplificado: null` e `core: false` | nada (fica registrada, sem critério) |

As três primeiras valem dos dois lados. Uma variável eliminada por QSSA que continua no
simplificado como regra de atribuição (`B := k1·A/k2`) é comparada normalmente, pelo nome.
Expressões (`C1 + C2`, razões, funções) são recusadas na validação.

## Métricas e critérios

Todas as métricas comparam a série original `o` com a simplificada `s` nos mesmos `n` pontos. Em
todas, **menor é melhor** e 0 é idêntico. Os valores em fração leem-se como porcentagem:
`0.05` = 5%.

| Nome | Tipo | Fórmula | Unidade | Parâmetros | Fonte | Limite base da literatura |
| --- | --- | --- | --- | --- | --- | --- |
| `nrmse` | quantitativa | $\sqrt{\frac1n\sum(o_i-s_i)^2}\,/\,(\max o - \min o)$ | fração | — | — | sem limite na literatura |
| `rmse` | quantitativa | $\sqrt{\frac1n\sum(o_i-s_i)^2}$ | unidade da variável | — | Chai & Draxler (2014) | sem limite na literatura |
| `mape` | quantitativa | $\frac{1}{\lvert I\rvert}\sum_{i\in I}\lvert o_i-s_i\rvert/\lvert o_i\rvert$ | fração | `epsilon` | Hyndman & Koehler (2006), para a exclusão perto de zero | sem limite na literatura |
| `erro_max_abs` | quantitativa | $\max_i\lvert o_i-s_i\rvert$ | unidade da variável | — | — | sem limite na literatura |
| `erro_max_rel` | quantitativa | $\max_{i\in I}\lvert o_i-s_i\rvert/\lvert o_i\rvert$ | fração | `epsilon` | Snowden et al. (2017a) | 0,05 |
| `erro_estacionario` | quantitativa | $\lvert\bar o-\bar s\rvert/\lvert\bar o\rvert$ | fração | `fracao_final` | — | sem limite na literatura |
| `erro_integral` | quantitativa | $\frac1T\int_0^T\lvert 1-s/o\rvert\,dt$ | fração | `epsilon` | Rao et al. (2014), eq. 14 | 0,10 |
| `erro_simetrico` | quantitativa | $\frac12\left[I(s,o)+I(o,s)\right]$ | fração | `epsilon` | Frøysa et al. (2018), eqs. 3–4 | sem limite no artigo; 0,10 derivado de Rao (2014) |
| `erro_l2_rel` | quantitativa | $\lVert o-s\rVert_{L^2}/\lVert o\rVert_{L^2}$ | fração | — | Vejchodský (2014), Tabela 1 | sem limite na literatura |
| `equilibrio` | qualitativa | $\lvert o^*-s^*\rvert/\lvert o^*\rvert$ no equilíbrio | fração | — | — | sem limite na literatura |
| `estabilidade_local` | qualitativa | classificação dos autovalores da Jacobiana | estável / instável / marginal | — | — | sem limite (compara classificações) |
| `comportamento_longo_prazo` | qualitativa | os dois chegam a um equilíbrio, ou nenhum chega | chega / não chega | — | Waldherr et al. (2007); Vejchodský (2014) | sem limite (compara rótulos) |

"Sem limite na literatura" quer dizer que nenhum artigo consultado dá um número; os limites de
[estudo_de_caso/simp1_criterios_propostos.yaml](estudo_de_caso/simp1_criterios_propostos.yaml)
para essas métricas são convenção do TCC.
As integrais (`erro_integral`, `erro_simetrico`, `erro_l2_rel`) usam a regra do trapézio na malha
de tempo, que não precisa ser uniforme. Um exemplo com os limites da literatura está em
[exemplos/limites_da_literatura.yaml](exemplos/limites_da_literatura.yaml).

### `nrmse`

$$\mathrm{NRMSE} = \frac{\sqrt{\frac{1}{n}\sum_i (o_i - s_i)^2}}{\max_i o_i - \min_i o_i}$$

RMSE normalizado pela **amplitude** do original. É a métrica de trajetória padrão, adequada a
variáveis que passam por zero porque não divide ponto a ponto. Recusa uma série original constante,
porque a amplitude seria zero. Há outras formas de normalizar o RMSE (pela média ou pelo
desvio-padrão); o reducheck usa a amplitude.

### `mape`

$$\mathrm{MAPE} = \frac{1}{|I|}\sum_{i \in I}\frac{|o_i - s_i|}{|o_i|},\qquad I = \{\, i : |o_i| \ge \varepsilon \,\}$$

Erro relativo médio. Use quando a pergunta for "quantos por cento erra, em média" e a variável
ficar longe de zero. Os pontos com `|o| < epsilon` ficam de fora, e o relatório diz quantos.
`epsilon` padrão: `10⁻⁶ · max|o|`; `parametros: {epsilon: ...}` dá um valor absoluto. Perto de
zero, uma diferença pequena vira um erro relativo enorme. Nesse caso prefira `nrmse` ou
`erro_max_abs`.

### `erro_max_abs`

$$E_{\max} = \max_i |o_i - s_i|$$

O pior ponto, na unidade da variável, e em que instante ele acontece. Use quando existe um erro
aceitável em unidades físicas, ou quando a variável passa por zero e nenhuma métrica relativa se
aplica.

### `erro_max_rel`

$$E^{\mathrm{rel}}_{\max} = \max_{i \in I}\frac{|o_i - s_i|}{|o_i|},\qquad I = \{\, i : |o_i| \ge \varepsilon \,\}$$

O pior ponto em valor relativo, com a mesma proteção e o mesmo `epsilon` do MAPE. Responde "quanto
erra no pior momento". Um transiente curto e ruim aparece aqui e se dilui no MAPE. É exigente: no
par `qssa_ok`, aprovado por NRMSE (0,00072), ele vale 0,247 por causa dos primeiros instantes.

### `erro_estacionario`

$$E_{\mathrm{ee}} = \frac{|\bar o - \bar s|}{|\bar o|}$$

Erro relativo no fim da simulação. `bar o` e `bar s` são as médias na fração final `fracao_final`
do **tempo** (padrão `0`: só o último ponto). Use quando o que importa é onde o sistema chega,
independentemente do caminho. Um `fracao_final` como `0.1` estabiliza o número se a trajetória
ainda oscila. Recusa um valor final zero; nesse caso use `erro_max_abs`.

### `rmse`

$$\mathrm{RMSE} = \sqrt{\frac{1}{n}\sum_i (o_i - s_i)^2}$$

O numerador do `nrmse`, na unidade da variável (`rmse = nrmse × (max o − min o)`). Não compare
nem some valores de variáveis diferentes. Chai & Draxler (2014) concluem que nenhuma métrica basta
sozinha. Sem limite na literatura, porque depende da escala da variável.

### `erro_integral`

$$I = \frac{1}{T}\int_0^T \left|1 - \frac{s(t)}{o(t)}\right| dt \approx \frac{\sum_{i \in I} w_i\,\frac{|o_i - s_i|}{|o_i|}}{\sum_{i \in I} w_i}$$

Erro relativo médio integrado no tempo (Rao et al., 2014, eq. 14), com os pesos `w_i` do
trapézio e a mesma exclusão perto de zero (e o mesmo `epsilon`) do `mape`. Em Rao a integral
também é tirada a média sobre as espécies importantes; aqui cada variável é um item e tem de passar
sozinha. Rao parou a redução em `I = 0,1` e viu diferenças visuais claras com `0,2`. O resultado
depende da janela `[0, T]` simulada. **Limite base: 0,10 (Rao et al., 2014).**

### `erro_simetrico`

$$E = \tfrac12\left[I(s, o) + I(o, s)\right],\qquad I(x_r, x_f) = \frac{1}{T}\int_0^T \left|1 - \frac{x_r(t)}{x_f(t)}\right| dt$$

A média do `erro_integral` dividindo pelo original e do mesmo erro dividindo pelo simplificado
(Frøysa et al., 2018, eqs. 3–4). Os dois termos usam os mesmos pontos: sai o ponto em que o
original **ou** o simplificado está perto de zero. O relatório mostra os dois termos
(`I_original`, `I_simplificado`). Frøysa usa a medida para agrupar e ranquear reduções, e não dá
limite. **0,10 é derivado de Rao (2014)**, porque `E` é a média de duas integrais de Rao. Atenção:
se o simplificado fica muito menor que o original em algum trecho, o termo que divide pelo
simplificado explode, e o valor pode passar de 100%.

### `erro_l2_rel`

$$E = \frac{\lVert o - s\rVert_{L^2(0,T)}}{\lVert o\rVert_{L^2(0,T)}} = \sqrt{\frac{\int_0^T (o - s)^2\,dt}{\int_0^T o^2\,dt}}$$

Erro relativo na norma L² (Vejchodský, 2014, Tabela 1), pelo trapézio. Não exclui ponto nenhum,
porque a norma é da série inteira: serve para variáveis que começam em zero, como `M1`. Vejchodský
alinha período e fase antes de calcular; aqui não há alinhamento, então um atraso conta como erro.
Números do artigo, como referência: QSSA padrão 92,7%, QSSA com atraso 19%. Sem limite na
literatura. Recusa um original identicamente zero; nesse caso use `erro_max_abs`.

### `equilibrio`

Para cada variável mapeada, o erro relativo entre o **ponto de equilíbrio** dos dois modelos, com
`limite` e `variaveis` como numa métrica. O equilíbrio é o que o sistema alcança a partir das
condições iniciais da configuração, e só esse: a biblioteca não procura todos os equilíbrios.
Encontrá-lo pode exigir integrar muito além de `t_fim` (no modelo de Verly (2025), cem vezes o
tempo simulado), e o relatório diz em que instante ele foi alcançado. Leia o critério como uma afirmação
sobre o longo prazo, não sobre a janela simulada. Numa variável que vai a zero nos dois modelos, o
erro relativo depende de onde a integração parou e pouco informa (questão 42 de
[docs/questoes-em-aberto.md](docs/questoes-em-aberto.md)).

### `estabilidade_local`

Um item único sobre o modelo inteiro, **sem** `limite` e **sem** `variaveis`. Calcula os
autovalores da Jacobiana no equilíbrio acima e classifica cada modelo como **estável** (toda
parte real negativa), **instável** (alguma positiva) ou **marginal** (nenhuma positiva, mas
alguma indistinguível de zero: abaixo de `10⁻⁶` vezes a maior parte real em módulo, onde a
linearização não decide). Passa quando os dois modelos recebem a mesma classificação. Compara a
classificação, e não os autovalores, porque o simplificado tem menos variáveis.

### `comportamento_longo_prazo`

Um item único sobre o modelo inteiro, **sem** `limite` e **sem** `variaveis`, como
`estabilidade_local`. Passa quando os dois modelos chegam a um equilíbrio, ou nenhum chega.
Waldherr et al. (2007) separam aproximar as quantidades de preservar a dinâmica qualitativa, e
Vejchodský (2014) mostra o mesmo comportamento com 30% de erro no período: este critério não
substitui as métricas. Hoje, se um dos modelos não acha equilíbrio, a análise qualitativa para com
erro antes de chegar a este critério, então na prática ele só aparece passando.

Declarar `equilibrio`, `estabilidade_local` ou `comportamento_longo_prazo` é o que liga a análise
qualitativa; sem eles, nada de equilíbrio é calculado. Exemplo com `equilibrio` e
`estabilidade_local`:
[tests/fixtures/config_qualitativo.yaml](tests/fixtures/config_qualitativo.yaml).

### Qual usar

- Comece com `nrmse` nas variáveis core: é robusto e funciona com variáveis que começam em zero.
- Acrescente `erro_estacionario` se o estado final importa para o propósito do modelo.
- Use `mape` ou `erro_max_rel` só em variáveis longe de zero e leia os avisos.
- Use `erro_max_abs` quando houver uma tolerância em unidades físicas.
- Para usar um limite publicado, `erro_integral` (0,10, Rao et al., 2014) e `erro_max_rel`
  (0,05, Snowden et al., 2017a) são os que têm número na literatura.
- Marque como desejável (`obrigatorio: false`) o que é bom ter, mas não reprova a simplificação.
- Declare os critérios **antes** de ver os resultados. Ajustar o limite até passar invalida a
  verificação.

## Como adicionar uma métrica

Uma métrica é uma função `(tempo, original, simplificado, **opções)` que devolve um
`ResultadoDeMetrica`, registrada com `@registrar("nome")`. As opções são argumentos com valor
padrão, e o YAML passa a aceitá-las em `parametros` sem mais nada. Ela pode morar fora da
biblioteca, num arquivo seu.

Exemplo: o erro absoluto médio, multiplicado por uma escala opcional. Rode da raiz do repositório:

```python
import numpy as np

import reducheck
from reducheck.metrics import ResultadoDeMetrica, registrar


@registrar("erro_medio_abs")
def erro_medio_abs(tempo, original, simplificado, escala: float = 1.0):
    """Erro absoluto médio entre as duas séries, multiplicado por 'escala'."""
    diferenca = escala * np.abs(np.asarray(original) - np.asarray(simplificado))
    return ResultadoDeMetrica(
        valor=float(np.mean(diferenca)),
        descricao="erro absoluto médio (na unidade da variável)",
        # Opcionais: o erro ponto a ponto e como ele se soma permitem que a razão de uma
        # falha diga em que janela de tempo o erro se concentra.
        erro_pontual=diferenca,
        agregacao="media",
    )


resultado = reducheck.verificar("exemplos/metrica_propria.yaml")
print(resultado.nivel)
for item in resultado.criterios:
    print(item.metrica, item.variavel, item.valor, item.passou)
```

E no YAML ([exemplos/metrica_propria.yaml](exemplos/metrica_propria.yaml)), ela é citada como
qualquer outra:

```yaml
criterios:
  - metrica: nrmse
    limite: 0.05
    variaveis: [X]
  - metrica: erro_medio_abs
    limite: 0.1
    variaveis: [X]
    parametros:
      escala: 1.0
```

Saída: `APROVADO`, com `erro_medio_abs` em `X` valendo 0,0241.

Regras que o registro confere (e recusa com mensagem):

- os três primeiros parâmetros se chamam `tempo`, `original` e `simplificado`;
- todo parâmetro depois deles tem valor padrão, porque o YAML pode omiti-lo;
- o nome não pode repetir o de uma métrica existente;
- se `erro_pontual` for dado, `agregacao` é `"media"`, `"raiz_da_media"` ou `"maximo"`.

E uma que fica por sua conta, porque nada a confere: agregar `erro_pontual` em todos os pontos
tem que devolver `valor`. Senão, os números da razão de uma falha não batem com o valor da tabela.

Para dizer que um número merece desconfiança sem parar a execução, devolva `avisos=("...",)`. Para
recusar uma série em que a métrica não se aplica, levante `reducheck.metrics.ErroDeMetrica`.

**Limitação:** uma métrica sua só é usável pelo Python, como acima. A linha de comando não carrega
código de fora da biblioteca, então `reducheck verificar` com `erro_medio_abs` no YAML para com
"a métrica 'erro_medio_abs' não está no registro".

## Estudos de caso

O reducheck foi avaliado em dois modelos reais, descritos no Capítulo 5 do TCC. Os modelos em
SBML estão em [modelos/](modelos/). Eles foram escritos em Antimony (os arquivos `.ant`) e
convertidos por `python modelos/build_sbml.py`.

**Modelo de Verly (2025).** Descreve a inflamação na consolidação de fraturas ósseas no contexto
da menopausa, com 11 variáveis. Os nomes das simplificações no TCC e os arquivos do repositório
se correspondem assim:

| No TCC | Configuração | O que muda | Veredito |
| --- | --- | --- | --- |
| Simplificação 1 | [estudo_de_caso/simp1_criterios_propostos.yaml](estudo_de_caso/simp1_criterios_propostos.yaml) | remove `Cm` e `Mc` (9 variáveis) | REPROVADO, 3 de 20 itens |
| Simplificação 2 | [estudo_de_caso/diag_sem_mc.yaml](estudo_de_caso/diag_sem_mc.yaml) | remove só `Mc` (10 variáveis) | APROVADO, 20 de 20 itens |

[estudo_de_caso/simp1.yaml](estudo_de_caso/simp1.yaml) é a primeira versão da configuração da
simplificação 1, revista antes da construção da simplificação 2 (ver o Capítulo 5 do TCC). Ela
também reprova a simplificação 1, com 7 de 21 itens.

**Modelo do inflamassoma NLRP3.** Um modelo de 13 variáveis e uma versão simplificada com 8, feita
em um trabalho de iniciação científica. Serve para mostrar que a biblioteca funciona em outro
modelo sem mudar o código. A mesma simplificação foi verificada com duas configurações:

| Configuração | Métricas | Veredito |
| --- | --- | --- |
| [estudo_de_caso/nlrp3/nlrp3_simp.yaml](estudo_de_caso/nlrp3/nlrp3_simp.yaml) | as do TCC (`nrmse`, `erro_estacionario`, `erro_max_abs`, `mape`) | REPROVADO, 19 de 24 itens |
| [exemplos/limites_da_literatura_nlrp3.yaml](exemplos/limites_da_literatura_nlrp3.yaml) | as da literatura (`erro_integral`, `erro_simetrico`, `erro_max_rel`) | REPROVADO, 9 de 24 itens |

Para refazer qualquer uma, da raiz do repositório:

```bash
reducheck verificar estudo_de_caso/simp1_criterios_propostos.yaml
```

Exemplos de relatório em HTML estão em [relatorios_exemplo/](relatorios_exemplo/). O GitHub
mostra o código do arquivo, e não a página: baixe o arquivo e abra no navegador.

## Limitações

O que a biblioteca **não** faz, por decisão de escopo:

- **Só SBML.** CellML e outros formatos não são lidos. Para usar outro formato, converta o
  modelo para SBML antes. O Antimony ajuda nisso: veja [modelos/](modelos/).
- **Só o integrador CVODE.**
- **Só mapeamentos lineares**: por nome, soma ou soma ponderada. Expressões como `C1/C2` ou
  `log(X)` são recusadas.
- **Um equilíbrio só**, o alcançado a partir das condições iniciais. A biblioteca não procura
  todos os equilíbrios nem faz análise de bifurcação.
- **Só estabilidade local**, pela linearização no equilíbrio.
- **Um cenário por verificação.** Cada verificação usa um conjunto de parâmetros e de condições
  iniciais. Para testar outro, use `simulacao.sobrescrever` e rode de novo.
- **Sem interface gráfica** e sem gerar simplificações: a biblioteca verifica uma simplificação
  que você já fez.
- **Métricas próprias só pelo Python** (veja a seção anterior).

Alguns valores são convenções do TCC, e não valores medidos: os limiares dos avisos (1%, 5% e
50%), a fronteira de 20% entre transiente e estado estacionário e os fatores 100 e 10 do ruído
numérico. Os detalhes estão em [docs/questoes-em-aberto.md](docs/questoes-em-aberto.md).

Por fim, o reducheck compara o modelo simplificado com o original, e não com dados
experimentais. Um veredito APROVADO diz que o simplificado é fiel ao original, e nada sobre a
validade biológica de nenhum dos dois.

## Desenvolvimento

```bash
pytest              # testes, inclusive os que rodam os exemplos deste README
ruff check .        # lint
```

Os testes rodam a cada alteração no GitHub, nas versões 3.11 e 3.12 do Python. As versões exatas
das dependências usadas nos resultados do TCC estão em
[requirements-lock.txt](requirements-lock.txt).

Documentos de apoio:

- [docs/produto.md](docs/produto.md): escopo, formato da entrada e da saída, regra do veredito;
- [docs/questoes-em-aberto.md](docs/questoes-em-aberto.md): decisões tomadas e pendentes;
- [CLAUDE.md](CLAUDE.md): estrutura de pastas e convenções do código.

## Como citar

Enquanto o TCC não é publicado, cite o software:

```bibtex
@misc{reducheck,
  author = {Isabella Mourão Dias},
  title  = {reducheck: verificação de modelos de EDOs simplificados},
  year   = {2026},
  note   = {Trabalho de Conclusão de Curso, Ciência da Computação, UFJF. Versão 0.3.0},
  url    = {https://github.com/isasmourao/tcc-reducheck}
}
```

Se usar o estudo de caso, cite também o modelo original:

> VERLY, Ana Clara. *Modelo in silico da remodelação óssea no contexto da osteoporose durante a
> menopausa*. Dissertação (Mestrado em Modelagem Computacional), Universidade Federal de Juiz de
> Fora, 2025.

Licença: MIT.
