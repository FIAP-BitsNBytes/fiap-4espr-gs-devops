# Segurança e LGPD by design

O público inclui crianças e adolescentes. A LGPD (Lei 13.709/2018, art. 14) exige que o tratamento desses dados seja feito no melhor interesse do menor, com consentimento específico de um responsável no caso de crianças, coleta limitada ao necessário e informação em linguagem simples. O projeto aplica a regra mais protetiva a todos os menores de 18 anos.

## 1. Dados pessoais: o que existe e o que não existe

| Dado | Guardado? | Finalidade | Proteção |
|---|---|---|---|
| Apelido | Sim | Identificar a conta sem expor o nome | — |
| Senha | Só o hash (scrypt, Werkzeug) | Autenticação | Irreversível |
| Série e faixa de idade (3 faixas) | Sim | Adequar monitorias e exigir consentimento | Faixa em vez de data de nascimento |
| Bairro | Sim | Monitorias próximas e indicadores por território | Sem rua, número ou CEP |
| E-mail do responsável / do voluntário | Sim, cifrado | Consentimento; contato da coordenação | Fernet (AES-128-CBC + HMAC), chave no Key Vault; exibido mascarado |
| Nome completo, CPF, RG, endereço, telefone, data de nascimento, foto, documento | **Não** | — | Não coletado |

O comprovante lido pela Visão Computacional não é armazenado por este app: `POST /api/v1/endereco` devolve só bairro, cidade e UF e descarta o resto.

## 2. Consentimento e direitos do titular

- **Menor de 18 anos**: a conta nasce como `pendente_consentimento`. O responsável recebe um link de uso único (só o hash do token fica no banco), lê o resumo do tratamento e autoriza ou nega. Negou: o cadastro é apagado na hora. Sem resposta em 30 dias: apagado automaticamente.
- Fica registrado **quando** e **qual versão** do Aviso de Privacidade foi aceita.
- **Acesso e portabilidade**: botão “Baixar meus dados” (JSON).
- **Eliminação**: botão “Apagar minha conta”, com confirmação por senha; remove conta, inscrições e monitorias.
- **Transparência**: página `/privacidade` em linguagem simples.
- **Boletim por e-mail**: só para voluntários adultos que marcaram a opção.

Limitação conhecida do MVP: o envio do e-mail ao responsável ainda não está ligado, então o link aparece na tela após o cadastro, com aviso. Em produção ele deve ser enviado somente ao e-mail informado (por exemplo com Azure Communication Services).

## 3. Quem vê o quê (acesso por papel)

**Dentro da aplicação**

| Papel | Pode | Não pode |
|---|---|---|
| Aluno | Inscrever-se, ver e apagar os próprios dados | Ver dados de outros alunos |
| Voluntário (após aprovação) | Publicar monitorias; ver apelido e série dos inscritos | Ver contato ou bairro dos alunos |
| Coordenação (admin) | Aprovar voluntários; ver indicadores agregados (grupos < 5 ocultos) e a trilha de auditoria | Ver e-mail de responsáveis |
| Integração (X-API-Key) | Cadastro em lote e lista do boletim (adultos) | Qualquer dado de aluno |

**Na Azure (RBAC)**

| Identidade | Papel | Escopo |
|---|---|---|
| Identidade gerenciada do Web App | Key Vault Secrets User (só leitura) | Apenas o Key Vault |
| Identidade do GitHub Actions (OIDC) | Website Contributor | Apenas o Web App |
| Quem provisiona | Key Vault Secrets Officer | Apenas o Key Vault |
| Professor e demais integrantes | Reader | Resource Group |

## 4. Segredos fora do código

- Nenhum segredo no repositório: `gitleaks` roda a cada commit e `.gitignore` bloqueia `.env`, bancos e publish profiles.
- `SECRET_KEY`, `FERNET_KEY`, `ADMIN_PASSWORD` e `INTEGRATION_API_KEY` são gerados pelo script direto no Key Vault, sem aparecer na tela.
- O App Service lê por **referência ao Key Vault** (`@Microsoft.KeyVault(...)`) usando a identidade gerenciada.
- Em produção a aplicação **não sobe** se `SECRET_KEY` ou `FERNET_KEY` faltarem.
- O deploy usa OIDC: o GitHub guarda só identificadores (client, tenant, subscription), que não são segredos.

## 5. Proteções da aplicação e da plataforma

| Camada | Controle |
|---|---|
| Transporte | HTTPS only, TLS mínimo 1.2, HSTS, FTP desligado, autenticação básica de deploy desligada |
| Navegador | Content-Security-Policy restrita a `'self'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin` |
| Sessão | Cookie `Secure`, `HttpOnly`, `SameSite=Lax`, expira em 2 h; CSRF em todos os formulários |
| Abuso | Limite de requisições por IP (login, cadastro, tutor) |
| Injeção | ORM com parâmetros; templates com escape automático |
| Logs | Sem apelido, e-mail ou IP nas mensagens da aplicação; auditoria registra a ação, nunca o conteúdo |
| Cadeia de suprimentos | Dependências com versão fixa, `pip-audit`, Dependabot, CodeQL, `bandit` |

## 6. Riscos aceitos no MVP

- **Dados fora do Brasil nesta fase.** A assinatura de avaliação não tinha cota de App Service em Brazil South, então o ambiente está em West US 3 (EUA). O Aviso de Privacidade informa isso. O MVP opera com dados de demonstração; antes de receber estudantes reais o ambiente deve ser recriado em Brazil South.
- A faixa de idade é autodeclarada.
- SQLite não tem cifragem do arquivo inteiro; o campo sensível (e-mail) é cifrado na aplicação e o disco do App Service é cifrado em repouso pela plataforma.
- O link de consentimento leva o token no endereço. Ele é excluído da telemetria do Application Insights (`OTEL_PYTHON_FLASK_EXCLUDED_URLS`), mas aparece nos logs HTTP da plataforma, que também registram o IP de origem. Mitigação: token de uso único, acesso ao Log Analytics restrito por RBAC e retenção de 30 dias.
- O limite de requisições fica em memória (uma instância). Ao escalar, mover para Redis.
