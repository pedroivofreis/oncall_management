"""
==============================================================================
ONCALL HUMANA - SYSTEM MASTER v9.0 "THE CITADEL"
==============================================================================
Desenvolvido por: Pedro Reis
Data: Fevereiro/2026
Versão: 9.0 Enterprise Edition (Full Verbose)

Descrição:
Sistema de ERP para gestão de horas, pagamentos e projetos.
Inclui lógica de conversão de horas (HH.MM -> Decimal), gestão de usuários,
aprovação em massa e BI financeiro.

Tecnologias: Streamlit, Pandas, SQLAlchemy, PostgreSQL (Neon).
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import uuid
import time
import io
from sqlalchemy import text

# ==============================================================================
# 1. CONFIGURAÇÃO INICIAL DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="OnCall Humana - Master v9.0",
    layout="wide",
    page_icon="🛡️",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.oncall.com.br/help',
        'Report a bug': "mailto:suporte@oncall.com.br",
        'About': "# OnCall Humana ERP v9.0\nSistema de Gestão de Horas e Pagamentos."
    }
)

# ==============================================================================
# 2. ESTILIZAÇÃO CSS AVANÇADA (ENTERPRISE UI)
# ==============================================================================
st.markdown("""
<style>
    /* Ajuste do container principal para maximizar espaço */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 5rem;
        max-width: 95% !important;
    }

    /* Estilo dos Cards de Métricas (KPIs) */
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        transition: transform 0.2s ease-in-out;
    }
    
    div[data-testid="stMetric"]:hover {
        border-color: #0f54c9;
        transform: translateY(-2px);
    }

    /* Labels de formulários mais legíveis */
    label {
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        color: inherit;
    }

    /* Cabeçalhos de Expander mais destacados */
    .streamlit-expanderHeader {
        font-weight: 700;
        font-size: 1.05rem;
        color: #0f54c9;
        background-color: rgba(128, 128, 128, 0.05);
        border-radius: 5px;
    }

    /* Tabelas (Dataframes) com bordas definidas */
    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 5px;
        padding: 5px;
    }

    /* Botões Primários */
    button[kind="primary"] {
        font-weight: bold;
        border: 1px solid rgba(255, 75, 75, 0.5);
    }
    
    /* Divisorias mais sutis */
    hr {
        margin-top: 1rem;
        margin-bottom: 1rem;
        border-color: rgba(128, 128, 128, 0.2);
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 3. GERENCIAMENTO DE CONEXÃO COM O BANCO DE DADOS
# ==============================================================================
class DatabaseManager:
    """Classe responsável por gerenciar conexões e execuções no banco."""
    
    @staticmethod
    def get_connection():
        """
        Estabelece conexão segura com o banco de dados Neon (PostgreSQL).
        Retorna o objeto de conexão.
        """
        try:
            # Cria a conexão usando a engine nativa do Streamlit
            # ttl=0 garante que não cacheie a conexão de forma perigosa
            c = st.connection("postgresql", type="sql")
            
            # Query leve para 'acordar' o banco serverless e testar latência
            c.query("SELECT 1", ttl=0) 
            
            return c
        except Exception as e:
            st.error("🔴 Erro Crítico de Conexão com o Banco de Dados.")
            st.error(f"Detalhe técnico: {e}")
            st.info("Verifique a internet ou as credenciais em .streamlit/secrets.toml")
            st.stop()

# Instância global da conexão
conn = DatabaseManager.get_connection()

# ==============================================================================
# 4. BIBLIOTECA DE FUNÇÕES UTILITÁRIAS (HELPER FUNCTIONS)
# ==============================================================================

def convert_hhmm_to_decimal(pseudo_hour):
    """
    Converte o formato visual HH.MM (Ex: 2.30) para Decimal (2.50).
    Isso é fundamental para que o cálculo financeiro (Horas * Valor) seja exato.
    
    Args:
        pseudo_hour (float/str): O valor digitado pelo usuário (ex: 1.30 para 1h30min).
        
    Returns:
        float: O valor em horas decimais (ex: 1.50).
    """
    try:
        if pd.isna(pseudo_hour) or pseudo_hour == "":
            return 0.0
        
        # Garante que tratamos como string formatada para evitar erros de float
        val_str = f"{float(pseudo_hour):.2f}"
        
        # Separa a parte inteira (horas) da decimal (minutos)
        parts = val_str.split('.')
        if len(parts) != 2:
            return float(pseudo_hour)
            
        horas_inteiras = int(parts[0])
        minutos = int(parts[1])
        
        # Proteção: Se o usuário digitar 1.90 (90 minutos), assumimos que ele errou
        # ou que já está tentando inserir decimal.
        # Regra de Negócio: Se minutos >= 60, trata como decimal puro.
        if minutos >= 60:
            return float(pseudo_hour)
            
        # Cálculo: Horas + (Minutos / 60)
        horas_decimais = horas_inteiras + (minutos / 60)
        
        return horas_decimais
    except Exception:
        # Em caso de qualquer erro bizarro, retorna 0.0 para não quebrar a aplicação
        return 0.0

def normalize_text_fields(text_val):
    """
    Padroniza strings para garantir consistência no Banco de Dados e BI.
    Remove espaços extras e resolve variações comuns de escrita.
    """
    if not isinstance(text_val, str):
        return "N/A"
        
    t = text_val.strip().lower()
    
    # Mapeamento de normalização
    if "back" in t and "end" in t: return "Back-end"
    if "front" in t and "end" in t: return "Front-end"
    if "dados" in t or "data" in t: return "Eng. Dados"
    if "infra" in t or "devops" in t: return "Infraestrutura"
    if "qa" in t or "test" in t: return "QA / Testes"
    if "banco" in t: return "Banco de Dados"
    if "reuni" in t: return "Reunião"
    if "gest" in t or "agile" in t: return "Gestão"
    if "design" in t: return "Design/UX"
    if "api" in t: return "Integrações/API"
    
    return text_val.capitalize()

def format_currency_brl(value):
    """Formata float para string de moeda BRL."""
    if pd.isna(value): return "R$ 0,00"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_competence_from_date(date_obj):
    """
    Gera a string de competência (YYYY-MM) a partir de um objeto date.
    Args: date_obj (datetime.date)
    Returns: str (Ex: '2026-02')
    """
    if not date_obj:
        return datetime.now().strftime("%Y-%m")
    return date_obj.strftime("%Y-%m")

# ==============================================================================
# 5. DATA ACCESS LAYER (DAL) - FUNÇÕES DE LEITURA
# ==============================================================================
# Utilizamos ttl=0 para garantir que os dados estejam sempre frescos (Real-time).

def fetch_all_launch_data(): 
    """
    Busca a tabela completa de lançamentos.
    Ordenação: Competência (desc), Data Registro (desc).
    """
    query = """
        SELECT * FROM lancamentos 
        ORDER BY competencia DESC, data_atividade DESC, data_registro DESC
    """
    return conn.query(query, ttl=0)

def fetch_users_data(): 
    """Busca tabela de usuários para login e mapeamento."""
    return conn.query("SELECT * FROM usuarios ORDER BY email", ttl=0)

def fetch_projects_data(): 
    """Busca tabela de projetos ativos."""
    return conn.query("SELECT * FROM projetos ORDER BY nome", ttl=0)

def fetch_banking_data(): 
    """Busca dados bancários para a folha de pagamento."""
    return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# ==============================================================================
# 6. SISTEMA DE AUTENTICAÇÃO E GESTÃO DE SESSÃO
# ==============================================================================

# Carrega dados dos usuários no início
try:
    df_u_login = fetch_users_data()
except Exception as e:
    st.error("Erro ao carregar usuários. O banco de dados pode estar indisponível.")
    st.stop()

# --- MAPEAMENTO INTELIGENTE DE NOMES ---
# Cria um dicionário {email: Nome Real} para exibir nomes em vez de e-mails na UI.
email_to_name_map = {}

if not df_u_login.empty:
    for row in df_u_login.itertuples():
        # Verifica se a coluna 'nome' existe e tem conteúdo válido
        nome_db = getattr(row, 'nome', None)
        
        if nome_db and str(nome_db).strip() != "":
            email_to_name_map[row.email] = str(nome_db).strip()
        else:
            # Fallback: Formata o e-mail (pedro.reis@... -> Pedro Reis)
            clean_name = row.email.split('@')[0].replace('.', ' ').title()
            email_to_name_map[row.email] = clean_name

# --- DICIONÁRIO DE AUTENTICAÇÃO ---
auth_db = {}
if not df_u_login.empty:
    auth_db = {
        row.email: {
            "valor_hora": float(row.valor_hora) if row.valor_hora else 0.0, 
            "senha": str(row.senha), 
            "is_admin": bool(getattr(row, 'is_admin', False)),
            "nome_real": email_to_name_map.get(row.email)
        } for row in df_u_login.itertuples()
    }

# Lista de Super Admins (Backdoor de segurança)
SUPER_ADMINS_LIST = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- SIDEBAR: TELA DE LOGIN ---
st.sidebar.title("🛡️ OnCall Humana")
st.sidebar.caption("System v9.0 Citadel")
st.sidebar.markdown("---")

# Seletor de Usuário (Visual: Nome | Retorno: Email)
if auth_db:
    lista_emails_sistema = list(auth_db.keys())
    # Cria lista formatada para o selectbox
    opcoes_visuais_login = [f"{email_to_name_map.get(e, e)} ({e})" for e in lista_emails_sistema]
    # Mapa reverso para recuperar o email
    login_visual_map = dict(zip(opcoes_visuais_login, lista_emails_sistema))
    
    # Widget Selectbox
    user_selection_visual = st.sidebar.selectbox(
        "👤 Identifique-se:", 
        ["..."] + opcoes_visuais_login
    )
    
    # Bloqueio inicial
    if user_selection_visual == "...":
        st.info("👈 Por favor, selecione seu usuário no menu lateral para acessar o sistema.")
        st.image("https://img.freepik.com/free-vector/access-control-system-abstract-concept_335657-3180.jpg", use_container_width=True)
        st.stop()
        
    # Recupera credenciais
    current_user_email = login_visual_map[user_selection_visual]
    current_user_data = auth_db[current_user_email]
    current_user_name = current_user_data["nome_real"]
    
    # Widget Senha
    password_attempt = st.sidebar.text_input("🔑 Senha de Acesso:", type="password")
    
    # Validação
    if password_attempt != current_user_data["senha"]:
        st.sidebar.error("Senha incorreta.")
        st.stop()
        
    # Definição de Privilégios
    is_admin_session = current_user_data["is_admin"] or (current_user_email in SUPER_ADMINS_LIST)
    
    # Feedback de Login
    if is_admin_session:
        st.sidebar.success(f"Logado como ADMIN: {current_user_name}")
    else:
        st.sidebar.info(f"Bem-vindo(a), {current_user_name}")
        
else:
    st.error("Tabela de usuários vazia ou inacessível.")
    st.stop()

# ==============================================================================
# 7. MENU DE NAVEGAÇÃO E ESTADO DA SESSÃO
# ==============================================================================
st.sidebar.divider()
st.sidebar.subheader("📍 Navegação")

# Define as opções de menu baseadas no nível de acesso
if is_admin_session:
    app_menu_options = [
        "📝 Lançamentos", 
        "📊 Meu Painel / Gestão", 
        "🛡️ Admin Aprovações", 
        "💸 Pagamentos", 
        "📈 BI Estratégico", 
        "⚙️ Configurações"
    ]
else:
    app_menu_options = [
        "📝 Lançamentos", 
        "📊 Meu Painel"
    ]

# Widget de Navegação (Radio Button é mais estável que buttons)
selected_tab = st.sidebar.radio("Ir para:", app_menu_options)

# ==============================================================================
# 8. PREPARAÇÃO DE DADOS GLOBAL (GLOBAL DATA FETCHING)
# ==============================================================================
# Carrega dados essenciais para todas as abas
try:
    df_lancamentos = fetch_all_launch_data()
    df_projetos = fetch_projects_data()
    df_bancos = fetch_banking_data()
except Exception as e:
    st.error(f"Erro ao carregar dados globais: {e}")
    st.stop()

# Listas auxiliares
lista_projetos_ativos = df_projetos['nome'].tolist() if not df_projetos.empty else ["Sustentação", "Projetos", "Outros"]
colaboradores_unicos_email = sorted(df_lancamentos['colaborador_email'].unique()) if not df_lancamentos.empty else []

# Cria lista visual de colaboradores para filtros (Nome + Email)
lista_colaboradores_visual = [f"{email_to_name_map.get(e, e)} ({e})" for e in colaboradores_unicos_email]

# --- TRATAMENTO E ENRIQUECIMENTO DO DATAFRAME ---
if not df_lancamentos.empty:
    # 1. Coluna Visual de Nome (Crucial para UI)
    df_lancamentos['Nome'] = df_lancamentos['colaborador_email'].map(email_to_name_map).fillna(df_lancamentos['colaborador_email'])
    
    # 2. Tratamento de Data Real da Atividade (Coluna 'data_atividade')
    # Se a coluna existir, converte. Se não, cria vazia.
    if 'data_atividade' in df_lancamentos.columns:
        df_lancamentos['Data Real'] = pd.to_datetime(df_lancamentos['data_atividade'], errors='coerce').dt.date
    else:
        df_lancamentos['Data Real'] = pd.NaT

    # 3. Tratamento de Data de Registro (Log do Sistema)
    df_lancamentos['Importado Em'] = pd.to_datetime(df_lancamentos['data_registro']).dt.date
    
    # 4. Fallback de Data: Se 'Data Real' estiver nula, preenche com a data de importação
    df_lancamentos['Data Real'] = df_lancamentos['Data Real'].fillna(df_lancamentos['Importado Em'])
    
    # 5. Garantia de Competência como String
    df_lancamentos['competencia'] = df_lancamentos['competencia'].astype(str)

# ==============================================================================
# ABA 1: LANÇAMENTOS (USER INTERFACE)
# ==============================================================================
if selected_tab == "📝 Lançamentos":
    st.subheader(f"📝 Novo Lançamento de Horas - {user_name_display}")
    
    # Instruções Claras
    with st.expander("ℹ️ Guia de Preenchimento (Clique para expandir)", expanded=False):
        st.markdown("""
        ### Regras de Ouro:
        1. **Data Real:** Selecione o dia exato em que a tarefa foi executada.
        2. **Horas (HH.MM):** Utilize ponto para separar horas de minutos.
           * Exemplo: `1.30` representa **1 hora e 30 minutos**.
           * Exemplo: `0.45` representa **45 minutos**.
        3. **Descrição:** Seja específico. "Reunião" é ruim. "Reunião de Alinhamento Projeto X" é bom.
        """)
    
    # Formulário de Lançamento
    with st.form("form_lancamento_main", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        
        input_projeto = c1.selectbox("Projeto Vinculado", lista_projetos_ativos)
        input_tipo = c2.selectbox("Tipo de Atividade", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design", "Apoio", "Outros"])
        
        # CAMPO VITAL: DATA DA ATIVIDADE
        input_data = c3.date_input("Data REAL da Atividade", datetime.now())
        
        c4, c5 = st.columns([1, 2])
        # Input numérico para horas
        input_horas = c4.number_input("Horas Trabalhadas (HH.MM)", min_value=0.0, step=0.10, format="%.2f", help="Use 1.30 para 1h30min")
        input_desc = c5.text_input("Descrição Detalhada da Entrega")
        
        btn_gravar = st.form_submit_button("🚀 Gravar Lançamento", type="primary")
        
        if btn_gravar:
            # Validação Front-end
            if input_horas <= 0:
                st.warning("⚠️ A quantidade de horas deve ser maior que zero.")
            elif not input_desc:
                st.warning("⚠️ A descrição é obrigatória para auditoria.")
            else:
                try:
                    # Preparação dos dados
                    competencia_str = input_data.strftime("%Y-%m")
                    data_full_str = input_data.strftime("%Y-%m-%d")
                    valor_hora_atual = dict_users[current_user_email]["valor"]
                    
                    # Execução no Banco
                    with conn.session as s:
                        s.execute(
                            text("""
                                INSERT INTO lancamentos 
                                (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico) 
                                VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v)
                            """),
                            {
                                "id": str(uuid.uuid4()), 
                                "e": current_user_email, 
                                "p": input_projeto, 
                                "h": input_horas, 
                                "c": competencia_str,   # Campo para Filtros Macro
                                "d_atv": data_full_str, # Campo para Data Real
                                "t": input_tipo, 
                                "d": input_desc, 
                                "v": valor_hora_atual
                            }
                        )
                        s.commit()
                    
                    # Feedback de Sucesso
                    st.toast(f"✅ Lançamento salvo: {input_horas}h em {data_full_str}", icon="✅")
                    st.success("Registro gravado com sucesso! Aguarde a atualização...")
                    time.sleep(1.5)
                    st.rerun()
                    
                except Exception as e:
                    st.error("Erro ao salvar no banco de dados.")
                    st.error(f"Detalhe técnico: {e}")

# ==============================================================================
# ABA 2: MEU PAINEL / GESTÃO (VIEWER)
# ==============================================================================
elif "Meu Painel" in selected_tab:
    st.subheader("📊 Painel de Controle e Auditoria")
    
    # --- 1. SELETOR DE USUÁRIO ALVO (VISÃO ADMIN) ---
    target_email = current_user_email
    target_name_curr = user_name_display
    
    if is_admin_session:
        col_sel_admin, col_spacer = st.columns([2, 2])
        
        # Filtra a lista para não mostrar o próprio admin duplicado se ele já estiver na lista
        lista_outros = [x for x in lista_colaboradores_visual if current_user_email not in x]
        # Adiciona o próprio admin no topo
        lista_adm_completa = [f"{user_name_display} ({current_user_email})"] + lista_outros
        
        sel_admin_val = col_sel_admin.selectbox(
            "👁️ (Admin) Visualizar Painel de:", 
            lista_adm_completa,
            help="Selecione um colaborador para auditar as horas e valores."
        )
        
        # Extrai email do string selecionado (Formato: Nome (email))
        target_email = sel_admin_val.split('(')[-1].replace(')', '')
        target_name_curr = email_to_name_map.get(target_email, target_email)
    
    st.markdown(f"**Visualizando dados de:** `{target_name_curr}`")
    
    # --- 2. FILTRO POR COMPETÊNCIA (MULTI-SELECT) ---
    st.write("---")
    
    # Pega todas as competências únicas do banco para montar o filtro
    if not df_lancamentos.empty:
        all_competencias = sorted(df_lancamentos['competencia'].unique(), reverse=True)
    else:
        all_competencias = []
        
    c_f1, c_f2 = st.columns([1, 3])
    
    # Default: Seleciona a competência mais recente
    default_comp = all_competencias[:1] if all_competencias else None
    
    comp_selecionadas = c_f1.multiselect(
        "📅 Filtrar Competência(s):", 
        all_competencias, 
        default=default_comp,
        help="Selecione um ou mais meses (YYYY-MM) para visualizar."
    )
    
    # --- 3. FILTRAGEM DO DATAFRAME ---
    # Passo 1: Filtra pelo usuário alvo
    df_painel = df_lancamentos[df_lancamentos["colaborador_email"] == target_email].copy()
    
    # Passo 2: Filtra pela competência selecionada
    if not df_painel.empty and comp_selecionadas:
        df_painel = df_painel[df_painel['competencia'].isin(comp_selecionadas)]
    
    if not df_painel.empty and comp_selecionadas:
        # --- 4. CÁLCULOS FINANCEIROS (REAL-TIME) ---
        # Converte HH.MM -> Decimal
        df_painel['h_dec'] = df_painel['horas'].apply(convert_hhmm_to_decimal)
        # Calcula Valor = Horas Decimais * Valor Hora Historico
        df_painel['valor_total'] = df_painel['h_dec'] * df_painel['valor_hora_historico']
        
        # --- 5. SCORECARDS (KPIs) ---
        st.markdown("### Resumo Financeiro do Período")
        k1, k2, k3, k4 = st.columns(4)
        
        # Agregação por Status
        h_pend = df_painel[df_painel['status_aprovaca'] == 'Pendente']['horas'].sum()
        h_aprov = df_painel[df_painel['status_aprovaca'] == 'Aprovado']['horas'].sum()
        h_pago = df_painel[df_painel['status_pagamento'] == 'Pago']['horas'].sum()
        val_total_periodo = df_painel['valor_total'].sum()
        
        k1.metric("Pendente (HH.MM)", f"{h_pend:.2f}", delta="Aguardando", delta_color="off")
        k2.metric("Aprovado (HH.MM)", f"{h_aprov:.2f}", delta="Validado", delta_color="normal")
        k3.metric("Pago (HH.MM)", f"{h_pago:.2f}", delta="Liquidado", delta_color="normal")
        k4.metric("Valor Total Estimado", f"R$ {val_total_periodo:,.2f}")
        
        st.divider()
        st.markdown(f"### 📋 Extrato Detalhado ({len(df_painel)} registros)")
        
        # Seleção de Colunas para Exibição Limpa
        df_view = df_painel[[
            'descricao', 'Data Real', 'projeto', 'horas', 'valor_total', 
            'status_aprovaca', 'status_pagamento', 'competencia'
        ]].sort_values(by='Data Real', ascending=False)
        
        st.dataframe(
            df_view, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "valor_total": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                "horas": st.column_config.NumberColumn("Horas (HH.MM)", format="%.2f"),
                "Data Real": st.column_config.DateColumn("Data Atividade", format="DD/MM/YYYY"),
                "status_aprovaca": st.column_config.TextColumn("Status Aprovação"),
                "status_pagamento": st.column_config.TextColumn("Pagamento"),
                "descricao": st.column_config.TextColumn("Descrição", width="large"),
                "projeto": st.column_config.TextColumn("Projeto"),
                "competencia": st.column_config.TextColumn("Comp.")
            }
        )
    else:
        if not comp_selecionadas:
            st.warning("👆 Selecione pelo menos uma competência (Mês/Ano) acima para ver os dados.")
        else:
            st.info("Nenhum registro encontrado para as competências selecionadas.")

# ==============================================================================
# ABA 3: ADMIN APROVAÇÕES (GESTAO OPERACIONAL)
# ==============================================================================
elif selected_tab == "🛡️ Admin Aprovações":
    st.subheader("🛡️ Central de Gestão Operacional")
    
    # --- BLOCO A: IMPORTAÇÃO EM MASSA ---
    with st.expander("📥 Importação em Massa (Copiar e Colar do Excel)", expanded=False):
        st.info("O sistema identificará a data correta (DD/MM/AAAA) e criará a competência.")
        st.markdown("""
        **Formato Obrigatório (Separado por TAB - Padrão Excel):**
        `Data` | `Projeto` | `Email` | `Horas` | `Tipo` | `Descrição`
        """)
        
        cola_texto = st.text_area("Área de Transferência:", height=150, placeholder="Cole aqui...")
        
        if cola_texto and st.button("🚀 Processar Importação em Massa", type="primary"):
            try:
                # Leitura flexível
                df_import = pd.read_csv(io.StringIO(cola_texto), sep='\t', names=["data", "p", "e", "h", "t", "d"])
                
                with conn.session as s:
                    for row in df_import.itertuples():
                        # Busca valor hora do usuário
                        v_h = dict_users.get(row.e, {}).get("valor", 0)
                        
                        # TRATAMENTO DATA DUPLO (DD/MM/AAAA -> YYYY-MM-DD)
                        try:
                            dt_obj = pd.to_datetime(row.data, dayfirst=True)
                            comp_str = dt_obj.strftime("%Y-%m")
                            data_full = dt_obj.strftime("%Y-%m-%d")
                        except:
                            # Fallback
                            now = datetime.now()
                            comp_str = now.strftime("%Y-%m")
                            data_full = now.strftime("%Y-%m-%d")

                        s.execute(
                            text("""
                                INSERT INTO lancamentos 
                                (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico) 
                                VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v)
                            """),
                            {
                                "id": str(uuid.uuid4()), "e": row.e, "p": row.p, "h": row.h, 
                                "c": comp_str, "d_atv": data_full, 
                                "t": row.t, "d": row.d, "v": v_h
                            }
                        )
                    s.commit()
                st.toast(f"✅ {len(df_import)} registros importados!", icon="🚀")
                time.sleep(1.5); st.rerun()
            except Exception as e: 
                st.error("Erro na leitura. Verifique as colunas."); st.code(str(e))

    st.divider()

    # --- BLOCO B: FILA DE PENDENTES ---
    st.markdown("### 🕒 Fila de Pendentes")
    
    # Filtros e Ações
    c_control_1, c_control_2 = st.columns([1, 3])
    select_all_pend = c_control_1.checkbox("Selecionar Todos")
    
    lista_filtro_pendentes = ["Todos"] + lista_colaboradores_visual
    filter_colab_pend = c_control_2.selectbox("Filtrar por Colaborador:", lista_filtro_pendentes, key="fp_admin")
    
    # Query Base
    df_p = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Pendente'].copy()
    
    # Aplica filtro de usuário
    if filter_colab_pend != "Todos":
        email_sel_pend = filter_colab_pend.split('(')[-1].replace(')', '')
        df_p = df_p[df_p['colaborador_email'] == email_sel_pend]
    
    if not df_p.empty:
        # Prepara colunas
        df_p = df_p[['descricao', 'Nome', 'projeto', 'Data Real', 'horas', 'tipo', 'id']]
        # Colunas de controle
        df_p.insert(0, "✅", select_all_pend)
        df_p.insert(1, "🗑️", False)
        
        # Editor de Dados
        edited_pend = st.data_editor(
            df_p, 
            use_container_width=True, 
            hide_index=True, 
            key="editor_pendentes_main",
            column_config={
                "✅": st.column_config.CheckboxColumn("Aprovar", width="small"),
                "🗑️": st.column_config.CheckboxColumn("Rejeitar", width="small"),
                "Data Real": st.column_config.DateColumn("Data Ativ.", format="DD/MM/YYYY"),
                "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                "Nome": st.column_config.TextColumn("Colaborador", width="medium"),
                "descricao": st.column_config.TextColumn("Descrição", width="large")
            }
        )
        
        # Botões de Ação em Massa
        c_btn_a, c_btn_b = st.columns(2)
        
        if c_btn_a.button("✔️ APROVAR SELECIONADOS", type="primary", use_container_width=True):
            ids_to_approve = edited_pend[edited_pend["✅"] == True]["id"].tolist()
            if ids_to_approve:
                with conn.session as s:
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Aprovado' WHERE id IN :ids"), {"ids": tuple(ids_to_approve)})
                    s.commit()
                st.toast(f"✅ {len(ids_to_approve)} itens aprovados!", icon="🎉")
                time.sleep(1); st.rerun()
                
        if c_btn_b.button("🔥 REJEITAR SELECIONADOS", use_container_width=True):
            ids_to_reject = edited_pend[edited_pend["🗑️"] == True]["id"].tolist()
            if ids_to_reject:
                with conn.session as s:
                    # Move para 'Negado'
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Negado' WHERE id IN :ids"), {"ids": tuple(ids_to_reject)})
                    s.commit()
                st.toast(f"🚫 {len(ids_to_reject)} itens rejeitados.", icon="🗑️")
                time.sleep(1); st.rerun()
    else:
        st.info("Nenhuma pendência encontrada.")

    st.divider()

    # --- BLOCO C: HISTÓRICO DE APROVADOS (EDIÇÃO) ---
    st.markdown("### ✅ Histórico de Aprovados")
    
    filter_colab_aprov = st.selectbox("Filtrar Aprovados:", lista_filtro_pendentes, key="fa_admin")
    
    df_a = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Aprovado'].copy()
    if filter_colab_aprov != "Todos":
        email_sel_aprov = filter_colab_aprov.split('(')[-1].replace(')', '')
        df_a = df_a[df_a['colaborador_email'] == email_sel_aprov]
    
    if not df_a.empty:
        # Exibe colunas editáveis importantes
        df_a = df_a[['descricao', 'Nome', 'projeto', 'Data Real', 'horas', 'status_aprovaca', 'id', 'competencia']]
        
        edited_aprov = st.data_editor(
            df_a, 
            use_container_width=True, 
            hide_index=True, 
            key="editor_aprovados_main",
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
                "Data Real": st.column_config.DateColumn("Data Ativ.", format="DD/MM/YYYY"),
                "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                "Nome": st.column_config.TextColumn("Colaborador", disabled=True),
                "competencia": st.column_config.TextColumn("Comp.", disabled=True)
            }
        )
        
        if st.button("💾 Salvar Alterações em Aprovados"):
            with conn.session as s:
                for row in edited_aprov.itertuples():
                    # Lógica de atualização inteligente de data/competência
                    try:
                        # Pega a data editada (pode vir como string ou date)
                        d_val = getattr(row, "Data_Real") # Pandas renomeia espaços para _
                        
                        # Converte para objeto date se necessário
                        if isinstance(d_val, str):
                            d_val = datetime.strptime(d_val, "%Y-%m-%d").date()
                        elif isinstance(d_val, pd.Timestamp):
                            d_val = d_val.date()
                            
                        # Recalcula strings
                        new_comp = d_val.strftime("%Y-%m")
                        new_date_str = d_val.strftime("%Y-%m-%d")
                        
                        s.execute(
                            text("UPDATE lancamentos SET status_aprovaca=:s, horas=:h, descricao=:d, projeto=:p, competencia=:c, data_atividade=:da WHERE id=:id"),
                            {
                                "s": row.status_aprovaca, "h": row.horas, "d": row.descricao, "p": row.projeto,
                                "c": new_comp, "da": new_date_str, "id": row.id
                            }
                        )
                    except Exception as e:
                        st.error(f"Erro ao atualizar linha {row.id}: {e}")
                s.commit()
            st.toast("✅ Alterações salvas com sucesso!", icon="💾")
            time.sleep(1); st.rerun()
    else:
        st.info("Nenhum item aprovado para este filtro.")

    # --- BLOCO D: REJEITADOS ---
    st.divider()
    with st.expander("❌ Visualizar Lixeira / Rejeitados"):
        df_n = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Negado'].copy()
        if not df_n.empty:
            df_n = df_n[['descricao', 'Nome', 'Data Real', 'status_aprovaca', 'id']]
            
            edited_neg = st.data_editor(
                df_n, 
                use_container_width=True, 
                hide_index=True, 
                column_config={"status_aprovaca": st.column_config.SelectboxColumn("Ação", options=["Negado", "Pendente", "Aprovado"])}
            )
            
            c_rec, c_del = st.columns(2)
            if c_rec.button("💾 Recuperar/Salvar Rejeitados"):
                with conn.session as s:
                    for row in edited_neg.itertuples():
                        if row.status_aprovaca != "Negado":
                            s.execute(text("UPDATE lancamentos SET status_aprovaca = :s WHERE id = :id"), {"s": row.status_aprovaca, "id": row.id})
                    s.commit()
                st.success("Recuperado!"); st.rerun()
                
            if c_del.button("🔥 EXCLUIR DEFINITIVAMENTE", type="primary"):
                with conn.session as s:
                    ids_del = tuple(edited_neg[edited_neg['status_aprovaca'] == 'Negado']['id'].tolist())
                    if ids_del:
                        s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": ids_del})
                        s.commit()
                st.warning("Excluído permanentemente."); st.rerun()
        else:
            st.info("Lixeira vazia.")

# ==============================================================================
# ABA 4: PAGAMENTOS (DRILL-DOWN FINANCEIRO)
# ==============================================================================
elif selected_tab == "💸 Pagamentos":
    st.subheader("💸 Consolidação Financeira")
    
    df_pay = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Aprovado'].copy()
    
    if not df_pay.empty:
        # Conversão Financeira
        df_pay['h_dec'] = df_pay['horas'].apply(convert_hhmm_to_decimal)
        df_pay['r$'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
        
        # Agrupa por Competência (YYYY-MM) e Colaborador
        df_grouped = df_pay.groupby(['competencia', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        
        # Totalizador Geral
        total_open_value = df_pay[df_pay['status_pagamento'] != 'Pago']['r$'].sum()
        st.metric("💰 Total Pendente Geral (Todos)", f"R$ {total_open_value:,.2f}")
        
        # Ordena grupos pela competência mais recente
        df_grouped = df_grouped.sort_values(['competencia', 'colaborador_email'], ascending=[False, True])
        
        # Iteração para Drill-down
        for idx, row in df_grouped.iterrows():
            nome_colab_pay = email_to_name_map.get(row['colaborador_email'], row['colaborador_email'])
            
            with st.expander(f"📅 {row['competencia']} | 👤 {nome_colab_pay} | Total: R$ {row['r$']:,.2f}"):
                
                # Detalhes do Grupo
                detalhes = df_pay[(df_pay['competencia'] == row['competencia']) & (df_pay['colaborador_email'] == row['colaborador_email'])]
                
                st.dataframe(
                    detalhes[['descricao', 'Data Real', 'horas', 'r$']], 
                    use_container_width=True, hide_index=True, 
                    column_config={
                        "r$": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                        "Data Real": st.column_config.DateColumn("Data"),
                        "horas": st.column_config.NumberColumn("HH.MM", format="%.2f")
                    }
                )
                
                # Controle de Status do Grupo
                status_atual_grupo = detalhes['status_pagamento'].iloc[0] if 'status_pagamento' in detalhes.columns else "Em aberto"
                opcoes_pagamento = ["Em aberto", "Pago", "Parcial"]
                idx_op = opcoes_pagamento.index(status_atual_grupo) if status_atual_grupo in opcoes_pagamento else 0
                
                c_sel_pay, c_btn_pay = st.columns([3, 1])
                new_status_pay = c_sel_pay.selectbox("Status do Grupo", opcoes_pagamento, index=idx_op, key=f"pay_sel_{idx}")
                
                if c_btn_pay.button("Atualizar Status", key=f"btn_upd_{idx}"):
                    with conn.session as s:
                        ids_update = tuple(detalhes['id'].tolist())
                        s.execute(text("UPDATE lancamentos SET status_pagamento=:s WHERE id IN :ids"), {"s": new_status_pay, "ids": ids_update})
                        s.commit()
                    st.toast("Status atualizado com sucesso!"); time.sleep(0.5); st.rerun()
    else:
        st.info("Nenhum lançamento aprovado disponível para pagamento.")

# ==============================================================================
# ABA 5: BI ESTRATÉGICO
# ==============================================================================
elif selected_tab == "📈 BI Estratégico":
    st.subheader("📈 Inteligência de Negócios")
    
    # Filtro Competência
    if not df_lancamentos.empty:
        all_comps_bi = sorted(df_lancamentos['competencia'].astype(str).unique(), reverse=True)
    else:
        all_comps_bi = []
        
    c1, c2 = st.columns([3, 1])
    sel_bi_comps = c1.multiselect("Filtrar Competências:", all_comps_bi, default=all_comps_bi[:2] if all_comps_bi else None)
    
    df_bi = df_lancamentos.copy()
    
    if sel_bi_comps and not df_bi.empty:
        # Filtra
        df_bi = df_bi[df_bi['competencia'].isin(sel_bi_comps)]
        
        # Processamento
        df_bi['tipo_norm'] = df_bi['tipo'].apply(normalize_text_for_bi)
        df_bi['h_dec'] = df_bi['horas'].apply(convert_hhmm_to_decimal)
        df_bi["custo"] = df_bi['h_dec'] * df_bi["valor_hora_historico"]
        
        # KPIs
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Horas Totais", f"{df_bi['horas'].sum():.2f}")
        m2.metric("Custo Total", f"R$ {df_bi['custo'].sum():,.2f}")
        m3.metric("Pago", f"R$ {df_bi[df_bi['status_pagamento']=='Pago']['custo'].sum():,.2f}")
        m4.metric("Registros", len(df_bi))
        
        st.divider()
        
        # Gráficos
        col_g1, col_g2 = st.columns(2)
        with col_g1: 
            st.write("**💰 Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        with col_g2: 
            st.write("**⏱️ Horas por Tipo de Atividade**")
            st.bar_chart(df_bi.groupby("tipo_norm")["horas"].sum())
        
        st.write("**🏆 Ranking de Colaboradores (Por Nome)**")
        # Agrupa pelo Nome Visual
        rank = df_bi.groupby("Nome").agg({'horas': 'sum', 'custo': 'sum'}).sort_values('horas', ascending=False)
        st.dataframe(rank, use_container_width=True, column_config={"custo": st.column_config.NumberColumn("Custo Total (R$)", format="R$ %.2f")})
    else:
        st.info("Selecione uma competência para visualizar os gráficos.")

# ==============================================================================
# ABA 6: CONFIGURAÇÕES (ADMINISTRAÇÃO DO SISTEMA)
# ==============================================================================
elif selected_tab == "⚙️ Configurações":
    st.subheader("⚙️ Configurações do Sistema")
    
    # 1. Usuários
    st.write("👥 **Gestão de Usuários e Nomes**")
    st.caption("Atenção: O campo 'Nome de Exibição' é o que aparece nos relatórios.")
    
    ed_users = st.data_editor(
        df_u_login, 
        num_rows="dynamic", 
        hide_index=True, 
        key="editor_users_cfg",
        column_config={
            "email": st.column_config.TextColumn("Login (Email)", disabled=True),
            "nome": st.column_config.TextColumn("Nome de Exibição"),
            "senha": st.column_config.TextColumn("Senha"),
            "is_admin": st.column_config.CheckboxColumn("Admin"),
            "valor_hora": st.column_config.NumberColumn("Valor Hora (R$)", format="%.2f")
        }
    )
    if st.button("Salvar Usuários"):
        with conn.session as s:
            for row in ed_users.itertuples():
                # Garante que nome não seja vazio
                nm_final = getattr(row, 'nome', row.email.split('@')[0])
                if pd.isna(nm_final) or str(nm_final).strip() == "":
                    nm_final = row.email.split('@')[0]
                
                # Upsert
                s.execute(
                    text("""
                        INSERT INTO usuarios (email, valor_hora, senha, is_admin, nome) 
                        VALUES (:e, :v, :s, :a, :n) 
                        ON CONFLICT (email) 
                        DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a, nome=:n
                    """), 
                    {"e": row.email, "v": row.valor_hora, "s": str(row.senha), "a": bool(row.is_admin), "n": nm_final}
                )
            s.commit()
        st.toast("Usuários atualizados!", icon="✅"); time.sleep(1); st.rerun()
        
    st.divider()
    
    # 2. Projetos
    st.write("📁 **Gestão de Projetos**")
    ed_projs = st.data_editor(df_projs, num_rows="dynamic", hide_index=True, key="editor_projs_cfg")
    if st.button("Salvar Projetos"):
        with conn.session as s:
            for row in ed_projs.itertuples():
                if row.nome: 
                    s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": row.nome})
            s.commit()
        st.toast("Projetos salvos!", icon="✅"); time.sleep(1); st.rerun()

    st.divider()
    
    # 3. Bancos
    st.write("🏦 **Dados Bancários**")
    ed_bancos = st.data_editor(
        df_banc, 
        num_rows="dynamic", 
        hide_index=True, 
        key="editor_banks_cfg",
        column_config={
            "tipo_chave": st.column_config.SelectboxColumn("Tipo Chave", options=["CPF", "CNPJ", "Email", "Aleatoria", "Agencia/Conta"])
        }
    )
    if st.button("Salvar Bancos"):
        with conn.session as s:
            for row in ed_bancos.itertuples():
                t_k = getattr(row, 'tipo_chave', 'CPF')
                s.execute(
                    text("""
                        INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) 
                        VALUES (:e, :b, :t, :c) 
                        ON CONFLICT (colaborador_email) 
                        DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c
                    """), 
                    {"e": row.colaborador_email, "b": row.banco, "t": t_k, "c": row.chave_pix}
                )
            s.commit()
        st.toast("Dados bancários salvos!", icon="✅"); st.rerun()

# ==============================================================================
# RODAPÉ
# ==============================================================================
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: gray; font-size: 12px;'>"
    "OnCall Humana - Developed by Pedro Reis | v9.0 Citadel Edition | "
    f"Status: Online | {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    "</p>", 
    unsafe_allow_html=True
)