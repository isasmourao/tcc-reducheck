# referencia/

Material de referência do estudo de caso: o modelo de remodelação óssea na menopausa de
Verly et al. (2024).

## `bone_estradiol.py`

Cópia **sem nenhuma alteração** de `original_Model/bone_estradiol.py` do repositório
[isasmourao/TCC-bone_estradiol](https://github.com/isasmourao/TCC-bone_estradiol).

| | |
| --- | --- |
| Commit de origem | `777a213b74a935b9269aa951a2ccb3244602cf20` |
| Mensagem do commit | "Alteração de valores de parametros" |
| Data | 2025-07-30 |
| Caminho no repositório de origem | `original_Model/bone_estradiol.py` |
| Baixado em | 2026-09-26 |

> **⚠️ Ponto de atenção — versão do modelo.** A Isabella confirmou em 2026-09-26 que esta é a
> versão homologada do modelo, e o trabalho seguiu com ela. Ainda assim, **antes de fechar o
> texto do TCC II é preciso voltar aqui e reconferir**, contra o texto do TCC I e com a
> orientadora, se os valores de parâmetros deste commit são mesmo os usados nos resultados do
> TCC I. O commit de origem se chama justamente "Alteração de valores de parametros", então há
> risco real de divergência. Se a versão mudar, é preciso refazer `modelos/verly_original.ant`,
> reexportar o SBML e rodar `comparar_sbml.py` de novo.

Este arquivo não deve ser editado. Ele existe para provar que o modelo em SBML reproduz o
código original.

## `comparar_sbml.py`

Compara o código original com a tradução em SBML:

```bash
python referencia/comparar_sbml.py
```

- original: `bonerepair` de `bone_estradiol.py`, integrado com scipy (`odeint`, LSODA), como no
  script original;
- SBML: `modelos/verly_original.xml`, integrado com libRoadRunner (CVODE, rtol 1e-10, atol 1e-12);
- mesmo vetor de tempo nos dois: 0 a 720 dias, 1000 pontos;
- condições iniciais e `E2_max` iguais aos da primeira chamada do script original
  (`E2(0) = E2max = 0.060`).

O erro relativo de cada variável é normalizado pela escala da própria trajetória (o maior valor
absoluto atingido no modelo original), porque seis das onze variáveis começam em zero e uma razão
ponto a ponto não estaria definida ali.

### Resultado (execução de 2026-09-26)

| Variável | Erro absoluto máximo | Erro relativo máximo |
| --- | --- | --- |
| D | 1.473946e-05 | 1.473946e-11 |
| Mo | 7.719225e-06 | 1.929806e-09 |
| M1 | 7.628737e-06 | 4.116161e-09 |
| M2 | 8.539305e-07 | 1.721934e-09 |
| C1 | 1.344888e-07 | 1.343432e-08 |
| C2 | 7.530568e-10 | 8.929179e-09 |
| Cm | 1.860432e-02 | 1.889832e-08 |
| Cb | 5.843171e-03 | 1.635608e-08 |
| Mc | 3.494488e-08 | 3.667985e-08 |
| Mb | 3.498876e-08 | 3.502596e-08 |
| E2 | 2.037676e-13 | 3.396126e-12 |

Maior erro relativo entre as variáveis: **3.67e-08**, bem abaixo da tolerância de 1e-4 pedida na
issue #4. O que sobra é a diferença esperada entre dois integradores diferentes (LSODA e CVODE).

Gráfico sobreposto das 11 variáveis: `comparacao_sbml.png`.

## `duvidas.md`

Lista de dúvidas e pontos de atenção encontrados na leitura do código original. Nada disso foi
"corrigido" no modelo em SBML: o modelo reproduz o original como está.
