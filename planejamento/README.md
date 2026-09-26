# Planejamento

- `tarefas.yaml`: fonte das issues #1–#29 (contexto, critérios de aceite, instrução para o Claude).
- `criar_issues.py`: cadastra ou atualiza as issues a partir do YAML.
- `numeros_issues.yaml`: mapa ID da tarefa (T02, W01, …) → número da issue.

Depois de editar o YAML, para refletir nas issues:

```bash
pip install requests pyyaml
GITHUB_TOKEN=$(gh auth token) python planejamento/criar_issues.py isasmourao/tcc-reducheck --atualizar
```

Durante o trabalho, o GitHub é a fonte de verdade: comentários e checkboxes marcados nas issues
são sobrescritos por `--atualizar`, então só rode esse comando para mudanças de planejamento.
