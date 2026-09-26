# ReduCheck

Biblioteca Python que verifica se um modelo de EDOs simplificado é fiel ao original: recebe os dois
modelos em SBML mais um arquivo YAML de configuração e emite um veredito (aprovado / aprovado com
ressalvas / reprovado) com a porcentagem de critérios atendidos e as razões de cada falha.

> Nome provisório. TCC II de Ciência da Computação (UFJF) — Isabella Mourão. Em desenvolvimento:
> este repositório ainda é o esqueleto do projeto, sem a lógica de verificação.

## Instalação

Requer Python 3.11 ou superior.

```bash
git clone https://github.com/isasmourao/tcc-reducheck.git
cd tcc-reducheck
python -m venv .venv
source .venv/bin/activate        # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Desenvolvimento

```bash
pytest              # testes
ruff check .        # lint
```

## Documentação

- `docs/produto.md` — escopo, formato do input (YAML), formato do output e regra do veredito
- `docs/questoes-em-aberto.md` — decisões tomadas e pendentes, trabalhos relacionados
- `CLAUDE.md` — contexto do projeto, estrutura de pastas e convenções
