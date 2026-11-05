# referencia/nlrp3/

Material de referência do **modelo da Julia para teste**: ativação do inflamassoma NLRP3 a partir
do NF-κB nuclear. Ele serve para testar se a biblioteca funciona com um modelo que não é o de
Verly et al. (2024), sem mudar o código da biblioteca.

## `nlrp3_original.ipynb`

Cópia **sem nenhuma alteração** do notebook do Google Colab que contém o modelo original.

| | |
| --- | --- |
| Link | <https://colab.research.google.com/drive/1rWdxS2aI9BPARkIULzG4vDL5ztHCElSi> |
| Baixado em | 2026-11-04 |
| SHA-256 | `6ff91a4fbf9bfc24e8cc0988fa94e38687b99c958299c3fcf674f026893b2cf4` |
| Autoria | Julia (origem científica a confirmar: pendente com a Bárbara, questão 55 de `docs/questoes-em-aberto.md`) |

O notebook não está versionado no Colab. Se ele mudar, baixe de novo, compare o SHA-256 e, se
for diferente, refaça `modelos/nlrp3_original.ant` e rode `comparar_sbml.py`.

Os acentos dos comentários já vêm corrompidos no arquivo original (caractere `�`). Eles não
foram corrigidos, porque o arquivo não deve ser editado.

### O modelo

- 13 variáveis de estado, na ordem de `dinamica_nlrp3`: `NLRP3i, NLRP3a, NLRP3o, ASCf, ASCb,
  proC1, C1, proIL1b, IL1bc, IL1be, proIL18, IL18c, IL18e`.
- Entrada externa: `nfkbn(t)`, o NF-κB nuclear como função explícita do tempo (um pulso
  log-normal somado a `nfkb0`). Ela não é variável de estado.
- Tempo em minutos, de 0 a 300 (os gráficos do notebook dizem "Minutos").
- Condições iniciais: `ASCf = proC1 = proIL18 = 1`; as outras são 0.
- No notebook: `solve_ivp` com BDF, `rtol = atol = 1e-4`.

## `nlrp3_simplificado.ipynb`

Cópia **sem nenhuma alteração** do notebook do Google Colab com o modelo simplificado.

| | |
| --- | --- |
| Link | <https://colab.research.google.com/drive/1tHLVyrbm1dvhyVXkAGQdVsugNZyz5eDl> |
| Baixado em | 2026-11-04 |
| SHA-256 | `926ec74b3faed8a36a9134772720cad9233ea6b3cbb5c73724a6b109e510ccfe` |
| Autoria | Julia |

- 8 variáveis, na ordem de `edos`: `NLRP3a, NLRP3o, ASCb, C1, IL18c, IL18e, proIL1B, IL1Be`.
  Todas começam em 0.
- Mesma entrada `nfkbn(t)`, mesmo horizonte e mesmo solver do original.
- O que muda em relação ao original está no cabeçalho de `modelos/nlrp3_simp.ant` e em
  `estudo_de_caso/nlrp3/NOTAS.md`.
- O notebook também lê CSVs de dados do artigo (`nlrp3a.csv`, `b.csv`, ...), que não vieram junto
  e não são usados aqui.

## `comparar_sbml.py`

Compara cada notebook com a sua tradução em SBML (`modelos/nlrp3_original.xml` e
`modelos/nlrp3_simp.xml`):

```bash
python referencia/nlrp3/comparar_sbml.py                # os dois
python referencia/nlrp3/comparar_sbml.py simplificado   # só um
```

- notebook: as células que definem os parâmetros, `nfkbn`, `hill`, `sinal` e as EDOs
  (`dinamica_nlrp3` ou `edos`), executadas sem alteração e integradas com scipy (`solve_ivp`, BDF);
- SBML: libRoadRunner (CVODE);
- os dois com `rtol = 1e-10` e `atol = 1e-12`, e com o mesmo vetor de tempo: 0 a 300 min,
  1001 pontos.

O erro relativo é normalizado pelo maior valor absoluto de cada variável no notebook, como no
modelo da Verly.

### Resultado do simplificado (execução de 2026-11-04)

| Variável | Erro absoluto máximo | Erro relativo máximo |
| --- | --- | --- |
| NLRP3a | 3.624385e-10 | 1.636717e-09 |
| NLRP3o | 3.701484e-10 | 3.672656e-10 |
| ASCb | 1.186317e-08 | 1.186911e-08 |
| C1 | 8.162260e-09 | 8.203905e-09 |
| IL18c | 1.917443e-08 | 4.018151e-08 |
| IL18e | 1.907652e-08 | 1.907652e-08 |
| proIL1B | 1.961820e-08 | 2.464360e-08 |
| IL1Be | 1.425266e-08 | 3.329976e-08 |

Maior erro relativo: **4.02e-08**. Gráfico: `comparacao_sbml_simp.png`. Com as tolerâncias do
próprio notebook, o simplificado também difere da execução precisa em até **22,8 %**.

### Resultado do original (execução de 2026-11-04)

| Variável | Erro absoluto máximo | Erro relativo máximo |
| --- | --- | --- |
| NLRP3i | 5.044302e-11 | 6.683157e-10 |
| NLRP3a | 7.026420e-10 | 3.193052e-09 |
| NLRP3o | 4.734685e-10 | 4.693920e-10 |
| ASCf | 8.272015e-09 | 8.272015e-09 |
| ASCb | 8.272016e-09 | 8.275835e-09 |
| proC1 | 5.560294e-09 | 5.560294e-09 |
| C1 | 5.560293e-09 | 5.588668e-09 |
| proIL1b | 1.352913e-08 | 1.699475e-08 |
| IL1bc | 8.252271e-09 | 2.889464e-08 |
| IL1be | 7.976362e-09 | 1.374329e-08 |
| proIL18 | 2.237241e-08 | 2.237241e-08 |
| IL18c | 1.348262e-08 | 2.802329e-08 |
| IL18e | 1.293498e-08 | 1.293498e-08 |

Maior erro relativo: **2.89e-08**, bem abaixo da tolerância de 1e-4 usada para o modelo da
Verly. Gráfico sobreposto das 13 variáveis: `comparacao_sbml.png`.

> **⚠️ Ponto de atenção.** Com as tolerâncias do próprio notebook (`rtol = atol = 1e-4`), o
> original difere da execução precisa em até **23,5 %** (em `IL1bc`). Os gráficos do notebook
> têm esse erro numérico. Detalhes em `duvidas.md`, item 2.

## `duvidas.md`

Dúvidas e pontos de atenção encontrados na leitura do notebook. Nada foi "corrigido" no SBML:
ele reproduz o notebook como está.
