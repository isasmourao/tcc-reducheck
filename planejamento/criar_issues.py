"""Cadastra labels, milestones e issues no GitHub a partir de tarefas.yaml.

Uso:
    GITHUB_TOKEN=... python criar_issues.py dono/repo            # cadastra
    python criar_issues.py dono/repo --previa tarefas.md         # só gera a prévia em Markdown

É idempotente: labels, milestones e issues que já existem (mesmo título) são reaproveitados.
As dependências são criadas como links para as issues (#número), por isso a ordem do YAML importa.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import requests
import yaml

API = "https://api.github.com"
AQUI = os.path.dirname(os.path.abspath(__file__))
MAPA = os.path.join(AQUI, "numeros_issues.yaml")


def corpo_issue(t: dict, numeros: dict[str, int], marcos: dict[str, dict]) -> str:
    deps = t.get("depende") or []
    dep_txt = ", ".join(f"#{numeros[d]} ({d})" if d in numeros else d for d in deps) or "nenhuma"
    caps = ", ".join(t.get("capacidades") or []) or "—"
    aceite = "\n".join(f"- [ ] {a}" for a in t["aceite"])
    marco = marcos[t["marco"]]
    return f"""**ID:** {t['id']} · **Marco:** {marco['titulo']} · **Semana:** {t['semana']} · **Capacidades:** {caps}
**Depende de:** {dep_txt}

## Contexto
{t['contexto'].strip()}

## O que entrega
{t['entrega'].strip()}

## Critérios de aceite
{aceite}

## Instrução para o Claude
```text
{t['instrucao'].strip()}
```
"""


def labels_da_tarefa(t: dict) -> list[str]:
    labels = list(t["tipo"])
    if t.get("risco"):
        labels.append("risco-alto")
    return labels


def titulo_issue(t: dict) -> str:
    return f"[{t['id']}] {t['titulo']}"


def gerar_previa(dados: dict, caminho: str) -> None:
    marcos = {m["id"]: m for m in dados["marcos"]}
    numeros = {}  # sem números na prévia
    partes = ["# Tarefas do TCC II — MVP e texto\n"]
    partes.append("| ID | Tarefa | Tipo | Marco | Semana | Depende de |\n|---|---|---|---|---|---|")
    for t in dados["tarefas"]:
        partes.append(
            f"| {t['id']} | {t['titulo']} | {', '.join(labels_da_tarefa(t))} | {t['marco']} | {t['semana']} | {', '.join(t.get('depende') or []) or '—'} |"
        )
    partes.append("\n## Marcos\n")
    for m in dados["marcos"]:
        partes.append(f"- **{m['titulo']}** (até {m['prazo']}): {m['descricao']}")
    for m in dados["marcos"]:
        partes.append(f"\n---\n\n# {m['titulo']}\n")
        for t in dados["tarefas"]:
            if t["marco"] == m["id"]:
                partes.append(f"\n## {titulo_issue(t)}\n\n**Labels:** {', '.join(labels_da_tarefa(t))}\n")
                partes.append(corpo_issue(t, numeros, marcos))
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(partes))
    print(f"Prévia gravada em {caminho}")


class GitHub:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})

    def req(self, metodo: str, caminho: str, **kw):
        r = self.s.request(metodo, f"{API}{caminho}", timeout=30, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{metodo} {caminho} → {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else None

    def todos(self, caminho: str) -> list:
        itens, pagina = [], 1
        while True:
            lote = self.req("GET", caminho, params={"per_page": 100, "page": pagina, "state": "all"})
            itens += lote
            if len(lote) < 100:
                return itens
            pagina += 1


def cadastrar(dados: dict, repo: str, token: str) -> None:
    gh = GitHub(repo, token)
    r = f"/repos/{repo}"

    existentes = {l["name"] for l in gh.todos(f"{r}/labels")}
    for l in dados["labels"]:
        if l["nome"] not in existentes:
            gh.req("POST", f"{r}/labels", json={"name": l["nome"], "color": l["cor"], "description": l["descricao"]})
            print(f"label criada: {l['nome']}")

    ms = {m["title"]: m["number"] for m in gh.todos(f"{r}/milestones")}
    num_marco = {}
    for m in dados["marcos"]:
        if m["titulo"] not in ms:
            criado = gh.req("POST", f"{r}/milestones", json={
                "title": m["titulo"], "description": m["descricao"], "due_on": f"{m['prazo']}T23:59:59Z"})
            ms[m["titulo"]] = criado["number"]
            print(f"milestone criado: {m['titulo']}")
        num_marco[m["id"]] = ms[m["titulo"]]

    marcos = {m["id"]: m for m in dados["marcos"]}
    issues = {i["title"]: i["number"] for i in gh.todos(f"{r}/issues") if "pull_request" not in i}
    numeros: dict[str, int] = {}
    for t in dados["tarefas"]:
        titulo = titulo_issue(t)
        if titulo in issues:
            numeros[t["id"]] = issues[titulo]
            print(f"já existe: #{issues[titulo]} {titulo}")
            continue
        criada = gh.req("POST", f"{r}/issues", json={
            "title": titulo,
            "body": corpo_issue(t, numeros, marcos),
            "labels": labels_da_tarefa(t),
            "milestone": num_marco[t["marco"]],
        })
        numeros[t["id"]] = criada["number"]
        print(f"issue criada: #{criada['number']} {titulo}")
        time.sleep(1)  # respeita o limite de criação de conteúdo do GitHub

    with open(MAPA, "w", encoding="utf-8") as f:
        yaml.safe_dump(numeros, f, allow_unicode=True)


def atualizar(dados: dict, repo: str, token: str, mapa: str = MAPA) -> None:
    """Reescreve título, corpo e labels das issues já criadas, usando o mapa ID → número."""
    gh = GitHub(repo, token)
    with open(mapa, encoding="utf-8") as f:
        numeros = yaml.safe_load(f)
    marcos = {m["id"]: m for m in dados["marcos"]}
    for t in dados["tarefas"]:
        n = numeros[t["id"]]
        gh.req("PATCH", f"/repos/{repo}/issues/{n}", json={
            "title": titulo_issue(t),
            "body": corpo_issue(t, numeros, marcos),
            "labels": labels_da_tarefa(t),
        })
        print(f"issue atualizada: #{n} {titulo_issue(t)}")
        time.sleep(0.5)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("repo")
    p.add_argument("--previa")
    p.add_argument("--atualizar", action="store_true", help="reescreve as issues existentes")
    p.add_argument("--arquivo", default=os.path.join(AQUI, "tarefas.yaml"))
    a = p.parse_args()
    with open(a.arquivo, encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    if a.previa:
        gerar_previa(dados, a.previa)
        return
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Defina GITHUB_TOKEN.")
    if a.atualizar:
        atualizar(dados, a.repo, token)
    else:
        cadastrar(dados, a.repo, token)


if __name__ == "__main__":
    main()
