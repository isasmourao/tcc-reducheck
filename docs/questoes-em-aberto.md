# Questões em aberto — TCC (framework de verificação de modelos)

_Cópia de 26/09/2026. O plano está em `docs/produto.md`; as tarefas, nas issues do repositório. Este arquivo guarda as questões, decisões e referências._

## Contexto da mudança de rumo
- A orientadora sugeriu trocar o foco: sair da **simplificação** do modelo da Verly et al. (2024) e ir para uma **validação robusta**.
- A proposta é um framework com várias métricas selecionáveis e entrada padronizada (modelo original + modelo simplificado). O usuário informa as variáveis "core", o código é alterado o mínimo possível e, no fim, sai um relatório de aprovação.
- As duas simplificações já feitas (9 e 7 variáveis) viram casos de teste: uma deve passar e a outra deve falhar.
- O texto do TCC I está em `docs/tcc1.pdf`. O código original do modelo está em https://github.com/isasmourao/TCC-bone_estradiol (`original_Model/bone_estradiol.py`, função `bonerepair`). No código a variável é `Mo` (letra o), e M1 começa em 0.

## Decisões tomadas
- **26/09**: seguir o caminho do meio, nem script específico nem ferramenta genérica "total". O framework é genérico na arquitetura, limitado no que promete e dá um veredito de aprovado/reprovado baseado em métricas.
- **26/09**: o formato de entrega será uma **biblioteca Python** que ninguém precisa editar. O "template" é o arquivo de configuração (YAML). Uma linha de comando também pode chamar a biblioteca.
- **26/09**: tratar como produto. O MVP está em `docs/produto.md`, com 36 capacidades em 11 módulos, e as tarefas estão nas issues #1–#29, com prazo final em 29/11/2026.

## Decisões pendentes (issue #1)
1. **Validar o escopo com a orientadora.**
2. **Público**: a biblioteca vai ser usada pelo grupo ou é uma prova de conceito para o TCC?
3. **Formato de entrada**: SBML como único formato (proposto). Configuração em YAML. O SED-ML serve de referência para descrever a simulação.
4. **Formato do relatório**: estilo **JEV** (porcentagem aprovada + razões). Falta levantar um exemplo concreto do relatório do JEV. Proposta atual: três níveis (aprovado / aprovado com ressalvas / reprovado).
5. **Nome da biblioteca**: ReduCheck é provisório.
6. **Código das simplificações do TCC I**: onde está? A equação da variável M da simplificação 2 não está no PDF nem no repositório TCC-bone_estradiol.

## Questões técnicas
1. **Mapeamento de variáveis** (ex.: M do simplificado ↔ Mo+M1+M2 do original)
   - Mapeamento 1:1 por nome: fácil.
   - Combinação linear (soma ou soma ponderada, *lumping*): dificuldade média. Cobre a maioria dos casos.
   - Expressão arbitrária: difícil (parser e unidades). Fica como trabalho futuro.
   - Variável eliminada (QSSA): o simplificado precisa expô-la como regra algébrica (*assignment rule* no SBML).
2. **Erro numérico vs. erro do modelo**: fixar solver, tolerâncias e malha de tempo. Medir o "ruído de fundo" rodando o original contra ele mesmo.
3. **Métricas não são neutras**: o MAPE (e o erro relativo de Frøysa) explode perto de zero. O RMSE entre variáveis de escalas diferentes precisa de normalização. O framework deve alertar sobre escolhas inadequadas.
4. **Veredito**: porcentagem de critérios atendidos + razões, com limites configuráveis. Separar critérios **obrigatórios** (reprovam independentemente da porcentagem) de **desejáveis**.
5. **Análise qualitativa genérica**
   - Equilíbrio: integrar até o estado estacionário e refinar com Newton. Encontra *um* equilíbrio, não todos (declarar essa limitação).
   - Estabilidade local: autovalores da Jacobiana. Viável e genérico.
   - Estabilidade global: fora do escopo. Alinhar com a orientadora, porque o texto do TCC I promete essa análise.
6. **Terminologia**: comparar com o original é "verificação de fidelidade". "Validação" costuma significar comparar com dados experimentais. Definir o termo no texto.
7. **Generalidade**: testar com um segundo modelo (Lemaire 2004 ou Komarova 2003, ambos no BioModels).
8. **Simplificação 2 (Mo, M1 e M2 agregados em M)**: verificar cedo se cabe no mapeamento linear.

## Diferença para Frøysa, Fallahi & Blaser (2018)
Artigo: "Evaluating model reduction under parameter uncertainty", *BMC Syst Biol*. https://link.springer.com/article/10.1186/s12918-018-0602-x

É o trabalho mais próximo encontrado até agora e precisa aparecer nos trabalhos relacionados, mas a pergunta que ele responde é outra.

| Aspecto | Frøysa et al. 2018 | Este TCC |
|---|---|---|
| Pergunta | Entre todas as reduções possíveis, qual é a melhor? (seleção, *ranking* relativo) | Esta redução específica é aceitável? (verificação, veredito absoluto) |
| Origem da redução | Gerada pelo próprio método (Rao et al. 2014: fixar espécies no estado estacionário, enumerar as 2^c combinações) | Vem de fora: qualquer método, inclusive feita à mão |
| Tipo de modelo | Redes bioquímicas numa forma matricial específica (ẋ = ZBv + Zv_b) | Qualquer sistema de EDOs em SBML |
| Entrada | Matrizes e vetores em scripts MATLAB | SBML + arquivo de configuração |
| Mapeamento de variáveis | As espécies importantes existem nos dois modelos (sem agregação) | Suporta agregação (M = Mo+M1+M2) |
| Métricas | Uma métrica fixa (erro relativo simétrico) | Métricas escolhidas pelo usuário, com limites por variável |
| Incerteza de parâmetros | Sim: amostragem, clustering e teste de Kolmogorov–Smirnov | Não, no escopo mínimo (possível extensão) |
| Análise qualitativa | Não: pressupõe estabilidade assintótica | Equilíbrio + estabilidade local |
| Saída | Dendrogramas + escore KS + escolha do "melhor" | Relatório com % de critérios atendidos, razões, aprovado/reprovado |
| Código | Scripts suplementares do artigo | Biblioteca reutilizável |

**O que aproveitar do artigo:**
- A métrica de erro simétrico pode virar uma das métricas plugáveis, citando a fonte.
- A ideia de "espécies importantes" sustenta o conceito de variáveis core.
- A incerteza de parâmetros é uma boa extensão ou trabalho futuro ("a aprovação se mantém se os parâmetros variarem ±X%?").

**Ressalva honesta:** a novidade do TCC é de engenharia e integração (padronização, configuração declarativa, métricas plugáveis, relatório), não uma métrica nova. Para um TCC de Computação isso é legítimo, mas o texto deve dizer isso com clareza.

## Trabalhos relacionados (levantamento inicial, 26/09)
Conferir cada item na fonte antes de citar.

**Ferramentas**
- **SBML Test Suite**: compara simulador vs. resultado de referência (tolerância absoluta + relativa). Não compara dois modelos diferentes. https://github.com/sbmlteam/sbml-test-suite
- **BiVeS / COMODI** (Scharm et al. 2016): diff *estrutural* entre versões de modelos. Não simula. https://github.com/SemsProject/BiVeS
- **BioSimulators** (Shaikh et al. 2022): registro de simuladores COMBINE/SED-ML. https://arxiv.org/abs/2203.06732
- **Tellurium / libRoadRunner** (Somogyi et al. 2015): simulação SBML, estado estacionário, Jacobiana e autovalores. Candidato a *motor* do framework. https://doi.org/10.1093/bioinformatics/btv363
- **COPASI**: estado estacionário, estabilidade e separação de escalas. Não verifica reduzido vs. original.
- **AutoReduce** (Pandey): *gera* reduções em Python/SBML, mas não as verifica. https://pypi.org/project/AutoReduce
- **SED-ML**: descreve simulações, sem critérios de aceitação (confirmar na L1V4).
- Ainda falta checar: **sbmlsim**, **PEtab**.

**Artigos sobre verificação de modelos reduzidos**
- Snowden, van der Graaf, Tindall (2017), *Bull Math Biol*. https://pmc.ncbi.nlm.nih.gov/articles/PMC5498684/
- Frøysa, Fallahi, Blaser (2018), *BMC Syst Biol* (ver a comparação acima).
- Hasegawa & Duffull (2018), *AAPS J*: critério composto de desempenho vs. número de estados. https://link.springer.com/article/10.1208/s12248-017-0170-9
- Hasegawa & Duffull (2018), *CPT:PSP*: redução automática de um **modelo de biologia óssea**. https://ascpt.onlinelibrary.wiley.com/doi/abs/10.1002/psp4.12324
- Derbalah et al. (2022), *Br J Clin Pharmacol*: framework de simplificação QSP.

**Credibilidade / V&V**
- ASME V&V 40-2018 e guia da FDA: critérios de aceitação definidos *antes* da comparação. https://www.fda.gov/media/154985/download
- Erdemir et al. (2020), "ten rules" de credibilidade, *J Transl Med*, e a rubrica de conformidade (medRxiv 2024). https://translational-medicine.biomedcentral.com/articles/10.1186/s12967-020-02540-4

**Modelos ósseos disponíveis**
- Lemaire 2004: BioModels **BIOMD0000000278**; também no PMR (CellML)
- Komarova 2003: BioModels **BIOMD0000000148**; também no PMR
- Outros: Pivonka 2008 (PMR), Peterson 2010 (BIOMD0000000613)

**Lacuna plausível**: não foi encontrada ferramenta que, dados o original e o reduzido em formato padrão, com variáveis core e mapeamento declarados, aplique métricas e limites definidos antes, faça comparação qualitativa e gere um relatório de aprovação com razões. Os critérios existem como métodos em artigos, não como ferramenta reutilizável.

## Riscos
- Crescimento de escopo (o maior risco).
- Converter o modelo da Verly para SBML dá trabalho manual subestimado. Mitigação: usar Antimony e comparar com o código atual.
- Prazo: entrega final em 29/11/2026.
