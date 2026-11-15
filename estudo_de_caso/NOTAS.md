# Estudo de caso: as simplificações do TCC I no reducheck

Escrito em 28/09/2026 (issue #16). Compara o veredito da biblioteca com o que o TCC I
(`docs/tcc1.pdf`, seção 4.1) afirma sobre as duas simplificações do modelo de
Verly et al. (2024).

| | |
| --- | --- |
| Modelo original | `modelos/verly_original.xml` (11 variáveis, conferido na issue #4) |
| Simplificação 1 | `modelos/verly_simp1.xml` (9 variáveis) — configuração em `simp1.yaml` |
| Simplificação 2 | **fora do escopo** por decisão de 11/10/2026 (ver o fim desta nota) |
| Fonte das equações | `referencia/simplificacao_2026-04-22.md` |
| Condições | 720 dias, 1000 pontos, CVODE, tol. relativa 1e-8 e absoluta 1e-10, iguais nos dois modelos |
| Ruído numérico de referência | 8,95e-07 (NRMSE máximo do original contra ele mesmo com tolerâncias 100× mais frouxas) |

Reproduzir:

```bash
python modelos/build_sbml.py
reducheck verificar estudo_de_caso/simp1.yaml
```

## Simplificação 1 — remoção de `Cm` e `Mc`

**Veredito da biblioteca: REPROVADO. 3 de 15 critérios (20,0%); obrigatórios 2/10,
desejáveis 1/5.**

O que o TCC I esperava: que esta fosse a simplificação viável, justificada pela "menor
centralidade de tais variáveis nos mecanismos hormonais de interesse".

> **Atualizado em 13/11/2026.** Até esta data a simplificação 1 usava o `C1` da nota de
> abril, sem o `E2` na degradação. A Isabella decidiu que o `C1` tem de ser o do original,
> porque remover `Cm` e `Mc` não mexe em `C1` (questão 35). Todos os números desta nota foram
> medidos de novo com o `C1` do original. A contagem da trajetória continua 3 de 15, mas os
> valores mudaram muito: **com o `C1` do original, a formação óssea praticamente some nos 720
> dias** (ver abaixo).

### Números

NRMSE das nove variáveis (as cinco core em negrito):

| Variável | NRMSE | Original (final) | Simp. 1 (final) |
| --- | --- | --- | --- |
| `D` | 0,00160 | 987.930 | 987.950 |
| `Mo` | 0,00044 | 0,015172 | 0,021250 |
| `M1` | 0,00184 | 0,043682 | 0,060304 |
| `M2` | 0,00875 | 0,045077 | 0,026922 |
| **`C1`** | **3,0292** | 10,011 | 43,779 |
| **`C2`** | **0,99247** | 0,084337 | 2,259e-08 |
| **`Cb`** | **0,55023** | 166.930 | 0,51718 |
| **`Mb`** | **0,91039** | 0,99894 | 2,034e-05 |
| **`E2`** | **0,00000** | 0,0564 | 0,0564 |

Os três critérios declarados, nas cinco variáveis core:

| Métrica | `Cb` | `Mb` | `C1` | `C2` | `E2` |
| --- | --- | --- | --- | --- | --- |
| `nrmse` (limite 0,05, obrigatório) | 0,55023 | 0,91039 | 3,0292 | 0,99247 | 7,4e-10 ✅ |
| `mape` (limite 0,05, desejável) | 1,00000 | 0,99999 | 3,1228 | 0,99950 | 5,1e-12 ✅ |
| `erro_estacionario` (limite 0,01, obrigatório) | 1,00000 | 0,99998 | 3,3732 | 1,00000 | 0 ✅ |

Os erros estão **seis ordens de grandeza acima do ruído numérico**, então nada disso é
solver ou tolerância.

### Por que falha: `Cb` não decola

No modelo original,

```
Cb' = Ab·Cb·(1 − Cb/k_lb)  +  F1·Cm  −  d_b·Cb
```

Todo termo carrega um fator `Cb`, **menos** `F1·Cm`. Como `Cb(0) = 0`, esse termo é a
única fonte de osteoblastos do modelo: é ele que tira `Cb` do zero. A simplificação 1
remove exatamente esse termo, e o documento de 22/04/2026 põe no lugar um termo `Es`.

**Sem nenhuma fonte, a equação é homogênea em `Cb` e `Cb = 0` é solução para sempre** —
`Cb ≡ 0`, `Mb ≡ 0`, e a simplificação apagaria a formação óssea inteira. Está travado em
`tests/test_verly_simp1.py::test_without_any_source_the_osteoblasts_stay_at_zero`.

O documento escreve a equação original de `Cb` como
`dCb/dt = Es + Ab·Cb·(1 − Cb)/klb − F1·Cm − db·Cb`, e a simplificação tira dela o
`F1·Cm`. O `Es` é `E2`, erro de digitação (confirmado pela Isabella em 11/10/2026 —
questão 34). Com isso `Cb` sai do zero, mas **não decola**:

| | Original | Simplificação 1 |
| --- | --- | --- |
| Pico de `Cb` | 357.248, em t = 32,4 dias | 1,108, em t = 28,8 dias |
| `Cb` final | 166.930 | 0,517 |
| `Mb` final | 0,99894 | 2,0e-05 |

O motivo é uma cadeia que passa por `C1`. Sem `k_3·Cm`, `C2` cai quase a zero (seção
seguinte); `C2` inibe `C1` por `H1 = a_12/(a_12 + C2)`, então `C1` sobe e termina em 43,8
contra 10,0 do original; e `C1` inibe a proliferação de osteoblastos por
`Ab = kpb·apb/(apb + C1)`. Com `C1 = 43,8`, `Ab = 0,041`, abaixo da morte `d_b = 0,15`.
**A logística deixa de ter ponto fixo positivo**, e com `Cb ≪ k_lb` a equação fica quase
linear, `Cb' ≈ E2 − (d_b − Ab)·Cb`, cujo equilíbrio é `E2/(d_b − Ab) = 0,0564/0,109 ≈ 0,517`.
É exatamente o valor final simulado (travado em
`tests/test_verly_simp1.py::test_the_source_sets_the_level_because_the_logistic_has_no_positive_point`).
No original, `Ab` final é 0,110, também abaixo de `d_b`, e o que sustenta `Cb` em 167 mil é o
`F1·Cm`, da ordem de 10⁴.

Enquanto a simplificação usava o `C1` da nota (sem `E2` na degradação), `C1` terminava em 2,47,
`Ab` ficava acima de `d_b` e `Cb` ia para o patamar da logística, cerca de 150 mil. Era daí
que vinha a leitura anterior, de que "o valor de `Es` quase não importa". Com o `C1` do
original, ela não vale mais.

**Agora o valor de `Es` decide o nível de `Cb`**, que é proporcional à fonte. Varrendo:

| `Es` | NRMSE `Cb` | NRMSE `Mb` | `Cb` final |
| --- | --- | --- | --- |
| 1e-12 | 0,55023 | 0,91040 | 9,2e-12 |
| 1e-6 | 0,55023 | 0,91040 | 9,2e-06 |
| 0,0564 (constante, ≈ `E2`) | 0,55023 | 0,91039 | 0,517 |
| **`E2` (a variável — adotado)** | **0,55023** | **0,91039** | **0,517** |
| 1 | 0,55020 | 0,91020 | 9,17 |
| 100 | 0,54737 | 0,89025 | 917 |
| 2.500 | 0,48028 | 0,54403 | 22.731 |
| 9.737 (valor final de `F1·Cm`) | 0,29238 | 0,17463 | 86.478 |
| 25.000 | 0,11635 | 0,01264 | 212.319 |

Nenhum valor leva `Cb` abaixo do limite de 0,05. O melhor é 0,116, em `Es = 25.000`, mais
que o dobro do limite, com uma fonte constante cinco ordens de grandeza acima do `E2`.
**O veredito não depende da resposta da Ana Clara**, só os números do texto dependem.

Uma ressalva para o texto: esse termo de fonte **não existe em
`referencia/bone_estradiol.py`**. Ele aparece na equação que o documento apresenta como
sendo a do modelo **original**, o que é uma pergunta sobre o original e não sobre a
simplificação — questão 38. Não muda o veredito, mas precisa de resposta antes de o texto
afirmar qual é o modelo de referência.

### Por que falha: `C2` perde sua fonte dominante

`C2' = H2·(k_2·M2 + k_3·Cm)·E2 − d_c2·C2`. No equilíbrio do original, `k_3·Cm` vale
`7e-7 × 9,84e5 ≈ 0,69`, enquanto `k_2·M2` vale `3,72e-6 × 0,027 ≈ 1,0e-7` — uma diferença
de quase sete ordens de grandeza. Remover `k_3·Cm` não remove um termo secundário: remove
**a** fonte de `C2`, que cai de 0,0843 para 2,3e-08. Daí o NRMSE de 0,992.

> **Pendente (questão 54 de `docs/questoes-em-aberto.md`):** o documento de 22/04 se
> contradiz sobre esse termo. O texto manda removê-lo, e a imagem das equações o mantém.
> O código segue o texto. A resposta tem que vir da Bárbara e da Ana Clara antes de o texto
> do TCC atribuir a falha em `C2` à simplificação.

> Como `C1` e `Cb` dependem de `C2` (cadeia `C2 → C1 → Cb` da seção anterior), essa questão
> agora decide também a falha em `C1`, `Cb` e `Mb`, e não só em `C2`.

### Por que falha: `C1` sobe por tabela

`C1` termina em 43,8 contra 10,0 do original (NRMSE 3,03). A equação de `C1` é a mesma nos
dois modelos (travado em `tests/test_verly_simp1.py::test_c1_equation_is_the_one_of_the_original`),
então a diferença é toda efeito em cadeia do colapso de `C2`, que entra em
`H1 = a_12/(a_12 + C2)`: com menos `C2`, menos inibição, mais `C1`.

### O que passa

`E2` passa nas três métricas com erro na casa de 1e-10, como tem que ser: `dE2/dt` não
depende de nenhuma outra variável e a simplificação não a tocou. É a prova de que a
transcrição está certa e de que os erros acima são do modelo, não do arquivo.

As quatro variáveis fora do conjunto core (`D`, `Mo`, `M1`, `M2`) ficam todas abaixo de
0,009 de NRMSE (o maior é 0,00875, em `M2`). Ou seja: **a simplificação preserva bem a dinâmica dos macrófagos e do
debri, e erra a parte óssea e as citocinas.** Se o conjunto core fosse escolhido entre os macrófagos,
a mesma simplificação seria aprovada — o que é um bom argumento, para o texto do TCC II,
a favor de declarar as variáveis core antes de comparar.

## Análise qualitativa: equilíbrio e estabilidade local

Acrescentado em 11/10/2026 (issue #18). Até 04/11/2026 ficava numa configuração separada
(`simp1_qualitativo.yaml`), para não alterar a porcentagem do veredito de trajetória
registrado acima. Desde então está no próprio `simp1.yaml`: o relatório separa as duas
perguntas em abas ("Trajetória" e "Longo prazo"), cada uma com a sua contagem, e os números
de cada uma são os mesmos de quando eram arquivos separados (conferido em 04/11/2026). O
veredito do topo junta as duas: **REPROVADO, 9 de 21 (42,9%); obrigatórios 8/16.**

```bash
reducheck verificar estudo_de_caso/simp1.yaml
```

**Longo prazo: APROVADO. 6 de 6 critérios (100%); obrigatórios 6/6.** Era REPROVADO (5 de
6, pelo `equilibrio` de `C1`) enquanto a simplificação usava o `C1` da nota.

Duas coisas precisam ser lidas antes dos números:

1. **Nenhuma das duas facilidades do libRoadRunner funciona neste modelo.** As 11 variáveis
   são parâmetros com regra de taxa, e não espécies flutuantes, então o `steadyState`
   devolve "convergiu" com resíduo 1,8e-18 sem ter resolvido nada (as taxas continuam em
   2500) e o `getFullJacobian` recusa (*fewer floating species (0) than rate rules (11)*).
   O equilíbrio sai por integração estendida e a Jacobiana por diferenças finitas centrais.
2. **O equilíbrio só é alcançado em t = 7,2×10⁸ dias**, um milhão de vezes os 720 dias
   simulados. É matematicamente legítimo e biologicamente sem sentido: o `Cb` quase dobra
   depois do fim da simulação (1,67×10⁵ em t = 720 contra 3,19×10⁵ no equilíbrio), e o
   modelo foi parametrizado para uma janela de meses a poucos anos. O relatório imprime o
   instante e o múltiplo do horizonte justamente para isso não passar batido.

| Variável | Equilíbrio original | Equilíbrio simp. 1 | Erro relativo | Limite | Resultado |
| --- | --- | --- | --- | --- | --- |
| Cb | 318 795 | 318 796 | 2,46e-06 | 0,05 | passou |
| Mb | 1 | 1 | 1,1e-16 | 0,05 | passou |
| C1 | 8,2922e-05 | 8,3217e-05 | 0,00356 | 0,05 | passou |
| C2 | 8,1726e-10 | 8,2007e-10 | 3,32e-05 | 0,05 | passou |
| E2 | 0,0564 | 0,0564 | 0 | 0,05 | passou |

| Modelo | Classificação | Autovalores dominantes |
| --- | --- | --- |
| original | marginal | −3,945e-09, −0,011057, −0,015940 |
| simplificado | marginal | −3,958e-09, −0,011057, −0,015940 |

A classificação coincide, então `estabilidade_local` passa. O autovalor dominante é
−3,9×10⁻⁹: um modo com escala de ~10⁹ dias, que é o `D` esvaziando. Ele é o motivo de os
dois modelos serem lidos como **marginais** e não como estáveis — com a tolerância relativa
ao espectro (10⁻⁶ × maior parte real, questão 40 de `docs/questoes-em-aberto.md`), uma parte
real nove ordens de grandeza abaixo do modo mais rápido é indistinguível de zero.

**O que isso diz sobre a simplificação 1.** Nas variáveis que têm equilíbrio diferente de
zero — `Cb`, `Mb`, `E2` — a simplificação **acerta o destino com seis dígitos**, enquanto
reprova nas trajetórias dentro dos 720 dias (`Mb` em 720 dias: 0,999 no original contra
2,0e-05 no simplificado). Ela erra o caminho e acerta o ponto de chegada: quando `C1` decai,
`Ab` volta a ficar acima de `d_b` e `Cb` chega ao mesmo patamar da logística, mas isso
acontece muito depois dos 720 dias. Para o texto do
TCC II, é o complemento do argumento da seção anterior: não basta escolher as variáveis
core, é preciso escolher também **em que horizonte** a fidelidade é exigida.

> **Leitura automática do relatório.** A aba "Resumo" lê as duas perguntas juntas e, desde
> 13/11/2026, diz *"Erra o caminho, mas acerta o destino"*, que agora concorda com a leitura
> acima. Antes, com o `C1` da nota, o `equilibrio` de `C1` falhava e o resumo dizia *"Não é
> fiel nem no caminho nem no destino"*.

**O que isso não diz.** O erro em `C1` (0,36%) e em `C2` **não é uma propriedade do
modelo**. `C1` e `C2` decaem para zero, então o equilíbrio delas é 0 nos dois modelos, e o
erro relativo num ponto de parada finito mede onde a integração parou. A tabela da questão 42
de `docs/questoes-em-aberto.md` (79% em t = 7,2×10⁷, 9,3% em 7,2×10⁸, …) foi medida com o `C1`
da nota e não foi refeita; o ponto continua valendo. Agora `C1` passa, mas pelo mesmo motivo
o acordo em `C1` e `C2` também não deve ser citado no texto como resultado sobre o modelo
enquanto a questão 42 não for decidida com a orientadora. O que vale como resultado é o
acordo em `Cb`, `Mb` e `E2` e a igualdade das classificações.

## Sensibilidade ao teste de convergência

Acrescentado em 15/11/2026, a partir de uma pergunta da orientadora: até onde o teste de
convergência aceita, e o veredito muda conforme ele? Interpretação e achados na questão 59
de `docs/questoes-em-aberto.md`. Números com o `C1` do original (com `E2`), a versão do main
desde o PR #59.

```bash
python estudo_de_caso/sensibilidade_convergencia.py   # cerca de 20 s
```

Gera `texto/tabelas/convergencia_tolerancia.tex`, `texto/tabelas/convergencia_horizonte.tex`
(as duas também em PNG), `texto/figuras/convergencia_horizonte.pdf` e `.png`, além dos CSV em
`resultados/convergencia/`. O erro e o veredito saem de `verdict.avaliar`, com os critérios
de longo prazo de `simp1.yaml`, então são os mesmos números do relatório.

**Tolerância** (análise da biblioteca como ela roda, trocando só a tolerância):

| Tolerância | Parou em | Cb | C1 | C2 | Longo prazo |
| --- | --- | --- | --- | --- | --- |
| 10⁻³ | 720 / steadyState | 1,00 | 1,00 | 1,00 | REPROVADO 0/6 |
| 10⁻⁴ | 7200 / steadyState | 1,00 | 1,00 | 1,00 | REPROVADO 0/6 |
| 10⁻⁵ | 7,2×10⁷ | 0,756 | 2,61 | 1,00 | REPROVADO 3/6 |
| 10⁻⁶ a 10⁻¹⁰ | 7,2×10⁸ | 2,5×10⁻⁶ | 0,0036 | 3,3×10⁻⁵ | APROVADO 6/6 |
| 10⁻¹¹ | 7,2×10⁸ / 7,2×10⁹ | 1,9×10⁻⁵ | **0,931** | 0,0090 | REPROVADO 5/6 |
| 10⁻¹² | não convergiu | — | — | — | — |

**Horizonte fixo** (os dois integrados até o mesmo instante, sem teste de parada):

| Horizonte (× 720) | Cb | Mb | C1 | C2 | Longo prazo |
| --- | --- | --- | --- | --- | --- |
| 10⁰ a 10⁴ | 1,00 | 1,00 a 0,82 | 3,4 | 1,00 | REPROVADO 2/6 |
| 10⁵ | 0,756 | 3×10⁻¹⁶ | 2,61 | 1,00 | REPROVADO 3/6 |
| 10⁶ | 2,5×10⁻⁶ | 1×10⁻¹⁶ | 0,0036 | 3,3×10⁻⁵ | APROVADO 6/6 |
| 10⁷ a 10¹¹ | 2,5×10⁻⁶ | < 10⁻¹⁵ | 2×10⁻⁷ a 1,5×10⁻⁴ | < 2×10⁻⁷ | APROVADO 6/6 |

Nos primeiros horizontes, o erro de `Cb` é 1,00 porque o `Cb` do simplificado fica perto de
zero (0,5 contra 1,67×10⁵ em t = 720; ainda 0,58 em 7,2×10⁶). Os dois modelos só se encontram
entre 7,2×10⁷ e 7,2×10⁸ dias. `E2` fica abaixo de 10⁻¹⁵ em todos os pontos. A estabilidade é
"marginal" nos dois modelos em todo ponto com tolerância de 10⁻⁵ ou mais apertada. Com 10⁻³ e
10⁻⁴, o simplificado é "instável" porque está no equilíbrio trivial.

**Leitura em uma frase:** a faixa útil de tolerâncias vai de 10⁻⁶ a 10⁻¹⁰. Dentro dela, o
longo prazo é APROVADO 6/6 em todas as cinco décadas. Fora dela, o teste ou aceita pontos que
ainda não são equilíbrio (frouxa) ou esbarra no piso numérico (10⁻¹¹ compara instantes
diferentes; 10⁻¹² não converge). Na versão v-nota, antes do PR #59, o padrão dava REPROVADO 5/6
por `C1` (9,3%), que era a fragilidade da questão 42. Com o `C1` do original, ela não muda mais
o veredito.

## Tempo de execução

Escrito em 17/10/2026 (issue #22). Medido por `gerar_resultados.py`: 10 execuções de cada
modelo, uma de aquecimento descartada, nas condições de `simp1.yaml`. Os números são desta
máquina (Windows 10, Python 3.13, libRoadRunner 2.10.0).

| Modelo | Carga do SBML (ms) | Integração (ms) | Integração / original |
| --- | --- | --- | --- |
| Original (11 variáveis) | 78,2 ± 0,9 | 5,94 ± 0,45 | 1,00 |
| Simplificação 1 (9 variáveis) | 65,3 ± 1,0 | 5,50 ± 0,07 | 0,925 |

Essa é a execução gravada em `texto/tabelas/tempo_execucao.tex`, refeita em 13/11/2026 com o
`C1` do original. Em 17/10/2026, em três execuções do script no mesmo dia, a razão da
integração ficou entre **0,997 e 1,07**, sempre dentro de um desvio padrão. A razão de 0,925
de agora está perto desse intervalo, e uma rodada só não basta para dizer que a diferença
mudou.

**A simplificação 1 não deixa a integração mais rápida**, e o custo dominante é compilar o
modelo, não integrá-lo. Leitura e ressalvas na questão 50 de `docs/questoes-em-aberto.md`.

## Material para o texto

```bash
python estudo_de_caso/gerar_resultados.py
```

Refaz as duas verificações e grava, a partir do mesmo `reducheck.Resultado` que gera o
relatório:

- `texto/figuras/simp1_core` e `simp1_nao_core`, cada uma em `.pdf` (vetorial, para o LaTeX) e
  `.png` (300 dpi): trajetórias, original × simplificação 1;
- `texto/tabelas/simp1_criterios.tex`, `simp1_criterios_qualitativos.tex`,
  `simp1_equilibrios.tex`, `simp1_autovalores.tex` e `tempo_execucao.tex` (pacote `booktabs`),
  cada uma também em `.png` com o mesmo nome, desenhada a partir do próprio `.tex` para os
  dois não poderem mostrar números diferentes.

O autovalor dominante da tabela é o do ponto onde a biblioteca para (t = 7,2×10⁸), e não o
−2,05×10⁻¹⁰ citado antes, que é de t = 10¹⁰ (questão 49).

## Comparação com o TCC I

| | TCC I | reducheck |
| --- | --- | --- |
| Simplificação 1 | tratada como a redução viável | **REPROVADO**, 20% dos critérios |
| Simplificação 2 | "caso de falha esperada" | **não avaliada**: nunca foi especificada por ninguém |

**Os vereditos não batem, e o motivo mais provável não é a biblioteca.** O TCC I declara
(seção 4.2) que "um modelo simplificado é considerado válido quando o MAPE global não
excede 5%", mas o MAPE **global** — média sobre todas as variáveis — dilui o problema:
quatro das nove variáveis batem quase exatamente (NRMSE abaixo de 0,009) e uma é exata,
então uma média não ponderada sobre as nove esconde o que acontece em `C2`, `C1`, `Cb` e
`Mb`. Aqui o MAPE é aplicado **por variável**, com as variáveis core declaradas antes, e
o problema aparece.

Três hipóteses para a divergência, em ordem de plausibilidade:

1. **O TCC I nunca chegou a rodar a simplificação 1 nessa forma.** A Isabella confirmou em
   28/09/2026 que não existe código oficial dessas simplificações, só uma transcrição não
   oficial. Os resultados "preliminares" do TCC I podem ter vindo de uma versão diferente
   da que o documento de 22/04 descreve.
2. **`Es` não é `E2`, e sim outra coisa.** Com a leitura adotada (questão 34), `Cb` fica
   em 0,517 contra 166.930. A varredura mostra que nenhum valor de `Es` leva `Cb` abaixo
   do limite, e `C2` e `C1` não melhoram em valor nenhum. Mesmo com a fonte "certa", a
   simplificação continua reprovando por `C2` e `C1`.
3. **O critério era outro.** Com MAPE global em vez de por variável, e sem variáveis core
   declaradas, a mesma simplificação pode ter parecido aceitável.

Nenhum limite foi afrouxado e nenhuma equação foi ajustada para mudar este resultado.

## Diagnóstico: remover só Mc

Escrito em 05/11/2026 e refeito em 13/11/2026. **Este modelo não é uma simplificação nova**
(simplificar está fora do escopo do TCC): é um teste para separar as causas da reprovação da
simplificação 1.

Em relação ao original, a simplificação 1 faz duas mudanças:

1. remove `Cm`, com os termos `F1·Cm` em `Cb` e `k_3·Cm` em `C2`, e põe a fonte `E2` em `Cb`;
2. remove `Mc`.

Até 13/11/2026 havia uma terceira: o `C1` da nota de abril, sem o `E2` na degradação. Para
medi-la existia um diagnóstico B (`verly_diag_sem_mc_c1_nota`). Com a simplificação usando o
`C1` do original (questão 35), o B ficaria idêntico ao A e foi removido; continua no histórico
do git (commit `56a494d`).

`Mc` só aparece na própria equação, então removê-lo não muda nenhuma outra variável. O modelo
parte de `verly_original.ant`, não da simplificação 1:

| Modelo | Arquivo | Diferenças em relação ao original |
| --- | --- | --- |
| Diagnóstico A | `modelos/verly_diag_sem_mc.ant` | só `Mc` (equação, condição inicial, `p_cs`, `q_cd1`, `q_cd2`) |

A configuração (`diag_sem_mc.yaml`) é cópia de `simp1_criterios_propostos.yaml`. Mudam só o
modelo simplificado, a pasta de saída e `Cm`, que passa a existir nos dois modelos
(`core: false`, sem critério). Métricas, limites, variáveis core e obrigatório/desejável são os
mesmos.

Reproduzir:

```bash
python modelos/build_sbml.py
reducheck verificar estudo_de_caso/simp1_criterios_propostos.yaml
reducheck verificar estudo_de_caso/diag_sem_mc.yaml
```

### Números

| Critério | Variável | Limite | Tipo | Simp. 1 | Diag. A |
| --- | --- | --- | --- | --- | --- |
| `nrmse` | `Cb` | 0,05 | obrigatório | 0,550 ✗ | 7,8e-09 ✓ |
| `nrmse` | `Mb` | 0,05 | obrigatório | 0,910 ✗ | 4,4e-09 ✓ |
| `nrmse` | `C1` | 0,05 | obrigatório | 3,03 ✗ | 3,2e-09 ✓ |
| `nrmse` | `C2` | 0,05 | obrigatório | 0,992 ✗ | 4,1e-09 ✓ |
| `erro_l2_rel` | `Cb` | 0,05 | desejável | 1,00 ✗ | 1,4e-08 ✓ |
| `erro_l2_rel` | `Mb` | 0,05 | desejável | 1,00 ✗ | 4,8e-09 ✓ |
| `erro_l2_rel` | `C1` | 0,05 | desejável | 3,28 ✗ | 3,5e-09 ✓ |
| `erro_l2_rel` | `C2` | 0,05 | desejável | 1,00 ✗ | 4,1e-09 ✓ |
| `erro_estacionario` | `Cb` | 0,01 | obrigatório | 1,00 ✗ | 4,4e-09 ✓ |
| `erro_estacionario` | `Mb` | 0,01 | obrigatório | 1,00 ✗ | 2,1e-09 ✓ |
| `erro_estacionario` | `C1` | 0,01 | obrigatório | 3,37 ✗ | 2,6e-09 ✓ |
| `erro_estacionario` | `C2` | 0,01 | obrigatório | 1,00 ✗ | 9,9e-13 ✓ |
| `erro_estacionario` | `Mo` | 0,01 | desejável | 0,401 ✗ | 1,5e-12 ✓ |
| `erro_estacionario` | `M1` | 0,01 | desejável | 0,381 ✗ | 1,1e-12 ✓ |
| `erro_estacionario` | `M2` | 0,01 | desejável | 0,403 ✗ | 6,3e-14 ✓ |
| `equilibrio` | `Cb` | 0,05 | desejável | 2,5e-06 ✓ | 2,8e-11 ✓ |
| `equilibrio` | `Mb` | 0,05 | desejável | 1,1e-16 ✓ | 0 ✓ |
| `equilibrio` | `C1` | 0,05 | desejável | 0,00356 ✓ | 1,6e-06 ✓ |
| `equilibrio` | `C2` | 0,05 | desejável | 3,3e-05 ✓ | 1,5e-08 ✓ |
| `estabilidade_local` | — | — | desejável | marginal/marginal ✓ | marginal/marginal ✓ |
| *`Cm` (informativo)* | `nrmse` / `erro_estacionario` | — | — | — | 5,5e-09 / 4,7e-12 |

| | Simp. 1 | Diag. A |
| --- | --- | --- |
| Veredito | REPROVADO | APROVADO |
| Itens atendidos | 5 de 20 (25,0%) | 20 de 20 (100%) |
| Obrigatórios | 0/8 | 8/8 |

### Leitura

- **O diagnóstico A confere a montagem.** Tirar só `Mc` dá erros entre 1e-14 e 1e-8 na
  trajetória (o ruído numérico de referência é 8,95e-07) e 1,6e-6 no equilíbrio de `C1`, que é
  da ordem da tolerância da busca do equilíbrio. Como esperado, `Mc` não influencia nada.
- **Logo, a reprovação da simplificação 1 vem toda da retirada de `Cm`.** A simplificação 1 é
  o diagnóstico A menos `Cm`. Como `Mc` não influencia nada, a diferença entre as duas colunas
  é o efeito de tirar `Cm`: os termos `F1·Cm` em `Cb` e `k_3·Cm` em `C2`, com a fonte `E2` no
  lugar do primeiro. Dentro disso, qual dos dois termos pesa mais depende da questão 54 (se
  `k_3·Cm` sai mesmo).

Nenhum limite foi mudado.

## Simplificação 2 — fora do escopo deste estudo de caso

**Decisão da Isabella em 11/10/2026: a simplificação 2 sai, e o estudo de caso fica só
com a simplificação da Ana Clara (remoção de `Cm` e `Mc`).**

O motivo é de procedência: **a simplificação 2 nunca foi escrita por ninguém.** Ela
aparece em três lugares do material, e nenhum deles tem equação:

| Onde | O que há |
| --- | --- |
| `referencia/simplificacao_2026-04-22.md` | O título "Segunda Simplificação — Remoção de M1 e M2" e a lista de variáveis (`D, M, c1, c2, Cb, mb, E2`). Nada abaixo. |
| `docs/tcc1.pdf`, seção 4.1 | Uma frase em prosa: "eliminar M1 e M2, agregando a dinâmica dos macrófagos na variável única M... atua como um caso de falha esperada". |
| Issue #16 e `planejamento/tarefas.yaml` | Só a referência a ela. |

O contraste com a simplificação 1 é grande: a 1 tem os parâmetros removidos listados um
a um, os termos removidos nomeados e as equações escritas; a 2 tem um título e uma lista
de variáveis. A leitura é que ela foi **combinada e não feita**.

Escrevê-la agora não seria transcrever o trabalho de alguém, e sim **projetar uma
simplificação nova**, porque quatro decisões de modelagem estão em aberto. Somar as três
equações dos macrófagos não resolve: o que cancela dá

```
Mo' + M1' + M2' = RM − (d_o·Mo + d_1·M1 + d_2·M2)
```

e o resto ainda pede `Mo`, `M1` e `M2` separados. As quatro decisões:

1. qual `d_M` usar no decaimento de `M`, já que os três decaem a ritmos diferentes
   (`d_o = 0,156`, `d_1 = 0,121`, `d_2 = 0,163`);
2. `D' = −RD·(ke_1·M1 + ke_2·M2)` → `−RD·ke·M`? Note que `Mo` **não** fagocita no
   original, e `M` o incluiria;
3. `C1' = H1·(k_o·D + k_1·M1)` → `k_1·M`? Só `M1` produz `C1` no original;
4. `C2' = H2·(k_2·M2)·E2` → `k_2·M`? Só `M2` produz `C2` no original.

Isso fica para depois, se houver tempo. Registrado como questão 36 em
`docs/questoes-em-aberto.md`.

> Observação que vale para o texto, independente de a simplificação 2 ser feita ou não:
> **dá para explicar por que ela seria o caso de falha esperada antes de rodá-la.** Ela
> joga fora exatamente a informação — qual tipo de macrófago — de que três das equações
> restantes dependem. É um argumento estrutural, não um número de métrica.
