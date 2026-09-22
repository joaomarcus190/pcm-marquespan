# PCM Marquespan Online

Sistema de PCM para acesso por celular e computador, preparado para Render + PostgreSQL.

## Deploy no Render

1. Suba estes arquivos para um repositório GitHub.
2. No Render, escolha **New > Blueprint** e selecione o repositório.
3. O `render.yaml` cria o Web Service e o PostgreSQL.
4. Defina `ADMIN_PASSWORD` e `TECH_PASSWORD` no serviço antes de usar.
5. Faça o primeiro login com `admin` e `equipe` usando as senhas configuradas.

O sistema expõe `/healthz` para teste de saúde.

## Local

```bash
pip install -r requirements.txt
python app.py
```

Sem `DATABASE_URL`, usa SQLite local para desenvolvimento. No Render, o sistema usa `DATABASE_URL` e PostgreSQL automaticamente.

## Segurança

Não use as senhas padrão em produção. O plano gratuito do Render é adequado para teste; para dados reais da empresa, use armazenamento/serviço pago e rotina de backup.
