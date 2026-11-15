# Briefing: sensibilidade ao teste de convergência (estudo de caso da Verly)

Para: o Claude que vai rascunhar "Resultados e Discussão" do TCC II da Isabella.
Escrito em 15/11/2026. Complementa `estudo_de_caso/PACOTE_RESULTADOS.md`, que só menciona esta
análise de passagem. As regras de sempre continuam valendo (CLAUDE.md, seção "Tarefas de
escrita"): você rascunha e a Isabella escreve a versão final; LaTeX no template SBC, em
`texto/`; nada de referência inventada, e onde faltar fonte escreva `[CITAR: ...]`.

## Antes de escrever qualquer número, leia isto

1. **Os números abaixo são da versão oficial da simplificação 1**, a que está no main desde o PR
   #59 (15/11): `C1' = … − d_c1·C1·E2`, com o `E2` do original (questão 35). O quadro "Leia
   primeiro" do `PACOTE_RESULTADOS.md` chama essa versão de **v-PR57**. As tabelas
   `convergencia_*.tex` que o pacote descreve como "v-nota" **foram regeradas** e agora são
   v-PR57. Se algum número de convergência no texto ou no pacote disser "REPROVADO 5/6" ou "C1 =
   0,0933" para o longo prazo, ele é da versão antiga.
2. A interpretação completa está na **questão 59** de `docs/questoes-em-aberto.md`, e as tabelas
   em texto corrido na seção "Sensibilidade ao teste de convergência" de
   `estudo_de_caso/NOTAS.md`. Elas são a fonte. Este briefing resume as duas e diz como usá-las no
   texto.
3. Para reproduzir: `python estudo_de_caso/sensibilidade_convergencia.py` (cerca de 20 s), na
   raiz do repositório.

## A pergunta

A orientadora perguntou: até onde o teste de convergência aceita, qual é o mínimo e o máximo? O
veredito de longo prazo muda conforme ele?

Contexto necessário para quem lê o texto: o critério de longo prazo do reducheck (`equilibrio`)
compara o equilíbrio dos dois modelos. No modelo da Verly, o `steadyState` do libRoadRunner não
funciona (as 11 variáveis são parâmetros com *rate rule*, questão 39), então a biblioteca acha o
equilíbrio **integrando** em horizontes crescentes (`t_fim`, 10·`t_fim`, 100·`t_fim`, …). Ela
para quando o resíduo relativo `max|dx/dt| / max|dx/dt|(t0)` fica abaixo de uma tolerância,
10⁻⁶ por padrão. A pergunta é: e se a tolerância fosse outra?

## O que foi feito (método)

Script `estudo_de_caso/sensibilidade_convergencia.py`, que **não altera a biblioteca**: ele só
chama as funções públicas dela, variando um parâmetro de cada vez.

- **Varredura da tolerância:** de 10⁻³ a 10⁻¹², uma por década. Em cada valor roda a mesma
  análise qualitativa que o `reducheck verificar` roda (`qualitative.analisar`), trocando só a
  tolerância.
- **Varredura do horizonte:** sem teste de parada, integra os dois modelos até o mesmo horizonte
  fixo, de 720·10⁰ a 720·10¹¹ dias, e trata o ponto final como equilíbrio. Serve para ver *por
  que* o veredito muda.
- Em todos os pontos, o erro e o veredito são calculados por `verdict.avaliar`, com os critérios
  de longo prazo de `simp1.yaml` (`equilibrio`, limite 0,05 nas cinco variáveis core, e
  `estabilidade_local`). Ou seja, são **os mesmos cálculos do relatório**. No padrão, o script
  reproduz o "Longo prazo: APROVADO 6 de 6" do `NOTAS.md`.

Para a Metodologia, basta uma frase: a análise é um uso da biblioteca, e não uma capacidade dela.

## Resultados

**Tolerância:**

| Tolerância | Onde parou (original / simplificado) | Longo prazo | Leitura |
| --- | --- | --- | --- |
| 10⁻³, 10⁻⁴ | 720 ou 7200 / `steadyState` | REPROVADO 0/6 | comparação inválida (achado 2) |
| 10⁻⁵ | 7,2×10⁷ | REPROVADO 3/6 | ainda no transiente lento (`Cb` erra 76%) |
| **10⁻⁶ (padrão) a 10⁻¹⁰** | 7,2×10⁸ | **APROVADO 6/6** | maior erro: `C1`, 0,36% |
| 10⁻¹¹ | 7,2×10⁸ / 7,2×10⁹ | REPROVADO 5/6 | modelos param em instantes diferentes; `C1` erra 93% (achado 3) |
| 10⁻¹² | não convergiu | — | resíduo do simplificado estaciona em 1,9×10⁻¹¹ (achado 4) |

**Horizonte fixo:** REPROVADO até 7,2×10⁷ dias e APROVADO de 7,2×10⁸ em diante. Até cerca de
7×10⁶ dias, o `Cb` do simplificado fica perto de zero (0,5 contra 1,67×10⁵ do original em
t = 720), que é a perda da saída óssea já discutida na trajetória. Os dois modelos só se
encontram entre 7,2×10⁷ e 7,2×10⁸ dias. A partir daí, `Cb`, `Mb` e `E2` ficam estáveis (erro de
`Cb` em 2,5×10⁻⁶), e o erro de `C1` cai de 0,36% para a faixa de 10⁻⁷ a 10⁻⁴, que é ruído
numérico. A estabilidade é "marginal" nos dois modelos em todo ponto com tolerância de 10⁻⁵ ou
mais apertada.

## A resposta à orientadora, em uma frase

Para este modelo, a faixa útil da tolerância vai de **10⁻⁶ (a mais frouxa) a 10⁻¹⁰ (a mais
apertada)**, e dentro dela o veredito de longo prazo não muda (APROVADO 6/6 nas cinco décadas).
Com tolerância mais frouxa, o teste aceita pontos que ainda não são equilíbrio. Com tolerância
mais apertada, ele esbarra no piso numérico da integração.

## Os quatro achados (o que o texto pode afirmar)

1. **Dentro da faixa útil, o veredito de longo prazo é robusto.** É o resultado principal: o
   "APROVADO 6/6" do longo prazo não é um acidente da tolerância padrão. Vale contrastar com a
   versão antiga (v-nota, sem `E2` em `C1`), em que o padrão dava REPROVADO 5/6 por `C1` (9,3%)
   e o veredito dependia de onde a integração parava (questão 42). A dependência continua
   existindo para variáveis que vão a zero, mas com o `C1` do original o erro fica abaixo do
   limite em todo ponto convergido. **Cuidado:** a questão 42 (como tratar no critério as
   variáveis que vão a zero) continua aberta com a orientadora. O texto pode dizer que, neste
   caso, ela não muda o veredito, mas não que ela foi resolvida.
2. **Com tolerância frouxa (10⁻³ ou 10⁻⁴), a comparação perde o sentido.** O original "converge"
   no próprio fim da janela (t = 720, que não é um equilíbrio), e o `steadyState` do simplificado
   acha **outro equilíbrio**, o trivial (`Cb = D = 0`), instável. É um exemplo concreto de por
   que o relatório avisa que "só um equilíbrio foi analisado".
3. **Cada modelo passa pelo teste de convergência sozinho, e os dois podem parar em instantes
   diferentes.** Em 10⁻¹¹, o critério comparou t = 7,2×10⁸ com t = 7,2×10⁹ e reprovou. É **a
   única mudança de veredito entre pontos em que os dois modelos convergem**. Com o padrão isso
   não acontece na Verly, então nenhum número atual está contaminado. Mas é uma **limitação da
   biblioteca, ainda não corrigida**: as correções possíveis (integrar os dois até o maior
   instante, ou avisar quando diferem) mudam o critério e dependem da orientadora. No texto, isso
   vai como limitação, e não como algo resolvido.
4. **Há um piso numérico.** Com 10⁻¹², o simplificado não converge nem integrando até 7,2×10¹⁴
   dias: o resíduo estaciona em cerca de 2×10⁻¹¹. É o limite inferior da faixa útil, e vale para
   este modelo com este solver e estas tolerâncias de integração. Não é uma constante.

## Como encaixar no capítulo

Sugestão: uma subseção curta dentro dos resultados de longo prazo da simplificação 1, logo depois
da tabela de equilíbrios, com um título como "Sensibilidade ao teste de convergência". Ordem
sugerida:

1. Uma frase sobre o que a tolerância controla.
2. A tabela da tolerância.
3. A figura do horizonte.
4. Os achados 1 e 2.
5. Os achados 3 e 4, como limitação, ou levados para a seção de limitações.

Material gerado pelo script (a pasta `texto/` não é versionada; rode o script para gerar):

| Arquivo | O que é | Rótulo |
| --- | --- | --- |
| `texto/tabelas/convergencia_tolerancia.tex` | tabela da tolerância, com legenda pronta | `tab:convergencia-tolerancia` |
| `texto/tabelas/convergencia_horizonte.tex` | tabela do horizonte, com legenda pronta | `tab:convergencia-horizonte` |
| `texto/figuras/convergencia_horizonte.pdf` | dois painéis contra o horizonte: resíduo relativo (com a linha de 10⁻⁶) e erro relativo por variável (com o limite de 0,05); a linha vertical marca onde o padrão para | **não tem rótulo**: escreva o `\begin{figure}` e o `\label` |

Para a legenda da figura, diga que `E2` não aparece e que `Mb` aparece só nos primeiros
horizontes: erros abaixo de 10⁻¹² são arredondamento de ponto flutuante e não são desenhados.

Provavelmente só uma das duas tabelas cabe no capítulo. A da tolerância responde à pergunta da
orientadora, e a figura do horizonte explica o porquê. A tabela do horizonte pode ficar de fora
ou ir para um apêndice.

## Trabalho futuro (para a Conclusão)

A versão genérica, que faria essa varredura para qualquer modelo (um subcomando que varre
tolerância, horizonte ou `t_fim` e mostra onde o veredito muda), **não foi implementada** e está
registrada como trabalho futuro em `docs/produto.md`, seção "Fica de fora". O texto deve dar os
três motivos com honestidade:

1. O veredito não muda numa direção só (aqui ele vai de reprovado para aprovado e volta a
   reprovado em 10⁻¹¹), então não há busca binária confiável, só uma grade de valores, que pode
   pular uma faixa curta em que o resultado muda.
2. Cada ponto é uma verificação completa, e na Verly o longo prazo integra até cerca de 10⁹ dias.
3. A interpretação não é automática: a varredura mostra *onde* o veredito muda, mas dizer se a
   causa é o modelo, o teste ou o piso numérico exigiu ler o modelo e os pontos de parada.

A frase-resumo é: "a varredura é genérica, a interpretação não".

## O que não afirmar

- Que a simplificação 1 é fiel ao original: o longo prazo aprova, mas a **trajetória** reprova
  dentro dos 720 dias. Os dois só se encontram depois de cerca de 10⁸ dias (centenas de milhares
  de anos), fora de qualquer sentido biológico (questão 39). Esta análise mostra que o "aprovado"
  do longo prazo é robusto ao teste, e não que ele é relevante para o modelo.
- Que a questão 42 foi resolvida: ela só deixou de mudar o veredito neste caso.
- Que a biblioteca determina automaticamente "o limite de convergência" de um modelo: ela não
  faz isso, e este script vale só para o estudo de caso.
- Que a faixa de 10⁻⁶ a 10⁻¹⁰ vale para outros modelos: ela é desta configuração (modelo, solver
  e tolerâncias de integração).
