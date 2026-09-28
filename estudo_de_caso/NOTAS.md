# Estudo de caso: as simplificações do TCC I no reducheck

Escrito em 28/09/2026 (issue #16). Compara o veredito da biblioteca com o que o TCC I
(`docs/tcc1.pdf`, seção 4.1) afirma sobre as duas simplificações do modelo de
Verly et al. (2024).

| | |
| --- | --- |
| Modelo original | `modelos/verly_original.xml` (11 variáveis, conferido na issue #4) |
| Simplificação 1 | `modelos/verly_simp1.xml` (9 variáveis) — configuração em `simp1.yaml` |
| Simplificação 2 | **não existe ainda**: as equações não foram definidas (ver o fim desta nota) |
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
| **`Cb`** | **0,55023** | 166.934 | **0** |
| **`Mb`** | **0,91040** | 0,99894 | **0** |
| **`E2`** | **0,00000** | 0,0564 | 0,0564 |

Os três critérios declarados, nas cinco variáveis core:

| Métrica | `Cb` | `Mb` | `C1` | `C2` | `E2` |
| --- | --- | --- | --- | --- | --- |
| `nrmse` (limite 0,05, obrigatório) | 0,55023 | 0,91040 | 0,68175 | 0,99247 | 7,4e-10 ✅ |
| `mape` (limite 0,05, desejável) | 1,00000 | 1,00000 | 0,71516 | 0,99950 | 5,1e-12 ✅ |
| `erro_estacionario` (limite 0,01, obrigatório) | 1,00000 | 1,00000 | 0,75328 | 1,00000 | 0 ✅ |

Os erros estão **seis ordens de grandeza acima do ruído numérico**, então nada disso é
solver ou tolerância.

### Por que falha: `Cb` e `Mb` ficam identicamente zero

No modelo original,

```
Cb' = Ab·Cb·(1 − Cb/k_lb)  +  F1·Cm  −  d_b·Cb
```

Todo termo carrega um fator `Cb`, **menos** `F1·Cm`. Como `Cb(0) = 0`, esse termo é a
única fonte de osteoblastos do modelo: é ele que tira `Cb` do zero. A simplificação 1
remove exatamente esse termo. O que sobra,

```
Cb' = Cb·(Ab·(1 − Cb/k_lb) − d_b)
```

é homogêneo em `Cb`, e `Cb = 0` é solução para sempre. Como `Mb' = (p_bs − q_bd·Mb)·Cb`,
a massa óssea vai junto. No original `Cb` chega a 357.247 e `Mb` a 0,999; na
simplificação os dois ficam em 0 do início ao fim — daí o MAPE exatamente 1,000 (erro
relativo de 100% em todos os pontos). Está travado em
`tests/test_verly_simp1.py::test_osteoblasts_stay_at_zero_while_es_is_zero`.

**Isto não é um detalhe de calibração: a simplificação 1, como está descrita, apaga a
formação óssea, que é a saída que o modelo existe para prever.** A nota de 22/04/2026
parece ter percebido o problema, porque introduz um termo `Es` no lugar de `F1·Cm` — mas
não dá valor a ele, e `Es` não existe no código original. **Com `Es = 0` (o valor
provisório usado aqui, que é a leitura literal do texto do TCC I) o resultado é o acima.**
Ver a questão 34 em `docs/questoes-em-aberto.md`.

O veredito não depende dessa escolha. Varrendo `Es`:

| `Es` | NRMSE `Cb` | NRMSE `Mb` |
| --- | --- | --- |
| 0 | 0,550 | 0,910 |
| 2.500 (valor inicial de `F1·Cm`) | 0,480 | 0,544 |
| 9.737 (valor final de `F1·Cm`) | 0,292 | 0,175 |
| 11.025 (média temporal de `F1·Cm`) | 0,261 | 0,146 |
| 25.000 | 0,116 | 0,013 |

Nenhum valor leva `Cb` abaixo do limite de 0,05, e `C2` não melhora em nenhum deles.

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
debri, e destrói a parte óssea.** Se o conjunto core fosse escolhido entre os macrófagos,
a mesma simplificação seria aprovada — o que é um bom argumento, para o texto do TCC II,
a favor de declarar as variáveis core antes de comparar.

## Comparação com o TCC I

| | TCC I | reducheck |
| --- | --- | --- |
| Simplificação 1 | tratada como a redução viável | **REPROVADO**, 20% dos critérios |
| Simplificação 2 | "caso de falha esperada" | **não avaliada** (equações indefinidas) |

**Os vereditos não batem, e o motivo mais provável não é a biblioteca.** O TCC I declara
(seção 4.2) que "um modelo simplificado é considerado válido quando o MAPE global não
excede 5%", mas o MAPE **global** — média sobre todas as variáveis — dilui o problema:
quatro das nove variáveis batem quase exatamente, então uma média não ponderada esconde
que a saída óssea foi a zero. Aqui o MAPE é aplicado **por variável**, com as variáveis
core declaradas antes, e o problema aparece.

Três hipóteses para a divergência, em ordem de plausibilidade:

1. **O TCC I nunca chegou a rodar a simplificação 1 nessa forma.** A Isabella confirmou em
   28/09/2026 que não existe código oficial dessas simplificações, só uma transcrição não
   oficial. Os resultados "preliminares" do TCC I podem ter vindo de uma versão que tinha
   alguma fonte de `Cb`.
2. **`Es` tinha um valor.** A nota introduz o termo justamente onde falta a fonte, o que
   sugere que alguém notou o colapso de `Cb`. Mas mesmo com `Es` generoso a simplificação
   continua reprovando por `C2` e `C1`.
3. **O critério era outro.** Com MAPE global em vez de por variável, e sem variáveis core
   declaradas, a mesma simplificação pode ter parecido aceitável.

Nenhum limite foi afrouxado e nenhuma equação foi ajustada para mudar este resultado.

## Simplificação 2 — bloqueada

A simplificação 2 (`D`, `M`, `C1`, `C2`, `Cb`, `Mb`, `E2`, 7 variáveis) **não foi
implementada**, porque as equações não existem. O documento de 22/04/2026 traz o título
"Segunda simplificação — remoção de M1 e M2" e nada abaixo dele; o `docs/tcc1.pdf` só diz
"agregando a dinâmica dos macrófagos na variável única M".

Somar as três equações não resolve sozinho. O que cancela, cancela:

```
Mo' + M1' + M2' = RM − (d_o·Mo + d_1·M1 + d_2·M2)
```

mas o resto ainda pede `Mo`, `M1` e `M2` separados, e cada um decai num ritmo diferente
(`d_o = 0,156`, `d_1 = 0,121`, `d_2 = 0,163`). Faltam **quatro** decisões que não são da
biblioteca nem podem ser inventadas aqui:

1. qual `d_M` usar no decaimento de `M`;
2. `D' = −RD·(ke_1·M1 + ke_2·M2)` → `−RD·ke·M`, com qual `ke`;
3. `C1' = H1·(k_o·D + k_1·M1)` → `k_1·M`?
4. `C2' = H2·(k_2·M2)·E2` → `k_2·M`?

Registrado como questão 36 em `docs/questoes-em-aberto.md`. Falta confirmar com a
Ana Clara Verly.
