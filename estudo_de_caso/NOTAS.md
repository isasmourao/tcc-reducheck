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

### Números

NRMSE das nove variáveis (as cinco core em negrito):

| Variável | NRMSE | Original (final) | Simp. 1 (final) |
| --- | --- | --- | --- |
| `D` | 0,00200 | 987.933 | 987.956 |
| `Mo` | 0,00046 | 0,015172 | 0,021313 |
| `M1` | 0,00183 | 0,043682 | 0,060253 |
| `M2` | 0,00881 | 0,045078 | 0,026899 |
| **`C1`** | **0,68175** | 10,011 | 2,4699 |
| **`C2`** | **0,99247** | 0,084337 | 2,257e-08 |
| **`Cb`** | **0,45000** | 166.934 | 150.504 |
| **`Mb`** | **0,68452** | 0,99894 | 0,89613 |
| **`E2`** | **0,00000** | 0,0564 | 0,0564 |

Os três critérios declarados, nas cinco variáveis core:

| Métrica | `Cb` | `Mb` | `C1` | `C2` | `E2` |
| --- | --- | --- | --- | --- | --- |
| `nrmse` (limite 0,05, obrigatório) | 0,45000 | 0,68452 | 0,68175 | 0,99247 | 7,4e-10 ✅ |
| `mape` (limite 0,05, desejável) | 0,62409 | 0,72558 | 0,71516 | 0,99950 | 5,1e-12 ✅ |
| `erro_estacionario` (limite 0,01, obrigatório) | 0,09843 | 0,10292 | 0,75328 | 1,00000 | 0 ✅ |

Os erros estão **seis ordens de grandeza acima do ruído numérico**, então nada disso é
solver ou tolerância.

### Por que falha: `Cb` perde o pico e para num patamar mais baixo

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
questão 34). Com isso `Cb` sai do zero e chega a 150.504, contra 166.934 do
original: **9,8% de diferença no valor final**, o que é um resultado bem diferente do
colapso total. O que sobra de erro é a forma da trajetória:

| | Original | Simplificação 1 |
| --- | --- | --- |
| Pico de `Cb` | 357.248, em t = 32,4 dias | não tem pico |
| `Cb` final | 166.934 | 150.504 |
| `Mb` final | 0,99894 | 0,89613 |

O original tem um **transiente de sobre-resposta** — `Cb` dispara até 357 mil por volta
do mês e depois recua para 167 mil — enquanto a simplificação sobe monotonicamente até o
patamar. É essa diferença de forma, e não o nível final, que dá NRMSE de 0,45 em `Cb`.
O `erro_estacionario`, que só olha o fim, cai para 0,098.

**O valor de `Es` quase não importa.** O que `Es` decide é apenas se `Cb` sai do zero; o
patamar é o ponto fixo não nulo da logística, `k_lb·(1 − d_b/Ab) ≈ 150.600`, que não
depende da fonte. Varrendo:

| `Es` | NRMSE `Cb` | NRMSE `Mb` | `Cb` final |
| --- | --- | --- | --- |
| 1e-12 | 0,55023 | 0,91040 | 0,008 |
| 1e-6 | 0,54927 | 0,90956 | 7.513 |
| 0,0564 (constante, ≈ `E2`) | 0,45005 | 0,68466 | 150.503 |
| **`E2` (a variável — adotado)** | **0,45000** | **0,68452** | **150.504** |
| 1 | 0,41042 | 0,56866 | 150.587 |
| 100 | 0,31833 | 0,33092 | 154.224 |
| 2.500 | 0,19877 | 0,10988 | 216.074 |
| 9.737 (valor final de `F1·Cm`) | 0,38354 | 0,02497 | 321.867 |
| 25.000 | 0,74894 | 0,06066 | 458.996 |

`Es = 0,0564` constante e `Es := E2` dão o mesmo número até a quarta casa: o estradiol
entra só como semente. Nenhum valor leva `Cb` abaixo do limite de 0,05 — o melhor é
0,199, em `Es = 2.500`, quatro vezes o limite. **O veredito não depende da resposta da
Ana Clara**, só os números do texto dependem.

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

### Por que falha: `C1` sobe por tabela

`C1` termina em 2,47 contra 10,01 do original (NRMSE 0,682). Parte disso é o efeito em
cadeia do colapso de `C2` (que entra em `H1 = a_12/(a_12 + C2)`) e parte é a ausência do
`E2` na degradação de `C1`, que é uma divergência entre a nota e o código, não um efeito
da simplificação — ver a questão 35 em `docs/questoes-em-aberto.md`. Com o `E2` do código,
o NRMSE de `C1` seria 3,029 em vez de 0,682; reprova dos dois jeitos.

### O que passa

`E2` passa nas três métricas com erro na casa de 1e-10, como tem que ser: `dE2/dt` não
depende de nenhuma outra variável e a simplificação não a tocou. É a prova de que a
transcrição está certa e de que os erros acima são do modelo, não do arquivo.

As quatro variáveis fora do conjunto core (`D`, `Mo`, `M1`, `M2`) ficam todas abaixo de
0,009 de NRMSE. Ou seja: **a simplificação preserva bem a dinâmica dos macrófagos e do
debri, e erra a parte óssea e as citocinas.** Se o conjunto core fosse escolhido entre os macrófagos,
a mesma simplificação seria aprovada — o que é um bom argumento, para o texto do TCC II,
a favor de declarar as variáveis core antes de comparar.

## Análise qualitativa: equilíbrio e estabilidade local

Acrescentado em 11/10/2026 (issue #18). Configuração separada, `simp1_qualitativo.yaml`,
para não alterar a porcentagem do veredito de trajetória registrado acima:

```bash
reducheck verificar estudo_de_caso/simp1_qualitativo.yaml
```

**Veredito: REPROVADO. 5 de 6 critérios (83,3%); obrigatórios 5/6.**

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
| Cb | 318 795 | 318 797 | 4,17e-06 | 0,05 | passou |
| Mb | 1 | 1 | 0 | 0,05 | passou |
| C1 | 8,2922e-05 | 7,5185e-05 | **0,0933** | 0,05 | **falhou** |
| C2 | 8,1726e-10 | 7,4352e-10 | 0,00087 | 0,05 | passou |
| E2 | 0,0564 | 0,0564 | 0 | 0,05 | passou |

| Modelo | Classificação | Autovalores dominantes |
| --- | --- | --- |
| original | marginal | −3,945e-09, −0,011057, −0,015940 |
| simplificado | marginal | −3,596e-09, −0,015940, −0,070199 |

A classificação coincide, então `estabilidade_local` passa. O autovalor dominante é
−3,9×10⁻⁹: um modo com escala de ~10⁹ dias, que é o `D` esvaziando. Ele é o motivo de os
dois modelos serem lidos como **marginais** e não como estáveis — com a tolerância relativa
ao espectro (10⁻⁶ × maior parte real, questão 40 de `docs/questoes-em-aberto.md`), uma parte
real nove ordens de grandeza abaixo do modo mais rápido é indistinguível de zero.

**O que isso diz sobre a simplificação 1.** Nas variáveis que têm equilíbrio diferente de
zero — `Cb`, `Mb`, `E2` — a simplificação **acerta o destino com seis dígitos**, enquanto
reprova nas trajetórias dentro dos 720 dias (`Mb` em 720 dias: 0,999 no original contra
0,896 no simplificado). Ela erra o caminho e acerta o ponto de chegada. Para o texto do
TCC II, é o complemento do argumento da seção anterior: não basta escolher as variáveis
core, é preciso escolher também **em que horizonte** a fidelidade é exigida.

**O que isso não diz.** O erro de 9,33% em `C1` **não é uma propriedade do modelo**. `C1` e
`C2` decaem para zero, então o equilíbrio delas é 0 nos dois modelos, e o erro relativo
num ponto de parada finito mede onde a integração parou: 79% em t = 7,2×10⁷, 9,3% em
7,2×10⁸, 0,75% em 7,2×10⁹, 0,07% em 7,2×10¹⁰. A tabela completa e as três saídas possíveis
estão na questão 42 de `docs/questoes-em-aberto.md`. **Enquanto essa questão não for
decidida com a orientadora, esta reprovação não deve ser citada no texto como resultado
sobre o modelo**; o que vale como resultado é o acordo em `Cb`, `Mb` e `E2` e a igualdade
das classificações.

## Tempo de execução

Escrito em 17/10/2026 (issue #22). Medido por `gerar_resultados.py`: 10 execuções de cada
modelo, uma de aquecimento descartada, nas condições de `simp1.yaml`. Os números são desta
máquina (Windows 10, Python 3.13, libRoadRunner 2.10.0).

| Modelo | Carga do SBML (ms) | Integração (ms) | Integração / original |
| --- | --- | --- | --- |
| Original (11 variáveis) | 96 ± 5 | 6,07 ± 0,44 | 1,00 |
| Simplificação 1 (9 variáveis) | 103 ± 36 | 6,50 ± 0,92 | 1,07 |

Essa é a execução gravada em `texto/tabelas/tempo_execucao.tex`. Em três execuções do script
no mesmo dia, a razão da integração ficou entre **0,997 e 1,07**, sempre dentro de um desvio
padrão: a diferença entre os dois modelos é menor que a variação de uma rodada para outra.

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
  `simp1_equilibrios.tex`, `simp1_autovalores.tex` e `tempo_execucao.tex` (pacote `booktabs`).

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
2. **`Es` não é `E2`, e sim outra coisa.** A leitura adotada (questão 34) põe `Cb` em
   150.504 contra 166.934, o que já é razoável; mas a varredura mostra que nenhum valor
   de `Es` leva `Cb` abaixo do limite, e `C2` não melhora em valor nenhum. Mesmo com a
   fonte "certa", a simplificação continua reprovando por `C2` e `C1`.
3. **O critério era outro.** Com MAPE global em vez de por variável, e sem variáveis core
   declaradas, a mesma simplificação pode ter parecido aceitável.

Nenhum limite foi afrouxado e nenhuma equação foi ajustada para mudar este resultado.

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
