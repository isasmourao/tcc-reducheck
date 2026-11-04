# Dúvidas sobre o modelo da Julia para teste (NLRP3)

**Pendente com a Bárbara** desde 04/11/2026. Resumo em `docs/questoes-em-aberto.md`, decisão
pendente 10 e questão 55.

Pontos encontrados na leitura de `nlrp3_original.ipynb` e na conversão para SBML. **Nenhum
deles mudou o modelo**: `modelos/nlrp3_original.ant` reproduz o notebook exatamente como está.

## 1. `nfkbn(0)` escrito sem `piecewise` (decisão de tradução, sem efeito no resultado)

No notebook, `nfkbn(t)` devolve 0.25 quando `t == 0` e, nos outros instantes, a fórmula
`S1*h*exp(-(ln(t/tau))^2/s) + nfkb0`. O caso especial só existe para evitar o aviso do numpy
sobre `log(0)`.

A primeira tradução usou `piecewise(0.25, time == 0, ...)`, mas o CVODE do libRoadRunner
recusou começar a integração com esse `piecewise` e `c = 1000` ("Initial ewt has component(s)
equal to zero"). Com `c = 10`, ou começando em `t = 1`, funcionava. Por isso o SBML usa só a
fórmula. Em `t = 0`, a aritmética IEEE dá `ln(0) = -inf`, `exp(-inf) = 0` e `nfkbn = nfkb0 =
0.25`, o mesmo valor do notebook, que também é o limite quando `t → 0`. O teste
`test_nfkb_input_is_025_at_time_zero` garante isso.

**Consequência para o modelo simplificado:** se ele tiver a mesma entrada, deve ser escrito do
mesmo jeito, sem `piecewise`.

## 2. As tolerâncias do notebook (`rtol = atol = 1e-4`) dão resultados com até 23 % de erro

Com as tolerâncias do notebook, o original difere de uma execução precisa (`rtol = 1e-10`,
`atol = 1e-12`) em, no máximo (normalizado pelo maior valor de cada variável):

| Variável | Erro relativo | | Variável | Erro relativo |
| --- | --- | --- | --- | --- |
| NLRP3i | 0.6 % | | proIL1b | 13.9 % |
| NLRP3a | 0.5 % | | IL1bc | **23.5 %** |
| NLRP3o | 0.1 % | | IL1be | 11.5 % |
| ASCf / ASCb | 6.7 % | | proIL18 | 18.2 % |
| proC1 / C1 | 4.5 % | | IL18c | **22.7 %** |
| | | | IL18e | 10.7 % |

O instante em que `NLRP3o` passa de 1 muda de 99.9 min (execução precisa) para 95.7 min
(notebook), e tudo o que vem depois (ASC, caspase-1, citocinas) se desloca no tempo.

**Pergunta:** os gráficos e os resultados que vão ser usados no texto vêm do notebook com
`1e-4`? Se sim, eles precisam ser refeitos com tolerâncias menores. A biblioteca sempre simula
os dois modelos com as mesmas tolerâncias, apertadas, então ela vai comparar com a execução
precisa, e não com os gráficos do notebook.

## 3. O acionamento da ASC depende de `NLRP3o` passar de 1 por menos de 1 %

`sinal(NLRP3o) = 1 / (1 + ((NLRP3o + a)/b)^(-c))`, com `a = 1`, `b = 2` e `c = 1000`, é um
degrau quase perfeito em `NLRP3o = b - a = 1`. Na execução precisa, `NLRP3o` cresce até
~1.0087 em 300 min. Ou seja, ele passa do limiar por menos de 1 %, e é isso que dispara toda a
parte de baixo da cascata.

- Com `NLRP3o = 1.0087`, `sinal ≈ 0.987`. Com `NLRP3o = 0.99`, `sinal ≈ 7e-3`.
- Por isso o modelo é muito sensível a pequenos erros em `NLRP3o`. Isso explica o item 2.

**Perguntas:** isso é intencional? O limiar em 1 e o fato de `NLRP3o` mal passar dele vêm do
artigo de origem? **Consequência para a verificação:** um modelo simplificado com erro de 1 %
em `NLRP3o` pode mudar muito o resto da cascata. Isso é um bom caso de teste para a biblioteca,
mas os limites dos critérios precisam ser escolhidos sabendo disso.

## 4. Pontos menores, para confirmar

- **Origem do modelo:** de qual artigo ou trabalho vem? Quem é o autor do notebook? É preciso
  saber para citar.
- **Unidades:** o tempo está em minutos, conforme os rótulos dos gráficos. As concentrações
  parecem adimensionais (valores iniciais 1). Confirmar.
- **`NLRP3o` não tem degradação** (`NLRP3i` e `NLRP3a` têm `delta1`), então só acumula. É
  intencional?
- **Totais conservados:** `ASCf + ASCb`, `proC1 + C1` e `proIL18 + IL18c + IL18e` ficam
  constantes (= 1); IL-1β não, porque tem produção e degradação. O teste `test_conserved_totals`
  confere isso. Pode ser útil para escolher o mapeamento do simplificado.
- **`G` aparece com e sem `k5`:** `k5*G*IL1bc` para IL-1β e só `G*IL18c` para IL-18 (com
  `k5 = 1` dá no mesmo). Há um comentário no notebook, "G = G * k6 (k6 = 1/min)". Confirmar se
  a assimetria é proposital.

## 5. Modelo simplificado (`nlrp3_simplificado.ipynb`)

Também pendente com a Bárbara (questão 56 de `docs/questoes-em-aberto.md`). Os números estão em
`estudo_de_caso/nlrp3/NOTAS.md`.

- **De onde vem `j = 0.7`?** No original, a fração do IL-1β celular que chega ao meio
  extracelular é `k5*G / (k5*G + delta2) = 0.08 / 0.084 ≈ 0.952`. Com `0.7`, `IL1be` termina
  26 % abaixo do original, e essa é a principal reprovação. O valor foi ajustado aos dados do
  artigo? O notebook compara o simplificado com CSVs do artigo (`b.csv` para `IL1Be`), que não
  vieram junto.
- **De onde vem `novodelta1 = 0.0025`?** O comentário diz "j * delta1 = 1.25 * 0.002 = 0.0025",
  mas `j = 0.7` no mesmo notebook, então o `j` do comentário é outro número. Na exploração da
  `NOTAS.md`, voltar ao `delta1 = 0.002` melhora `NLRP3a` e piora muito `IL18c` (erro final de
  6 % para 56 %), o que sugere que `0.0025` foi calibrado para compensar a retirada de `NLRP3i`.
- **O objetivo do simplificado é reproduzir o original ou os dados do artigo?** O notebook só o
  compara com o artigo. A biblioteca compara com o original. Se o objetivo for o artigo, uma
  reprovação contra o original não quer dizer que a simplificação é ruim, e o texto precisa
  deixar isso claro.
- **Parâmetros declarados e não usados:** `S2`, `k1`, `k5` e `k6`. Estão no SBML com o mesmo
  valor, para manter a transcrição fiel.
- **A fração `1 - j` do IL-1β clivado some** (não vai para nenhuma variável). No original, o
  que não sai da célula é degradado por `delta2`. Confirmar se a perda é intencional.
- **Quais variáveis importam e com quais limites?** A configuração usa, por ora, os critérios
  do estudo de caso da Verly, com todas as variáveis como core.
