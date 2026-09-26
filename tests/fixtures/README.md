# Modelos de brinquedo

Pares de modelos original/simplificado pequenos (2 a 4 variáveis), com veredito conhecido de
antemão. Servem para testar a biblioteca ponta a ponta e como exemplo no README do projeto.

Cada par tem quatro arquivos: `<nome>_original.ant` / `.xml` e `<nome>_simplified.ant` / `.xml`.
O Antimony é a fonte; o SBML é gerado por `build_sbml.py` e versionado junto, para que os testes
não dependam do tradutor:

```bash
python tests/fixtures/build_sbml.py
```

## Como os números abaixo foram medidos

Os dois modelos de cada par são simulados no libRoadRunner com o **mesmo vetor de tempo, solver e
tolerâncias** (`absolute_tolerance = 1e-10`, `relative_tolerance = 1e-8`). O NRMSE é o RMSE
normalizado; como a normalização ainda não está fechada (ver `docs/questoes-em-aberto.md`), estão
anotadas as duas formas usuais — pela **amplitude** (`max - min`) e pela **média** da série de
referência. Os parâmetros foram escolhidos para que as duas fiquem longe do limite de 5%, então o
veredito não depende dessa escolha.

Os valores são conferidos por `tests/test_fixtures.py`.

## 1. `qssa_ok` — deve **PASSAR**

Cadeia `A → B → C` com `k1 = 0,1` e `k2 = 50`. O intermediário `B` é 500 vezes mais rápido que a
entrada, então vale a hipótese de quase-equilíbrio (QSSA): `dB/dt ≈ 0`, ou seja `B ≈ k1·A/k2`.
O simplificado elimina `B` da dinâmica (vira uma regra de atribuição) e a cadeia colapsa em
`A → C` com taxa `k1·A`.

Mapeamento 1:1 (`A → A`, `C → C`), horizonte `t ∈ [0, 40]`, 401 pontos.

| Variável | NRMSE (amplitude) | NRMSE (média) | Limite |
| --- | --- | --- | --- |
| A | 0,00000 | 0,00000 | 0,05 |
| C | 0,00072 | 0,00093 | 0,05 |

`A` é idêntico nos dois modelos (a redução não toca na equação de `A`). O erro em `C` vem só do
transiente inicial de `B`, que dura `1/k2 = 0,02` — desprezível no horizonte simulado.

## 2. `qssa_fail` — deve **FALHAR**

A mesma cadeia e a mesma redução, mas com `k2 = 0,05`: agora o intermediário é **mais lento** que a
entrada (`k2/k1 = 0,5`) e não existe separação de escala de tempo. A QSSA passa a afirmar que o
material chega em `C` assim que sai de `A`, quando na verdade ele fica acumulado em `B`.

Mapeamento 1:1 (`A → A`, `C → C`), horizonte `t ∈ [0, 40]`, 401 pontos.

| Variável | NRMSE (amplitude) | NRMSE (média) | Limite |
| --- | --- | --- | --- |
| A | 0,00000 | 0,00000 | 0,05 |
| C | 0,52006 | 1,02122 | 0,05 |

O par mostra que o veredito não pode olhar só para as variáveis preservadas: `A` bate perfeitamente
e mesmo assim a simplificação é infiel.

## 3. `aggregation` — deve **PASSAR**

Dois compartimentos com dinâmica parecida (entrada constante e decaimento de primeira ordem):
`X1` com `s1 = 1,0`, `d1 = 0,20` e `X2` com `s2 = 0,5`, `d2 = 0,22`. O simplificado agrega os dois
em `X = X1 + X2`, com entrada `s = s1 + s2 = 1,5` e taxa `d = 0,207`, a média de `d1` e `d2`
ponderada pelas entradas.

Mapeamento por soma (`X1 + X2 → X`), horizonte `t ∈ [0, 50]`, 501 pontos.

| Variável | NRMSE (amplitude) | NRMSE (média) | Limite |
| --- | --- | --- | --- |
| X | 0,00523 | 0,00320 | 0,05 |

A agregação não é exata (`d1 ≠ d2`, então a soma de duas exponenciais não é uma exponencial), mas
como as duas escalas são próximas o erro fica uma ordem de grandeza abaixo do limite.

## Resumo

| Par | Tipo de redução | Mapeamento | Veredito esperado | Pior NRMSE (amplitude) |
| --- | --- | --- | --- | --- |
| `qssa_ok` | QSSA com separação de escala forte | 1:1 | passou | 0,00072 |
| `qssa_fail` | a mesma QSSA, sem separação de escala | 1:1 | falhou | 0,52006 |
| `aggregation` | agregação de compartimentos | soma | passou | 0,00523 |
