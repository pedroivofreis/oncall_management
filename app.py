"""
====================================================================================================
ONCALL HUMANA ERP - SYSTEM MASTER v12.4 "INFINITY STABLE"
====================================================================================================
Desenvolvido por: Pedro Reis
Data: Fevereiro/2026
Versão: 12.4 Enterprise Edition (Procedural Architecture)

DESCRIÇÃO TÉCNICA DO SISTEMA:
-----------------------------
Este é um sistema de ERP (Enterprise Resource Planning) focado na gestão de timesheets (horas),
aprovações gerenciais, fluxo financeiro, inteligência de dados (BI) e gestão de Notas Fiscais.

A arquitetura segue o padrão PROCEDURAL (Functional-Based) para garantir estabilidade de execução
no ambiente do Streamlit, evitando problemas de estado de sessão comuns em abordagens OOP puras.

MÓDULOS DO SISTEMA:
1. CONFIGURAÇÃO: Definições de página, CSS e constantes.
2. DATABASE: Gerenciamento de conexão PostgreSQL com tratamento de reconexão.
3. UTILS: Funções de conversão matemática (HH.MM -> Decimal) e normalização de texto.
4. AUTH: Sistema de login, mapeamento de nomes (Email -> Nome Real) e controle de permissões.
5. VIEW - LANÇAMENTOS: Formulário de input para colaboradores.
6. VIEW - HISTÓRICO: Interface para o colaborador ver e editar seus itens pendentes.
7. VIEW - PAINEL: Dashboards financeiros com filtros de competência (Mês/Ano).
8. VIEW - ADMIN: Central de aprovação, edição em massa, importação XLSX e exclusão de itens.
   **FEATURE CRÍTICA:** Sincronia automática entre Data Real e Competência Financeira.
9. VIEW - NOTAS FISCAIS: Upload de PDFs, aprovação e controle de status.
10. VIEW - FINANCEIRO: Consolidação de pagamentos e drill-down por colaborador.
11. VIEW - BI: Gráficos executivos.
12. VIEW - CONFIG: CRUD de tabelas auxiliares (Usuários, Projetos, Bancos).

TABELAS DO BANCO DE DADOS (SCHEMA):
- usuarios: email (PK), senha, valor_hora, is_admin, nome
- projetos: nome (PK)
- dados_bancarios: colaborador_email (PK), banco, tipo_chave, chave_pix
- lancamentos: id (PK), colaborador_email, projeto, horas, competencia, data_atividade,
               tipo, descricao, data_registro, valor_hora_historico, status_aprovaca,
               status_pagamento, foi_editado
- invoices: id (PK), collaborator_email, competence, amount, file_name, file_pdf, status
====================================================================================================
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import uuid
import time
import io
from sqlalchemy import text

# ==============================================================================
# 1. CONFIGURAÇÃO INICIAL DA PÁGINA E META-DADOS
# ==============================================================================
st.set_page_config(
    page_title="OnCall Humana - Master v12.5",
    layout="wide",
    page_icon="♾️",  # <--- Ícone atualizado aqui
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.oncall.com.br/help',
        'Report a bug': "mailto:suporte@oncall.com.br",
        'About': """
        # OnCall Humana ERP v12.5
        Sistema oficial de gestão de horas e pagamentos.
        Desenvolvido com Python/Streamlit e PostgreSQL.
        """
    }
)

# ==============================================================================
# 2. ESTILIZAÇÃO CSS AVANÇADA (ENTERPRISE UI/UX)
# ==============================================================================
st.markdown("""
<style>
    /* Ajuste do container principal para maximizar a área útil */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 5rem;
        max-width: 98% !important;
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

    /* Labels de formulários mais legíveis e fortes */
    label {
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        color: inherit;
        letter-spacing: 0.02em;
    }

    /* Cabeçalhos de Expander mais destacados (Azul Corporativo) */
    .streamlit-expanderHeader {
        font-weight: 700;
        font-size: 1.05rem;
        color: #0f54c9;
        background-color: rgba(128, 128, 128, 0.05);
        border-radius: 5px;
        padding: 10px;
    }

    /* Tabelas (Dataframes) com bordas definidas */
    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 5px;
        padding: 2px;
    }

    /* Botões Primários (Gradiente Azul) */
    button[kind="primary"] {
        font-weight: bold;
        border: 1px solid rgba(255, 75, 75, 0.5);
        background: linear-gradient(90deg, #0f54c9 0%, #0a3a8b 100%);
        color: white;
    }
    
    /* Alerta de Edição (Texto Vermelho) */
    .edited-alert {
        color: #ff4b4b;
        font-weight: bold;
        font-size: 0.8rem;
    }
    
    /* Toast Notifications */
    div[data-testid="stToast"] {
        padding: 1rem;
        border-radius: 8px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 3. GERENCIAMENTO DE CONEXÃO COM O BANCO DE DADOS (DAL)
# ==============================================================================
def get_connection():
    """
    Estabelece uma conexão segura e persistente com o banco de dados Neon (PostgreSQL).
    """
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0) 
        return c
    except Exception as e:
        st.error("🔴 Erro Crítico de Conexão com o Banco de Dados.")
        st.error(f"Detalhe técnico: {e}")
        st.info("Verifique sua conexão com a internet ou as credenciais no arquivo .streamlit/secrets.toml")
        st.stop()

# Instância global da conexão para ser reutilizada
conn = get_connection()

# ==============================================================================
# 4. BIBLIOTECA DE FUNÇÕES UTILITÁRIAS (HELPER FUNCTIONS)
# ==============================================================================
def convert_hhmm_to_decimal(pseudo_hour):
    """
    Converte o formato visual de horas HH.MM (Ex: 2.30) para formato Decimal (2.50).
    """
    try:
        if pd.isna(pseudo_hour) or pseudo_hour == "":
            return 0.0
        
        val_str = f"{float(pseudo_hour):.2f}"
        parts = val_str.split('.')
        
        if len(parts) != 2:
            return float(pseudo_hour)
            
        horas_inteiras = int(parts[0])
        minutos = int(parts[1])
        
        if minutos >= 60:
            return float(pseudo_hour)
            
        return horas_inteiras + (minutos / 60.0)
    except Exception:
        return 0.0

def normalize_text_fields(text_val):
    """
    Padroniza strings para garantir consistência no Banco de Dados e nos Gráficos de BI.
    """
    if not isinstance(text_val, str):
        return "Outros"
        
    t = text_val.strip().lower()
    
    if "back" in t and "end" in t: return "Back-end"
    if "front" in t and "end" in t: return "Front-end"
    if "dados" in t or "data" in t: return "Eng. Dados"
    if "infra" in t or "devops" in t: return "Infraestrutura"
    if "qa" in t or "test" in t: return "QA / Testes"
    if "banco" in t: return "Banco de Dados"
    if "reuni" in t or "meeting" in t: return "Reunião"
    if "gest" in t or "agile" in t: return "Gestão"
    if "design" in t or "ux" in t: return "Design/UX"
    if "api" in t: return "Integrações/API"
    
    return text_val.capitalize()

def calculate_competence(date_obj):
    """
    Gera a string de competência (YYYY-MM) a partir de um objeto de data.
    """
    if not date_obj:
        return datetime.now().strftime("%Y-%m")
    
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.strptime(date_obj, "%Y-%m-%d")
        except:
            return datetime.now().strftime("%Y-%m")
            
    return date_obj.strftime("%Y-%m")

# ==============================================================================
# 5. DATA ACCESS LAYER (DAL) - FUNÇÕES DE LEITURA
# ==============================================================================
def fetch_all_launch_data(): 
    try:
        query = "SELECT * FROM lancamentos ORDER BY competencia DESC, data_atividade DESC, data_registro DESC"
        return conn.query(query, ttl=0)
    except Exception as e:
        st.error(f"Erro ao buscar lançamentos: {e}")
        return pd.DataFrame()

def fetch_users_data(): 
    try:
        return conn.query("SELECT * FROM usuarios ORDER BY email", ttl=0)
    except Exception as e:
        st.error(f"Erro ao buscar usuários: {e}")
        return pd.DataFrame()

def fetch_projects_data(): 
    try:
        return conn.query("SELECT * FROM projetos ORDER BY nome", ttl=0)
    except:
        return pd.DataFrame(columns=["nome"])

def fetch_banking_data(): 
    try:
        return conn.query("SELECT * FROM dados_bancarios", ttl=0)
    except:
        return pd.DataFrame()

def fetch_invoices_data():
    try:
        query = "SELECT id, collaborator_email, competence, amount, file_name, status FROM invoices ORDER BY competence DESC"
        return conn.query(query, ttl=0)
    except:
        return pd.DataFrame()

# ==============================================================================
# 6. SISTEMA DE AUTENTICAÇÃO E GESTÃO DE SESSÃO
# ==============================================================================
try:
    df_u_login = fetch_users_data()
except Exception as e:
    st.error("Erro fatal: Não foi possível carregar a tabela de usuários.")
    st.stop()

# --- MAPEAMENTO INTELIGENTE DE NOMES ---
email_to_name_map = {}

if not df_u_login.empty:
    for row in df_u_login.itertuples():
        nome_db = getattr(row, 'nome', None)
        
        if nome_db and str(nome_db).strip() != "":
            email_to_name_map[row.email] = str(nome_db).strip()
        else:
            clean_name = row.email.split('@')[0].replace('.', ' ').title()
            email_to_name_map[row.email] = clean_name

# --- DICIONÁRIO DE AUTENTICAÇÃO E PERMISSÕES ---
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

SUPER_ADMINS_LIST = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- SIDEBAR: TELA DE LOGIN ---
st.sidebar.title("♾️ OnCall Humana") # <--- Ícone atualizado aqui
st.sidebar.caption("v12.5 Infinity Stable")
st.sidebar.markdown("---")

if not auth_db:
    st.error("Tabela de usuários vazia. Contate o suporte.")
    st.stop()

lista_emails_sistema = list(auth_db.keys())
opcoes_visuais_login = [f"{email_to_name_map.get(e, e)} ({e})" for e in lista_emails_sistema]
login_visual_map = dict(zip(opcoes_visuais_login, lista_emails_sistema))

user_selection_visual = st.sidebar.selectbox(
    "👤 Identifique-se:", 
    ["..."] + opcoes_visuais_login,
    help="Selecione seu nome na lista para iniciar o acesso."
)

if user_selection_visual == "...":
    # --- TELA DE BOAS VINDAS (SUBSTITUI A IMAGEM FEIA) ---
    st.markdown("""
    <div style="padding: 2rem; border-radius: 10px; background-color: rgba(128, 128, 128, 0.05); border: 1px solid rgba(128, 128, 128, 0.2);">
        <h1 style="color: #0f54c9; margin-bottom: 0;">♾️ OnCall Humana</h1>
        <h4 style="color: gray; margin-top: 0;">Enterprise Resource Planning</h4>
        <hr style="opacity: 0.2;">
        <h3>🔐 Acesso Autenticado</h3>
        <p>Por favor, <b>selecione seu nome</b> no menu lateral esquerdo e insira sua senha para acessar o seu painel.</p>
        <br>
        <h4>📌 Diretrizes do Sistema:</h4>
        <ul>
            <li><b>Registro de Atividades:</b> Preencha suas horas detalhando o escopo e garantindo a <b>Data Real</b> correta da execução.</li>
            <li><b>Notas Fiscais:</b> Realize o upload do PDF e confirme o valor exato da nota para agilizar o faturamento.</li>
            <li><b>Aprovações:</b> Edições em lançamentos pendentes notificam a administração automaticamente.</li>
        </ul>
        <br><br>
        <p style='color: gray; font-size: 0.85em; text-align: justify;'>
        <i><b>Disclaimer de Segurança:</b> Este é um ambiente corporativo privado. O acesso é restrito a colaboradores e parceiros autorizados da OnCall. Todas as transações financeiras, aprovações e uploads de documentos são registrados com marcação de tempo. Em caso de perda de senha ou necessidade de acesso a novos projetos, contate a administração do sistema.</i>
        </p><br>Desenvolvido por Pedro Reis - 2026
    </div>
    """, unsafe_allow_html=True)
    
    st.stop()

current_user_email = login_visual_map[user_selection_visual]
current_user_data = auth_db[current_user_email]
current_user_name = current_user_data["nome_real"]

password_attempt = st.sidebar.text_input("🔑 Senha de Acesso:", type="password")

if password_attempt != current_user_data["senha"]:
    st.sidebar.error("Senha incorreta.")
    st.stop()

is_admin_session = current_user_data["is_admin"] or (current_user_email in SUPER_ADMINS_LIST)

if is_admin_session:
    st.sidebar.success(f"Logado como ADMIN: {current_user_name}")
else:
    st.sidebar.info(f"Bem-vindo(a), {current_user_name}")

# ==============================================================================
# 7. MENU DE NAVEGAÇÃO E ESTADO DA SESSÃO
# ==============================================================================
st.sidebar.divider()
st.sidebar.subheader("📍 Menu Principal")

if is_admin_session:
    app_menu_options = [
        "📝 Lançamentos", 
        "🗂️ Histórico Pessoal",
        "🧾 Notas Fiscais",
        "➖➖ 🔐 ÁREA ADMIN ➖➖", # <-- Separador Visual Adicionado
        "📊 Gestão de Painéis", 
        "🛡️ Admin Aprovações",
        "💸 Pagamentos", 
        "📈 BI Estratégico", 
        "⚙️ Configurações"
    ]
else:
    app_menu_options = [
        "📝 Lançamentos", 
        "🗂️ Histórico Pessoal",
        "📊 Meu Painel",
        "🧾 Notas Fiscais"
    ]

selected_tab = st.sidebar.radio("Ir para:", app_menu_options)

# Lógica para não quebrar a tela se o admin clicar no separador sem querer
if selected_tab == "➖➖ 🔐 ÁREA ADMIN ➖➖":
    st.sidebar.info("👆 Escolha uma das opções abaixo.")
    st.title("🔐 Área Administrativa")
    st.info("Selecione um dos módulos de gestão no menu lateral para continuar.")
    st.stop()

# ==============================================================================
# 8. PREPARAÇÃO DE DADOS GLOBAL (GLOBAL DATA FETCHING)
# ==============================================================================
try:
    df_lancamentos = fetch_all_launch_data()
    df_projetos = fetch_projects_data()
    df_bancos = fetch_banking_data()
    df_invoices = fetch_invoices_data()
except Exception as e:
    st.error(f"Erro ao carregar dados globais: {e}")
    st.stop()

lista_projetos_ativos = df_projetos['nome'].tolist() if not df_projetos.empty else ["Sustentação", "Projetos", "Outros"]
colaboradores_unicos_email = sorted(df_lancamentos['colaborador_email'].unique()) if not df_lancamentos.empty else []
lista_colaboradores_visual = [f"{email_to_name_map.get(e, e)} ({e})" for e in colaboradores_unicos_email]

if not df_lancamentos.empty:
    df_lancamentos['Nome'] = df_lancamentos['colaborador_email'].map(email_to_name_map).fillna(df_lancamentos['colaborador_email'])
    
    if 'data_atividade' in df_lancamentos.columns:
        df_lancamentos['Data Real'] = pd.to_datetime(df_lancamentos['data_atividade'], errors='coerce').dt.date
    else:
        df_lancamentos['Data Real'] = pd.NaT

    df_lancamentos['Importado Em'] = pd.to_datetime(df_lancamentos['data_registro']).dt.date
    df_lancamentos['Data Real'] = df_lancamentos['Data Real'].fillna(df_lancamentos['Importado Em'])
    
    if 'foi_editado' not in df_lancamentos.columns:
        df_lancamentos['foi_editado'] = False
    else:
        df_lancamentos['foi_editado'] = df_lancamentos['foi_editado'].fillna(False).astype(bool)

# ==============================================================================
# ABA 1: LANÇAMENTOS (USER INTERFACE)
# ==============================================================================
if selected_tab == "📝 Lançamentos":
    st.subheader(f"📝 Registro de Atividade - {current_user_name}")
    
    with st.expander("ℹ️ Guia de Preenchimento", expanded=False):
        st.markdown("""
        * **Data Real:** Dia da execução da tarefa.
        * **Horas:** Use ponto para minutos (ex: 1.30 = 1h30min).
        * **Descrição:** Detalhe a entrega de forma clara.
        """)
    
    with st.form("form_lancamento_main", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        input_projeto = c1.selectbox("Projeto", lista_projetos_ativos)
        input_tipo = c2.selectbox("Tipo de Atividade", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design", "Apoio"])
        input_data = c3.date_input("Data REAL da Atividade", datetime.now())
        
        c4, c5 = st.columns([1, 2])
        input_horas = c4.number_input("Horas (HH.MM)", min_value=0.0, step=0.10, format="%.2f", help="Ex: 1.30 para 1h 30min")
        input_desc = c5.text_input("Descrição Detalhada")
        
        if st.form_submit_button("🚀 Gravar Lançamento", type="primary"):
            if input_horas > 0 and input_desc:
                try:
                    competencia_str = input_data.strftime("%Y-%m")
                    data_full_str = input_data.strftime("%Y-%m-%d")
                    valor_hora_atual = auth_db[current_user_email]["valor_hora"]
                    
                    with conn.session as s:
                        s.execute(
                            text("""
                                INSERT INTO lancamentos 
                                (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico, foi_editado) 
                                VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v, FALSE)
                            """),
                            {
                                "id": str(uuid.uuid4()), 
                                "e": current_user_email, 
                                "p": input_projeto, 
                                "h": input_horas, 
                                "c": competencia_str, 
                                "d_atv": data_full_str, 
                                "t": input_tipo, 
                                "d": input_desc, 
                                "v": valor_hora_atual
                            }
                        )
                        s.commit()
                    
                    st.toast(f"✅ Lançamento salvo: {input_horas}h em {data_full_str}", icon="✅")
                    time.sleep(1.5)
                    st.rerun()
                    
                except Exception as e:
                    st.error("Erro ao salvar no banco de dados.")
                    st.error(f"Detalhe: {e}")
            else:
                st.warning("⚠️ Preencha as horas (> 0) e a descrição.")

# ==============================================================================
# ABA 2: HISTÓRICO PESSOAL (USER EDITA SEUS PENDENTES)
# ==============================================================================
elif selected_tab == "🗂️ Histórico Pessoal":
    st.subheader(f"🗂️ Meus Registros - {current_user_name}")
    st.info("💡 Você pode editar lançamentos que ainda estão **Pendentes**. A edição enviará uma notificação ao administrador.")
    
    my_df = df_lancamentos[df_lancamentos['colaborador_email'] == current_user_email].copy()
    
    if not my_df.empty:
        tab_pend, tab_aprov, tab_neg = st.tabs(["⏳ Pendentes (Editável)", "✅ Aprovados", "❌ Negados"])
        
        with tab_pend:
            my_pend = my_df[my_df['status_aprovaca'] == 'Pendente'].copy()
            if not my_pend.empty:
                edited_my_pend = st.data_editor(
                    my_pend[['descricao', 'projeto', 'Data Real', 'horas', 'tipo', 'id']],
                    use_container_width=True, 
                    hide_index=True, 
                    key="user_edit_pend",
                    column_config={
                        "Data Real": st.column_config.DateColumn("Data Ativ.", format="DD/MM/YYYY"),
                        "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                        "id": None 
                    }
                )
                
                if st.button("💾 Salvar Minhas Edições"):
                    count_edits = 0
                    with conn.session as s:
                        for row in edited_my_pend.itertuples():
                            try:
                                d_val = row.Data_Real if hasattr(row, 'Data_Real') else getattr(row, '_3', None)
                                
                                if isinstance(d_val, str): 
                                    d_val = datetime.strptime(d_val, "%Y-%m-%d").date()
                                elif isinstance(d_val, pd.Timestamp): 
                                    d_val = d_val.date()
                                
                                c_s = d_val.strftime("%Y-%m")
                                d_s = d_val.strftime("%Y-%m-%d")
                                
                                s.execute(
                                    text("""
                                        UPDATE lancamentos 
                                        SET descricao=:d, projeto=:p, horas=:h, data_atividade=:da, competencia=:c, foi_editado=TRUE 
                                        WHERE id=:id
                                    """),
                                    {"d": row.descricao, "p": row.projeto, "h": row.horas, "da": d_s, "c": c_s, "id": row.id}
                                )
                                count_edits += 1
                            except Exception as e: 
                                st.error(f"Erro ao salvar linha ID {row.id}: {e}")
                        s.commit()
                    
                    if count_edits > 0:
                        st.toast("Edições salvas! O Admin foi notificado.", icon="⚠️")
                        time.sleep(1.5)
                        st.rerun()
            else:
                st.info("Você não tem itens pendentes no momento.")

        with tab_aprov:
            st.dataframe(
                my_df[my_df['status_aprovaca'] == 'Aprovado'][['descricao', 'Data Real', 'horas', 'valor_hora_historico', 'competencia']],
                use_container_width=True, 
                hide_index=True, 
                column_config={"Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY")}
            )

        with tab_neg:
            st.dataframe(
                my_df[my_df['status_aprovaca'] == 'Negado'][['descricao', 'Data Real', 'horas']],
                use_container_width=True, 
                hide_index=True
            )
    else:
        st.info("Nenhum histórico encontrado para seu usuário.")

# ==============================================================================
# ABA 3: PAINEL GERENCIAL (ADMIN VE TODOS / USER VE SEU)
# ==============================================================================
elif "Painel" in selected_tab or "Gestão" in selected_tab:
    st.subheader("📊 Painel Financeiro e de Auditoria")
    
    target_email = current_user_email
    target_name_curr = current_user_name
    
    if is_admin_session:
        c_sel_admin, _ = st.columns([2, 2])
        lista_outros = [x for x in lista_colaboradores_visual if current_user_email not in x]
        lista_adm_completa = [f"{current_user_name} ({current_user_email})"] + lista_outros
        
        sel_admin_val = c_sel_admin.selectbox(
            "👁️ (Admin) Visualizar Painel de:", 
            lista_adm_completa,
            help="Selecione um colaborador para auditar."
        )
        
        target_email = sel_admin_val.split('(')[-1].replace(')', '')
        target_name_curr = email_to_name_map.get(target_email, target_email)
    
    st.markdown(f"**Analisando dados de:** `{target_name_curr}`")
    st.write("---")
    
    if not df_lancamentos.empty:
        all_competencias = sorted(df_lancamentos['competencia'].astype(str).unique(), reverse=True)
    else:
        all_competencias = []
        
    c_f1, c_f2 = st.columns([1, 3])
    
    comp_selecionadas = c_f1.multiselect(
        "📅 Filtrar Competência(s):", 
        all_competencias, 
        default=all_competencias[:1] if all_competencias else None
    )
    
    df_painel = df_lancamentos[df_lancamentos["colaborador_email"] == target_email].copy()
    
    if not df_painel.empty and comp_selecionadas:
        df_painel = df_painel[df_painel['competencia'].isin(comp_selecionadas)]
    
    if not df_painel.empty and comp_selecionadas:
        df_painel['h_dec'] = df_painel['horas'].apply(convert_hhmm_to_decimal)
        df_painel['valor_total'] = df_painel['h_dec'] * df_painel['valor_hora_historico']
        
        st.markdown("### Resumo Financeiro do Período")
        k1, k2, k3, k4 = st.columns(4)
        
        h_pend = df_painel[df_painel['status_aprovaca'] == 'Pendente']['horas'].sum()
        h_aprov = df_painel[df_painel['status_aprovaca'] == 'Aprovado']['horas'].sum()
        h_pago = df_painel[df_painel['status_pagamento'] == 'Pago']['horas'].sum()
        val_total_periodo = df_painel['valor_total'].sum()
        
        k1.metric("Pendente (HH.MM)", f"{h_pend:.2f}", delta="Aguardando", delta_color="off")
        k2.metric("Aprovado (HH.MM)", f"{h_aprov:.2f}", delta="Validado", delta_color="normal")
        k3.metric("Pago (HH.MM)", f"{h_pago:.2f}", delta="Liquidado", delta_color="normal")
        k4.metric("Valor Total Estimado", f"R$ {val_total_periodo:,.2f}")
        
        st.divider()
        st.markdown(f"### 📋 Detalhamento ({len(df_painel)} registros)")
        
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
                "status_aprovaca": st.column_config.TextColumn("Status"),
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
# ABA 4: ADMIN APROVAÇÕES E IMPORTAÇÃO BLINDADA
# ==============================================================================
elif selected_tab == "🛡️ Admin Aprovações":
    st.subheader("🛡️ Central de Gestão Operacional")
    
    # --- BLOCO A: IMPORTAÇÃO EM MASSA (DUPLA OPÇÃO) ---
    st.markdown("### 📥 Importação em Massa")
    tab_xlsx, tab_texto = st.tabs(["📊 Importar Planilha (XLSX)", "📋 Copiar e Colar (Texto)"])

    # OPÇÃO 1: UPLOAD DE PLANILHA
    with tab_xlsx:
        st.info("Faça o upload da planilha e mapeie as colunas. A competência será gerada automaticamente.")
        uploaded_file = st.file_uploader("Upload de Lançamentos", type=['xlsx', 'xls'])
        
        if uploaded_file is not None:
            try:
                df_import = pd.read_excel(uploaded_file)
                cols_opcoes = ["-- Selecione --"] + df_import.columns.tolist()
                
                st.write("**De/Para de Colunas:**")
                c_mp1, c_mp2, c_mp3 = st.columns(3)
                map_data = c_mp1.selectbox("Data da Atividade *", cols_opcoes, index=0)
                map_email = c_mp2.selectbox("Email Colaborador *", cols_opcoes, index=0)
                map_proj = c_mp3.selectbox("Projeto *", cols_opcoes, index=0)
                
                c_mp4, c_mp5, c_mp6 = st.columns(3)
                map_horas = c_mp4.selectbox("Horas *", cols_opcoes, index=0)
                map_tipo = c_mp5.selectbox("Tipo de Atividade", cols_opcoes, index=0)
                map_desc = c_mp6.selectbox("Descrição *", cols_opcoes, index=0)
                
                st.warning("⚠️ **Dica:** Se as datas da sua planilha estiverem formatadas como Dia/Mês (Padrão BR), mantenha a caixa abaixo marcada.")
                corrigir_inversao = st.checkbox("🔄 Corrigir Inversão de Dia/Mês automática do Excel", value=True)
                
                if st.button("🚀 Executar Importação XLSX", type="primary"):
                    valid = all(v != "-- Selecione --" for v in [map_data, map_email, map_proj, map_horas, map_desc])
                    if not valid:
                        st.error("Mapeie todas as colunas obrigatórias sinalizadas com asterisco (*).")
                    else:
                        count_imported = 0
                        with conn.session as s:
                            for idx, r in df_import.iterrows():
                                try:
                                    dt_val = r[map_data]
                                    if isinstance(dt_val, str):
                                        dt_str = str(dt_val).strip().split(" ")[0]
                                        dt_obj = pd.to_datetime(dt_str, dayfirst=True)
                                    else:
                                        dt_obj = pd.to_datetime(dt_val)
                                        
                                    if corrigir_inversao:
                                        try:
                                            dt_obj = dt_obj.replace(day=dt_obj.month, month=dt_obj.day)
                                        except ValueError:
                                            pass
                                            
                                    comp_str = dt_obj.strftime("%Y-%m")
                                    data_full = dt_obj.strftime("%Y-%m-%d")
                                except Exception as e:
                                    now = datetime.now()
                                    comp_str = now.strftime("%Y-%m")
                                    data_full = now.strftime("%Y-%m-%d")
                                
                                email_colab = str(r[map_email]).strip()
                                v_h = auth_db.get(email_colab, {}).get("valor_hora", 0)
                                tipo_val = r[map_tipo] if map_tipo != "-- Selecione --" else "Outros"
                                
                                s.execute(
                                    text("""
                                        INSERT INTO lancamentos 
                                        (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico, status_aprovaca, foi_editado) 
                                        VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v, 'Pendente', FALSE)
                                    """),
                                    {
                                        "id": str(uuid.uuid4()), "e": email_colab, "p": r[map_proj], "h": float(r[map_horas]), 
                                        "c": comp_str, "d_atv": data_full, "t": tipo_val, "d": r[map_desc], "v": v_h
                                    }
                                )
                                count_imported += 1
                            s.commit()
                        st.success(f"{count_imported} registros importados com sucesso!")
                        time.sleep(1.5); st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

    # OPÇÃO 2: COPIA E COLA TEXTO
    with tab_texto:
        st.info("O sistema identificará a data automaticamente (DD/MM/AAAA).")
        # Texto ajustado para a ordem real da sua planilha
        st.write("**Ordem obrigatória das colunas:** Data | Projeto | Email | Tipo | Horas | Descrição")
        cola_texto = st.text_area("Cole os dados do Excel aqui (separados por colunas):", height=150)
        
        if cola_texto and st.button("🚀 Processar Texto", type="primary"):
            try:
                # MÁGICA AQUI: Invertemos o "t" e o "h" para ler "Tipo" antes de "Horas"
                df_p = pd.read_csv(io.StringIO(cola_texto), sep='\t', names=["data", "p", "e", "t", "h", "d"])
                count_imported = 0
                
                with conn.session as s:
                    for r in df_p.itertuples():
                        email_colab = str(r.e).strip()
                        v_h = auth_db.get(email_colab, {}).get("valor_hora", 0)
                        
                        # Tratamento Data Padrão BR para o texto
                        try:
                            dt_str = str(r.data).strip().split(" ")[0]
                            dt_obj = pd.to_datetime(dt_str, dayfirst=True)
                            comp_str = dt_obj.strftime("%Y-%m")
                            data_full = dt_obj.strftime("%Y-%m-%d")
                        except:
                            now = datetime.now()
                            comp_str = now.strftime("%Y-%m")
                            data_full = now.strftime("%Y-%m-%d")

                        s.execute(
                            text("""
                                INSERT INTO lancamentos 
                                (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico, status_aprovaca, foi_editado) 
                                VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v, 'Pendente', FALSE)
                            """),
                            {
                                "id": str(uuid.uuid4()), "e": email_colab, "p": r.p, "h": float(r.h), 
                                "c": comp_str, "d_atv": data_full, "t": r.t, "d": r.d, "v": v_h
                            }
                        )
                        count_imported += 1
                    s.commit()
                st.success(f"{count_imported} registros colados e importados com sucesso!")
                time.sleep(1.5); st.rerun()
            except Exception as e:
                st.error("Erro na leitura do texto. Verifique se copiou na ordem correta e se não tem colunas vazias.")
                st.code(str(e))
    st.divider()
    
    # --- BLOCO B: PENDENTES ---
    st.markdown("### 🕒 Fila de Pendentes")
    
    c_chk, c_fil = st.columns([1, 3])
    sel_all = c_chk.checkbox("Selecionar Todos")
    
    lista_filtro_pend = ["Todos"] + lista_colaboradores_visual
    f_p = c_fil.selectbox("Filtrar Pendentes:", lista_filtro_pend, key="fp_adm")
    
    df_p = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Pendente'].copy()
    if f_p != "Todos":
        e_p = f_p.split('(')[-1].replace(')', '')
        df_p = df_p[df_p['colaborador_email'] == e_p]
        
    if not df_p.empty:
        df_p = df_p[['foi_editado', 'descricao', 'Nome', 'projeto', 'Data Real', 'horas', 'id']]
        df_p.insert(0, "✅", sel_all)
        df_p.insert(1, "🗑️", False)
        
        ed_p = st.data_editor(
            df_p, 
            use_container_width=True, 
            hide_index=True, 
            key="adm_pend",
            column_config={
                "✅": st.column_config.CheckboxColumn("Apv", width="small"),
                "🗑️": st.column_config.CheckboxColumn("Rej", width="small"),
                "foi_editado": st.column_config.CheckboxColumn("⚠️ Editado?", disabled=True, help="O usuário alterou este item recentemente!"),
                "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "horas": st.column_config.NumberColumn("HH.MM", format="%.2f")
            }
        )
        
        c1, c2 = st.columns(2)
        if c1.button("Aprovar Selecionados", type="primary"):
            ids = ed_p[ed_p["✅"] == True]["id"].tolist()
            if ids:
                with conn.session as s:
                    s.execute(text("UPDATE lancamentos SET status_aprovaca='Aprovado', foi_editado=FALSE WHERE id IN :ids"), {"ids": tuple(ids)})
                    s.commit()
                st.toast("Aprovado!")
                time.sleep(0.5)
                st.rerun()
                
        if c2.button("Rejeitar Selecionados"):
            ids = ed_p[ed_p["🗑️"] == True]["id"].tolist()
            if ids:
                with conn.session as s:
                    s.execute(text("UPDATE lancamentos SET status_aprovaca='Negado' WHERE id IN :ids"), {"ids": tuple(ids)})
                    s.commit()
                st.toast("Rejeitado!")
                time.sleep(0.5)
                st.rerun()
    else:
        st.info("Nada pendente.")

    st.divider()
    
    # --- BLOCO C: APROVADOS (EDIÇÃO TOTAL + EXCLUSÃO + SYNC DATA) ---
    st.markdown("### ✅ Histórico de Aprovados (Edição e Exclusão)")
    st.caption("Ajuste datas, projetos, ou exclua itens aprovados indevidamente.")
    
    f_a = st.selectbox("Filtrar Aprovados:", lista_filtro_pend, key="fa_adm")
    
    df_a = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Aprovado'].copy()
    if f_a != "Todos":
        e_a = f_a.split('(')[-1].replace(')', '')
        df_a = df_a[df_a['colaborador_email'] == e_a]
        
    if not df_a.empty:
        df_a = df_a[['descricao', 'Nome', 'projeto', 'competencia', 'Data Real', 'horas', 'status_aprovaca', 'id']]
        
        # Inserir coluna de deleção no dataframe visual
        df_a.insert(0, "Excluir", False)
        
        ed_a = st.data_editor(
            df_a, 
            use_container_width=True, 
            hide_index=True, 
            key="adm_aprov",
            column_config={
                "Excluir": st.column_config.CheckboxColumn("🗑️ Excluir", width="small", help="Marque para deletar este lançamento do banco."),
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
                "Data Real": st.column_config.DateColumn("Data Ativ.", format="DD/MM/YYYY"),
                "competencia": st.column_config.TextColumn("Comp. (Auto)", disabled=True)
            }
        )
        
        if st.button("Salvar Alterações em Aprovados"):
            ids_to_delete = ed_a[ed_a["Excluir"] == True]["id"].tolist()
            df_to_update = ed_a[ed_a["Excluir"] == False]
            
            count_updates = 0
            
            with conn.session as s:
                # 1. Executa as Exclusões
                if ids_to_delete:
                    s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": tuple(ids_to_delete)})
                
                # 2. Executa as Atualizações do restante
                for r in df_to_update.itertuples():
                    try:
                        d_val = getattr(r, "Data_Real") 
                        
                        if isinstance(d_val, str): 
                            d_obj = datetime.strptime(d_val, "%Y-%m-%d").date()
                        elif isinstance(d_val, pd.Timestamp): 
                            d_obj = d_val.date()
                        else:
                            d_obj = d_val 
                        
                        c_s = d_obj.strftime("%Y-%m")
                        d_s = d_obj.strftime("%Y-%m-%d")
                        
                        s.execute(
                            text("""
                                UPDATE lancamentos 
                                SET status_aprovaca=:s, horas=:h, descricao=:d, projeto=:p, competencia=:c, data_atividade=:da 
                                WHERE id=:id
                            """),
                            {"s": r.status_aprovaca, "h": r.horas, "d": r.descricao, "p": r.projeto, "c": c_s, "da": d_s, "id": r.id}
                        )
                        count_updates += 1
                    except Exception as e:
                        st.error(f"Erro ao atualizar linha ID {r.id}: {e}")
                        
                s.commit()
            
            msgs = []
            if ids_to_delete: msgs.append(f"{len(ids_to_delete)} itens excluídos")
            if count_updates > 0: msgs.append(f"{count_updates} itens atualizados")
            
            if msgs:
                st.success(" e ".join(msgs) + " com sucesso!")
                time.sleep(1.5)
                st.rerun()
    else:
        st.info("Nenhum item aprovado para este filtro.")

    # --- BLOCO D: REJEITADOS ---
    st.divider()
    with st.expander("❌ Visualizar Lixeira / Rejeitados"):
        df_n = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Negado'].copy()
        if not df_n.empty:
            df_n = df_n[['descricao', 'Nome', 'Data Real', 'status_aprovaca', 'id']]
            ed_n = st.data_editor(
                df_n, 
                use_container_width=True, 
                hide_index=True, 
                column_config={"status_aprovaca": st.column_config.SelectboxColumn("Ação", options=["Negado", "Pendente"])}
            )
            
            c_rec, c_del = st.columns(2)
            if c_rec.button("💾 Recuperar"):
                with conn.session as s:
                    for r in ed_n.itertuples():
                        if r.status_aprovaca != "Negado":
                            s.execute(text("UPDATE lancamentos SET status_aprovaca=:s WHERE id=:id"), {"s": r.status_aprovaca, "id": r.id})
                    s.commit()
                st.success("Recuperado!")
                st.rerun()
                
            if c_del.button("🔥 EXCLUIR DEFINITIVAMENTE", type="primary"):
                with conn.session as s:
                    ids_del = tuple(ed_n[ed_n['status_aprovaca'] == 'Negado']['id'].tolist())
                    if ids_del:
                        s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": ids_del})
                        s.commit()
                st.warning("Excluído!")
                st.rerun()
        else:
            st.info("Lixeira vazia.")

# ==============================================================================
# ABA 5: NOTAS FISCAIS
# ==============================================================================
elif selected_tab == "🧾 Notas Fiscais":
    st.subheader("🧾 Gestão de Notas Fiscais")
    
    if is_admin_session:
        # VISÃO ADMIN: Cobrar e Aprovar
        st.markdown("### 🛠️ Painel da Administração")
        with st.expander("➕ Cobrar Nova Nota Fiscal", expanded=False):
            st.write("Solicite o envio de uma NF para um colaborador.")
            c_nf1, c_nf2 = st.columns(2)
            nf_colab = c_nf1.selectbox("Colaborador", opcoes_visuais_login)
            nf_comp = c_nf2.text_input("Competência (Ex: 2026-02)", value=datetime.now().strftime("%Y-%m"))
            
            if st.button("Solicitar Envio"):
                email_solic = login_visual_map[nf_colab]
                with conn.session as s:
                    s.execute(
                        text("INSERT INTO invoices (id, collaborator_email, competence, status) VALUES (:id, :e, :c, 'Pendente de Envio')"),
                        {"id": str(uuid.uuid4()), "e": email_solic, "c": nf_comp}
                    )
                    s.commit()
                st.success("Solicitação criada com sucesso!")
                time.sleep(1)
                st.rerun()
        
        st.markdown("### 📋 Análise de NFs")
        if not df_invoices.empty:
            for r in df_invoices.itertuples():
                nm_exibicao = email_to_name_map.get(r.collaborator_email, r.collaborator_email)
                valor_fmt = f"R$ {r.amount:,.2f}" if r.amount else "Aguardando valor"
                
                with st.expander(f"[{r.status}] {nm_exibicao} - {r.competence} - {valor_fmt}"):
                    if r.status == "Pendente de Aprovação":
                        st.info(f"Arquivo: {r.file_name}")
                        
                        # Conversão para Bytes para o Streamlit não dar erro de memoryview
                        with conn.session as s:
                            res = s.execute(text("SELECT file_pdf FROM invoices WHERE id = :id"), {"id": r.id}).fetchone()
                        
                        if res and res[0]:
                            pdf_bytes = bytes(res[0])
                            st.download_button(
                                label="📥 Baixar Arquivo NF", 
                                data=pdf_bytes, 
                                file_name=r.file_name, 
                                mime="application/pdf",
                                key=f"dl_{r.id}"
                            )
                        else: 
                            st.error("Arquivo corrompido ou não encontrado no banco de dados.")
                                
                        c_ap, c_rj = st.columns(2)
                        if c_ap.button("✅ Aprovar NF", key=f"ap_{r.id}"):
                            with conn.session as s: 
                                s.execute(text("UPDATE invoices SET status='Aprovada' WHERE id=:id"), {"id": r.id})
                                s.commit()
                            st.rerun()
                            
                        if c_rj.button("❌ Rejeitar NF", key=f"rj_{r.id}"):
                            with conn.session as s: 
                                s.execute(text("UPDATE invoices SET status='Rejeitada' WHERE id=:id"), {"id": r.id})
                                s.commit()
                            st.rerun()
                    else:
                        st.write(f"Status Atual: **{r.status}**")
        else:
            st.info("Nenhuma Nota Fiscal no sistema.")
            
        st.divider()

    # ==========================================================
    # VISÃO USUÁRIO: Enviar e Acompanhar (Visível para Admin e Users)
    # ==========================================================
    st.markdown("### 📤 Minhas Notas Fiscais (Área do Colaborador)")
    st.write("Suas Notas Fiscais pendentes de envio e histórico.")
    
    my_nfs = df_invoices[df_invoices['collaborator_email'] == current_user_email]
    
    if not my_nfs.empty:
        for r in my_nfs.itertuples():
            with st.expander(f"[{r.status}] Competência: {r.competence}"):
                if r.status in ["Pendente de Envio", "Rejeitada"]:
                    if r.status == "Rejeitada": 
                        st.warning("Sua última NF enviada foi rejeitada. Por favor, reenvie.")
                    
                    with st.form(f"form_nf_{r.id}"):
                        valor_nf = st.number_input("Valor da NF (R$)", min_value=0.0, step=10.0, format="%.2f")
                        pdf_file = st.file_uploader("Anexar PDF da NF", type=['pdf'])
                        
                        if st.form_submit_button("📤 Enviar para Aprovação", type="primary"):
                            if pdf_file and valor_nf > 0:
                                pdf_bytes = pdf_file.getvalue()
                                pdf_name = pdf_file.name
                                with conn.session as s:
                                    s.execute(
                                        text("UPDATE invoices SET amount=:v, file_name=:an, file_pdf=:ap, status='Pendente de Aprovação' WHERE id=:id"),
                                        {"v": valor_nf, "an": pdf_name, "ap": pdf_bytes, "id": r.id}
                                    )
                                    s.commit()
                                st.success("Nota Fiscal enviada com sucesso!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Preencha o valor e anexe o PDF.")
                else:
                    st.write(f"**Valor:** R$ {r.amount:,.2f}")
                    st.write(f"**Arquivo Anexado:** {r.file_name}")
                    st.success(f"Status: {r.status}")
    else:
        st.info("Você não possui requisições de Nota Fiscal no seu nome.")

# ==============================================================================
# ABA 6: PAGAMENTOS (DRILL-DOWN)
# ==============================================================================
elif selected_tab == "💸 Pagamentos":
    st.subheader("💸 Consolidação Financeira")
    
    df_pay = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Aprovado'].copy()
    
    if not df_pay.empty:
        df_pay['h_dec'] = df_pay['horas'].apply(convert_hhmm_to_decimal)
        df_pay['r$'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
        
        # --- NOVOS SCORECARDS VISUAIS ---
        st.markdown("### 📊 Resumo por Status")
        c1, c2, c3, c4 = st.columns(4)
        
        # Filtra os dados de cada status
        df_aberto = df_pay[df_pay['status_pagamento'] == 'Em aberto']
        df_liberado = df_pay[df_pay['status_pagamento'] == 'Liberado para pagamento']
        df_parcial = df_pay[df_pay['status_pagamento'] == 'Parcial']
        df_pago = df_pay[df_pay['status_pagamento'] == 'Pago']
        
        # Cria os cards (O delta_color="off" deixa a hora em cinza)
        c1.metric("🔴 Em Aberto", f"R$ {df_aberto['r$'].sum():,.2f}", f"{df_aberto['horas'].sum():.2f}h", delta_color="off")
        c2.metric("🔵 Liberado", f"R$ {df_liberado['r$'].sum():,.2f}", f"{df_liberado['horas'].sum():.2f}h", delta_color="off")
        c3.metric("🟡 Parcial", f"R$ {df_parcial['r$'].sum():,.2f}", f"{df_parcial['horas'].sum():.2f}h", delta_color="off")
        c4.metric("🟢 Pago", f"R$ {df_pago['r$'].sum():,.2f}", f"{df_pago['horas'].sum():.2f}h", delta_color="off")
        
        st.divider()
        # --------------------------------
        
        df_g = df_pay.groupby(['competencia', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        df_g = df_g.sort_values(['competencia'], ascending=False)
        
        for idx, row in df_g.iterrows():
            nm = email_to_name_map.get(row['colaborador_email'], row['colaborador_email'])
            
            # 1. Filtra os detalhes PRIMEIRO para descobrir o status do grupo
            det = df_pay[(df_pay['competencia'] == row['competencia']) & (df_pay['colaborador_email'] == row['colaborador_email'])]
            s_at = det['status_pagamento'].iloc[0] if 'status_pagamento' in det.columns and not det.empty else "Em aberto"
            
            # 2. Define a label colorida baseada no status
            if s_at == "Pago":
                badge = "🟢 PAGO"
            elif s_at == "Liberado para pagamento":
                badge = "🔵 LIBERADO"
            elif s_at == "Parcial":
                badge = "🟡 PARCIAL"
            else:
                badge = "🔴 EM ABERTO"
            
            # 3. Adiciona a badge visual direto no título do Drill-Down
            with st.expander(f"{badge} | 📅 {row['competencia']} | 👤 {nm} | R$ {row['r$']:,.2f}"):
                
                st.dataframe(
                    det[['descricao', 'Data Real', 'horas', 'r$', 'status_pagamento']],
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "r$": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                        "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
                    }
                )
                
                ops = ["Em aberto", "Liberado para pagamento", "Parcial", "Pago"]
                ix = ops.index(s_at) if s_at in ops else 0
                
                c1, c2 = st.columns([3, 1])
                ns = c1.selectbox("Status", ops, index=ix, key=f"p_{idx}")
                
                if c2.button("Atualizar Pagamento", key=f"b_{idx}"):
                    with conn.session as s:
                        ids_u = tuple(det['id'].tolist())
                        s.execute(text("UPDATE lancamentos SET status_pagamento=:s WHERE id IN :ids"), {"s": ns, "ids": ids_u})
                        s.commit()
                    st.toast("Status atualizado!")
                    time.sleep(0.5)
                    st.rerun()
    else:
        st.info("Nenhum lançamento aprovado.")

# ==============================================================================
# ABA 7: BI ESTRATÉGICO
# ==============================================================================
elif selected_tab == "📈 BI Estratégico":
    st.subheader("📈 Inteligência de Negócios")
    
    comps = sorted(df_lancamentos['competencia'].astype(str).unique(), reverse=True) if not df_lancamentos.empty else []
    sel_bi = st.multiselect("Filtrar Competências:", comps, default=comps[:2] if comps else None)
    
    df_bi = df_lancamentos.copy()
    if sel_bi and not df_bi.empty:
        df_bi = df_bi[df_bi['competencia'].isin(sel_bi)]
        
        df_bi['tipo_norm'] = df_bi['tipo'].apply(normalize_text_fields)
        df_bi['h_dec'] = df_bi['horas'].apply(convert_hhmm_to_decimal)
        df_bi["custo"] = df_bi['h_dec'] * df_bi["valor_hora_historico"]
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Horas Totais", f"{df_bi['horas'].sum():.2f}")
        m2.metric("Custo Total", f"R$ {df_bi['custo'].sum():,.2f}")
        m3.metric("Pago", f"R$ {df_bi[df_bi['status_pagamento']=='Pago']['custo'].sum():,.2f}")
        m4.metric("Registros", len(df_bi))
        
        c1, c2 = st.columns(2)
        with c1: 
            st.write("**💰 Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        with c2: 
            st.write("**⏱️ Horas por Tipo de Atividade**")
            st.bar_chart(df_bi.groupby("tipo_norm")["horas"].sum())
        
        st.divider()
        st.write("**🏆 Ranking de Colaboradores (Por Nome)**")
        
        rank = df_bi.groupby("Nome").agg({'horas': 'sum', 'custo': 'sum'}).sort_values('horas', ascending=False)
        st.dataframe(rank, use_container_width=True, column_config={"custo": st.column_config.NumberColumn("R$", format="%.2f")})
    else:
        st.info("Selecione uma competência para visualizar os gráficos.")

# ==============================================================================
# ABA 8: CONFIGURAÇÕES (ADMINISTRAÇÃO)
# ==============================================================================
elif selected_tab == "⚙️ Configurações":
    st.subheader("⚙️ Configurações do Sistema")
    
    st.write("👥 **Gestão de Usuários**")
    
    ed_u = st.data_editor(
        df_u_login, 
        num_rows="dynamic", 
        hide_index=True, 
        column_config={
            "email": st.column_config.TextColumn("Login (Email)"),
            "nome": st.column_config.TextColumn("Nome de Exibição"),
            "senha": st.column_config.TextColumn("Senha (Texto)"),
            "is_admin": st.column_config.CheckboxColumn("Admin"),
            "valor_hora": st.column_config.NumberColumn("Valor Hora")
        }
    )
    
    if st.button("Salvar Usuários"):
        with conn.session as s:
            for r in ed_u.itertuples():
                # Validação para ignorar linhas totalmente vazias criadas sem querer
                if pd.isna(r.email) or str(r.email).strip() == "":
                    continue
                    
                nm = getattr(r, 'nome', str(r.email).split('@')[0])
                if pd.isna(nm) or str(nm).strip() == "": 
                    nm = str(r.email).split('@')[0]
                
                s.execute(
                    text("""
                        INSERT INTO usuarios (email, valor_hora, senha, is_admin, nome) 
                        VALUES (:e, :v, :s, :a, :n) 
                        ON CONFLICT (email) 
                        DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a, nome=:n
                    """), 
                    {"e": r.email, "v": r.valor_hora, "s": str(r.senha), "a": bool(r.is_admin), "n": nm}
                )
            s.commit()
        st.success("Usuários salvos com sucesso!")
        st.rerun()
        
    st.divider()
    
    st.write("📁 **Gestão de Projetos**")
    
    ed_p = st.data_editor(
        df_projetos, 
        num_rows="dynamic", 
        hide_index=True
    )
    
    if st.button("Salvar Projetos"):
        with conn.session as s:
            for r in ed_p.itertuples():
                if r.nome: 
                    s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
            s.commit()
        st.success("Projetos salvos com sucesso!")
        st.rerun()

    st.divider()
    
    st.write("🏦 **Dados Bancários**")
    
    ed_b = st.data_editor(
        df_bancos, 
        num_rows="dynamic", 
        hide_index=True, 
        column_config={
            "tipo_chave": st.column_config.SelectboxColumn("Tipo", options=["CPF", "CNPJ", "Email", "Aleatoria", "Agencia/Conta"])
        }
    )
    
    if st.button("Salvar Bancos"):
        with conn.session as s:
            for r in ed_b.itertuples():
                # Ignorar linhas vazias
                if pd.isna(r.colaborador_email) or str(r.colaborador_email).strip() == "":
                    continue
                    
                tk = getattr(r, 'tipo_chave', 'CPF')
                s.execute(
                    text("""
                        INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) 
                        VALUES (:e, :b, :t, :c) 
                        ON CONFLICT (colaborador_email) 
                        DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c
                    """), 
                    {"e": r.colaborador_email, "b": r.banco, "t": tk, "c": r.chave_pix}
                )
            s.commit()
        st.success("Dados bancários salvos com sucesso!")
        st.rerun()

# ==============================================================================
# RODAPÉ
# ==============================================================================
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: gray; font-size: 12px;'>"
    "OnCall Humana - Developed by Pedro Reis | v12.4 Infinity Stable | "
    f"Status: Online | {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    "</p>", 
    unsafe_allow_html=True
)