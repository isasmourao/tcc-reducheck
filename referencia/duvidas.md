# Dúvidas sobre o código original (issue #4)

Pontos encontrados na leitura de `referencia/bone_estradiol.py`
(commit `777a213b74a935b9269aa951a2ccb3244602cf20`). **Nenhum deles foi alterado** em
`modelos/verly_original.ant`: o modelo em SBML reproduz o código original exatamente como está.
Cada item precisa de uma resposta da Isabella / da orientadora antes do texto do TCC II.

## 0. Versão do modelo (ponto de atenção principal)

A Isabella confirmou em 2026-09-26 que este commit é a versão homologada e o trabalho seguiu com
ela. Mesmo assim, é preciso **voltar e reconferir** se os valores de parâmetros deste commit são
os mesmos usados nos resultados do TCC I — o commit se chama "Alteração de valores de
parametros". Se houver divergência, `verly_original.ant` precisa ser refeito.

## 1. `E2_max` é o mesmo valor da condição inicial de `E2`

`bonerepair` recebe `E2_max` como argumento e o script sempre passa o valor inicial de `E2`
(0.060 na primeira chamada, 0.019 na segunda). Com isso a equação

```
dE2/dt = ((E2max - E2)/E2max) * ae2 * E2 - de2 * E2
```

começa sempre com o termo logístico zerado, e `E2` só cai (por `de2`) até o equilíbrio
`E2 = E2max * (1 - de2/ae2) = 0.94 * E2max`. Isso é intencional? Ou `E2max` deveria ser um
parâmetro fixo (por exemplo 0.019, "artigo") independente da condição inicial?
**No SBML: `E2max = 0.060` e `E2(0) = 0.060`, reproduzindo a primeira chamada do script.**

## 2. Parâmetro `a_ed` declarado e não usado

O código define `a_ed = 4.71e6` e também `aed = 4.71e6`, mas `RD` é chamada com `aed`. Os dois
têm o mesmo valor, então não muda o resultado — é só duplicação. **No SBML os dois parâmetros
existem, e a equação de `D` usa `aed`, como no original.**

## 3. Termo `E2` na equação de `C1`

```
dC1/dt = H1*(k_o*D + k_1*M1) - (d_c1*C1)*E2
```

O estradiol multiplica o termo de **degradação** de `C1`, enquanto em `C2` ele multiplica o termo
de **produção**. Confere com o artigo de Verly et al. (2024)? Como `E2` fica na ordem de 0.056, a
meia-vida efetiva de `C1` fica ~18x maior do que `d_c1` sugere.

## 4. Nomes das constantes de saturação logística: `K_lm` e `k_lb`

`Cm` satura em `K_lm = 1e6` e `Cb` em `k_lb = 1e6`. Os nomes seguem convenções diferentes
(maiúscula/minúscula) para o mesmo papel. Não muda nada numericamente; é só para conferir se não
houve troca de variável em algum momento.

## 5. Comentários que não batem com o uso das funções

- `G2` está comentada como "Rate of differentiation of M_1 into M_0", mas é usada como taxa de
  diferenciação de `Mo` em `M2` (`dM2dt = G2*Mo + ...`).
- `H1` e `H2` têm comentários quase idênticos ("Inhibitory effect of the ... cytokine"), embora
  usem parâmetros diferentes (`a_12` e `a_22`), ambos em função de `C2`.
- `Am` está comentada como "Inhibitory effect of the anti-inflammatory cytokine", mas é a
  proliferação de `Cm`.

São só comentários; as equações foram reproduzidas como estão.

## 6. Horizonte e número de pontos da simulação

O script original simula **360 dias com `np.linspace(0, days)`, ou seja, 50 pontos**. A issue #4
pede a comparação em **720 dias com 1000 pontos**, e foi isso que `comparar_sbml.py` fez. Qual
horizonte vale para os resultados do TCC II? (Em 720 dias o sistema já está em equilíbrio.)

## 7. Valores comentados no código

Há alternativas comentadas nas condições iniciais e nos parâmetros: `D = 1000000 #5.0*10**5`,
`C1 = 0 #100.0`, `Cm = 2500 #1000.0`, `Cb = 0.0 # 1.8*10**6`, `d_c1 = 0.2 # 20`. Foram usados os
valores ativos (não os comentados). Confirmar que é isso mesmo.

## 8. `Mo` começa em 4000 e cai para ~0.015

Nas primeiras horas `Mo` despenca (RM é quase constante e pequena, `kmax = 0.015`, enquanto
`d_o + G1 + G2` é grande). O regime de interesse do TCC é esse mesmo? Para o MAPE, atenção
também a `M1`, que começa em 0.
