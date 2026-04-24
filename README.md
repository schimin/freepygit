# Git Manager

Gerenciador visual de múltiplos repositórios Git (GitHub, GitLab, Bitbucket, etc.)
Inspirado no SmartGit. Feito em Python + Tkinter. Compila para `.exe` sem dependências.

---

## Funcionalidades

| Feature | Descrição |
|---|---|
| **Multi-repo** | Gerencie dezenas de repos em um único lugar |
| **Grupos** | Organize repos por projeto/cliente/time |
| **Status visual** | Ícones e cores: ✓ clean · ● modified · ↓ behind · ↑ ahead · ↕ diverged |
| **Fetch / Pull / Push** | Individual ou todos de uma vez |
| **Commit Log** | Visualize os últimos 80 commits de qualquer repo |
| **Changes** | Lista os arquivos modificados (git status) |
| **Branches** | Lista branches locais e remotas |
| **Console** | Log colorido de todas as operações git |
| **Contexto** | Clique direito no repo para opções rápidas |
| **Terminal** | Abre cmd.exe já no diretório do repo |
| **Pesquisa** | Filtro de repos pelo nome em tempo real |
| **Persistência** | Repos salvos em `~/.gitmanager_repos.json` |

---

## Como compilar para .exe no Windows

### Pré-requisitos
- Python 3.9 ou superior → https://python.org
- Git instalado → https://git-scm.com

### Passos

```bat
# 1. Abra o CMD nesta pasta
cd caminho\para\gitmanager

# 2. Execute o script de build (instala PyInstaller e compila)
build.bat
```

O executável final estará em `dist\GitManager.exe` (~12 MB, sem dependências externas).

### Alternativa manual

```bat
pip install pyinstaller
pyinstaller gitmanager.spec --noconfirm --clean
```

---

## Rodar sem compilar (modo dev)

```bat
pip install tk   # já incluso no Python padrão
python gitmanager.py
```

---

## Adicionar um repositório

1. Clique em **＋ Add Repo** (toolbar ou barra lateral)
2. Selecione a pasta do repositório (deve conter `.git/`)
3. Informe o grupo (opcional: ex: "Trabalho", "Pessoal")
4. O repo aparece na lista com status atualizado automaticamente

---

## Arquivo de configuração

Os repos ficam salvos em:
```
C:\Users\<SeuUsuario>\.gitmanager_repos.json
```

Pode ser copiado/versionado para compartilhar a lista de repos entre máquinas.

---

## Autenticação SSH / HTTPS

O app usa o `git` do sistema. Se seus repos precisam de autenticação:

- **SSH**: configure `~/.ssh/config` e `ssh-agent` normalmente
- **HTTPS**: use o Git Credential Manager (instalado com Git for Windows)
- **GitLab/GitHub tokens**: configure via `git credential store` ou `.netrc`

Não é necessário nenhuma configuração extra no app.
