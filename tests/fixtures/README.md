# Modelos de brinquedo

Pares de modelos original/simplificado pequenos (2 a 4 variáveis), com veredito conhecido de
antemão. Servem para testar a biblioteca ponta a ponta e como exemplo no README do projeto.

Cada par tem quatro arquivos: `<nome>_original.ant` / `.xml` e `<nome>_simplified.ant` / `.xml`.
O Antimony é a fonte; o SBML é gerado por `build_sbml.py` e versionado junto, para que os testes
não dependam do tradutor:

```bash
python tests/fixtures/build_sbml.py
```

## Configurações prontas

Os três pares têm uma configuração YAML ao lado, usada pelos testes de ponta a ponta
(`tests/test_pipeline.py`) e servindo de exemplo mínimo do formato de entrada:

| Arquivo | Par | Mapeamento | Veredito esperado |
| --- | --- | --- | --- |
| `config_qssa_ok.yaml` | `qssa_ok` | 1:1 | aprovado |
| `config_qssa_fail.yaml` | `qssa_fail` | 1:1 | reprovado |
| `config_aggregation.yaml` | `aggregation` | soma (`[X1, X2]`) | aprovado |

Os caminhos dentro do YAML são relativos ao próprio arquivo, então os testes copiam a
configuração e os modelos para uma pasta temporária e rodam ali.

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

### O próprio `B`, a variável eliminada

`B` sai da dinâmica mas continua legível no simplificado, como regra de atribuição
(`B := k1·A/k2`). Comparado com o `B` do original, ele **não passa** no limite de 0,05:

| Variável | NRMSE (amplitude) | NRMSE (média) | Limite |
| --- | --- | --- | --- |
| B | 0,05069 | 0,20464 | 0,05 |

O erro está inteiro em **um único ponto**, `t = 0`: o original começa com `B = 0` e a regra de
atribuição já diz `B = k1·A(0)/k2 = 0,02`, que é a amplitude inteira da série. É a *camada
inicial* da QSSA — a aproximação só vale depois que o transiente rápido passa. Tirando esse
ponto, o NRMSE por amplitude cai para 0,00075, da mesma ordem do erro em `C`.

Por isso `B` entra no `exemplos/config_exemplo.yaml` com `core: false`: é uma variável cuja
fidelidade a simplificação não promete. O par serve de exemplo de que o veredito depende de
quais variáveis são declaradas core, e de que um único ponto da malha pode decidir um critério
(ver `docs/questoes-em-aberto.md`).

### As outras métricas na mesma variável

As cinco métricas do MVP (issue #11), medidas em `C` no par `qssa_ok`, com a mesma configuração.
Conferidas por `tests/test_pipeline.py`.

| Métrica | Valor | Onde |
| --- | --- | --- |
| nrmse | 0,00072 | — |
| mape | 0,00277 | 1 dos 401 pontos excluído (`C(0) = 0`) |
| erro_max_abs | 0,01971 | t = 0,1 |
| erro_max_rel | 0,24695 | t = 0,1 |
| erro_estacionario | 0,00004 | último ponto |

O par é aprovado por NRMSE e seria **reprovado** pelo erro máximo relativo com o mesmo limite de
0,05: o pior ponto está dentro da camada inicial da QSSA, onde o original ainda é pequeno. É a
mesma coisa que acontece com `B`, agora numa variável preservada — ver `docs/questoes-em-aberto.md`,
itens 14, 17 e 18.

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

No par `qssa_fail` a variável eliminada também foi medida, e erra muito mais: NRMSE 1,14056 por
amplitude, 1,52816 pela média — ali o problema não é só a camada inicial, é a QSSA inteira.
