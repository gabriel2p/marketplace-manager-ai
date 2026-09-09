# Marketplace Manager AI (Versão Definitiva 10/10)

Sistema multiagente autônomo de inteligência comercial, precificação determinística, testes de estresse, criação de anúncios e governança para marketplaces (Mercado Livre e Shopee).

---

## 🌟 O que foi construído

Este sistema é a implementação direta da arquitetura de 15 camadas do diagrama:

1. **Intake & Briefing (Camadas 1 & 3):** Coleta estruturada de SKU, CMV, margens alvo, estoque, cubagem e diferenciais.
2. **Evidence Store Versionado (Camada 6):** Rastreabilidade ponta a ponta com classificação metodológica de cada dado (`FATO`, `CALCULO`, `ESTIMATIVA`, `INFERENCIA`) e nível de confiança (0 a 100%).
3. **Agentes Especialistas Paralelos (Camada 7):**
   - *Product Intelligence:* Extração de benefícios, proposta de valor e persona.
   - *Market Intelligence:* Benchmarking de preços concorrentes no Mercado Livre e elasticidade.
   - *Marketplace Specialist:* Regras de SEO do Mercado Livre (título estrito de até 60 caracteres, atributos obrigatórios).
4. **Financial Engine Determinístico (Camada 7.4):**
   - Cálculo exato centavo a centavo das tabelas oficiais do Mercado Livre (comissões Clássico vs Premium, barreira de R$ 79,00 para frete grátis e taxa fixa de R$ 6,00).
   - Cálculo de ponto de equilíbrio (Break-even), ACOS máximo permitido e ROI.
5. **Scenario & Stress-Test Engine (Camada 9):**
   - Simulação automática dos 4 cenários:
     - **Conservador:** Margem máxima e segurança.
     - **Base:** Equilíbrio ótimo entre volume e rentabilidade.
     - **Agressivo:** Ganho acelerado de volume e Buy Box.
     - **Adverso (Stress-Test):** Resistência a concorrência agressiva (-10%), inflação de fornecedor (+10%), aumento de leilão de Ads (+30%) e devoluções (5%).
6. **Viability & Decision Gate (Camadas 10 & 11):**
   - Classificação objetiva: **A (Viável)**, **B (Viável com Condições)**, **C (Testar em Escala Reduzida)** ou **D (Não Viável)**.
   - Motor de alternativas caso a margem esteja ameaçada (kits, combos, renegociação).
7. **Listing & Creative Intelligence (Camadas 12.1 a 12.6):**
   - Título otimizado para o algoritmo do Mercado Livre (<= 60 caracteres).
   - Roteiro estratégico de 6 fotos de alta conversão (Fundo branco puro 255,255,255, ângulos, infográfico de medidas, lifestyle, diferenciais e embalagem).
   - Descrição persuasiva completa com Ficha Técnica e FAQ.
   - Estratégia de Product Ads (ACOS/ROAS e palavras-chave).
8. **Human Approval Gate (Etapa 12.7):**
   - **Parada obrigatória de segurança:** O sistema nunca publica nada sem aprovação expressa do operador humano (**Aprovar**, **Ajustar** ou **Rejeitar**).
9. **Bounded Autonomy Guardrails (Camada 13):**
   - Travas inegociáveis: margem mínima obrigatória, limite de alteração autônoma de preço (±3%) e verificação de duplicidade por chave de idempotência.
10. **Modo Seguro Sandbox:**
    - Simulador de voo que gera o payload canônico oficial da API do Mercado Livre (`/items`) para validação sem qualquer risco de alterar sua conta real.

---

## 🔒 Autenticação & Tela de Login

O sistema possui proteção de acesso via tela de login integrada:
- **Usuário padrão:** `admin`
- **Senha padrão:** `admin123`

Você pode alterar essas credenciais a qualquer momento via variáveis de ambiente no Render (`ADMIN_USER` e `ADMIN_PASSWORD`).

---

## ☁️ Como Hospedar no Render (Guia Passo a Passo)

O sistema já está pronto para deploy gratuito no **[Render.com](https://render.com)**.

### Passo 1: Subir o projeto para o seu GitHub
1. Crie um repositório no seu GitHub (público ou privado).
2. Envie os arquivos do projeto para o repositório (`git add .`, `git commit -m "Deploy Marketplace Manager"`, `git push`).

### Passo 2: Criar o Web Service no Render
1. Acesse o painel do [Render](https://dashboard.render.com) e clique em **New +** > **Web Service**.
2. Conecte o repositório do GitHub que você acabou de criar.
3. Configure os campos:
   - **Name:** `marketplace-manager-ai`
   - **Language / Runtime:** `Python 3`
   - **Build Command:** `pip install -r backend/requirements.txt`
   - **Start Command:** `python servidor_local.py`
   - **Instance Type:** `Free`

### Passo 3: Configurar Variáveis de Ambiente (Environment Variables)
No painel do Render, na aba **Environment**, adicione:
- `ADMIN_USER`: seu usuário de login (ex: `admin`)
- `ADMIN_PASSWORD`: sua senha forte de acesso (ex: `SuaSenhaSegura@2026`)
- `ML_APP_ID`: seu App ID do Mercado Livre Developers (opcional)
- `ML_CLIENT_SECRET`: seu Client Secret do Mercado Livre Developers (opcional)

### Passo 4: Conectar com o Mercado Livre (OAuth Oficial em HTTPS)
1. No [Mercado Livre Developers](https://developers.mercadolivre.com.br), edite seu aplicativo.
2. Em **Redirect URI**, coloque a URL HTTPS fornecida pelo Render:
   `https://seu-app.onrender.com/api/auth/callback`
3. Ao acessar seu aplicativo no Render, clique em **"Conectar API Oficial ML"** e faça a autorização oficial em 1 clique!
4. Pronto! O agente passará a puxar preços, fotos e links 100% oficiais direto do Mercado Livre Brasil.

---

## 🚀 Como Visualizar e Testar Localmente

1. Execute o servidor:
   ```bash
   python servidor_local.py
   ```
2. Abra seu navegador em `http://localhost:8000`.
3. Insira o usuário `admin` e senha `admin123`.
4. O painel será carregado com a análise de mercado e os concorrentes verificados da Garrafa Térmica Inox.
