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
    /* Ajuste do container principal */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 5rem;
        max-width: 98% !important;
    }

    /* --- OS SCORECARDS BONITINHOS VOLTARAM --- */
    /* Estilo dos Cards de Métricas (KPIs) */
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(128, 128, 128, 0.3);
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease-in-out;
    }
    
    /* Efeito de destaque ao passar o mouse */
    div[data-testid="stMetric"]:hover {
        border-color: #0f54c9;
        transform: translateY(-4px);
        background-color: rgba(15, 84, 201, 0.05);
        box-shadow: 0 6px 12px rgba(0,0,0,0.2);
    }

    /* Labels e títulos mais fortes */
    label {
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.02em;
    }

    /* Cabeçalhos de Expander (Azul Corporativo) */
    .streamlit-expanderHeader {
        font-weight: 700;
        font-size: 1.05rem;
        color: #0f54c9;
        background-color: rgba(128, 128, 128, 0.08);
        border-radius: 8px;
        padding: 12px;
        border: 1px solid rgba(128, 128, 128, 0.1);
    }

    /* Botão de Destaque (BI Estratégico) no Sidebar */
    div.stButton > button {
        border-radius: 8px;
        font-weight: bold;
        transition: all 0.2s;
    }

    /* Estilização específica do separador Admin no Menu */
    .admin-divider {
        margin: 1.5rem 0 0.5rem 0;
        padding: 8px;
        background-color: rgba(15, 84, 201, 0.1);
        border-left: 5px solid #0f54c9;
        font-weight: bold;
        color: #0f54c9;
        font-size: 0.75rem;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        border-radius: 0 4px 4px 0;
    }
    
    /* Botões Primários (Gradiente Azul) */
    button[kind="primary"] {
        background: linear-gradient(90deg, #0f54c9 0%, #0a3a8b 100%) !important;
        border: none !important;
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

# Inicializa o estado mestre
if 'selected_tab' not in st.session_state:
    st.session_state.selected_tab = "📝 Lançamentos"
if 'radio_clicked' not in st.session_state:
    st.session_state.radio_clicked = False

def _on_radio_change():
    """Sinaliza que o usuário clicou explicitamente no radio."""
    st.session_state.radio_clicked = True

# --- BOTÃO MINIMALISTA: BI ESTRATÉGICO (SOMENTE ADMIN) ---
# Aqui usamos um gatilho temporário
btn_bi = False
if is_admin_session:
    # Estilo discreto conforme solicitado
    if st.sidebar.button("📈 DASHBOARD ESTRATÉGICO", use_container_width=True):
        btn_bi = True

st.sidebar.subheader("📍 Menu Principal")

if is_admin_session:
    app_menu_options = [
        "📝 Lançamentos", "🗂️ Histórico Pessoal", "🧾 Notas Fiscais",
        "➖➖ 🔐 ÁREA ADMIN ➖➖",
        "📊 Gestão de Painéis", "🛡️ Admin Aprovações", "💸 Pagamentos", "⚙️ Configurações"
    ]
else:
    app_menu_options = ["📝 Lançamentos", "🗂️ Histórico Pessoal", "📊 Meu Painel", "🧾 Notas Fiscais"]

# O rádio funciona independente; on_change detecta clique explícito do usuário
selected_radio = st.sidebar.radio(
    "Ir para:",
    app_menu_options,
    index=app_menu_options.index(st.session_state.selected_tab) if st.session_state.selected_tab in app_menu_options else 0,
    key="main_nav_radio",
    on_change=_on_radio_change
)

# Lê e reseta o flag de clique no radio
radio_clicked = st.session_state.radio_clicked
st.session_state.radio_clicked = False

# --- PRECEDÊNCIA DE NAVEGAÇÃO ---
# Botão BI > clique explícito no radio > manter aba BI > radio normal
if btn_bi:
    selected_tab = "📈 BI Estratégico"
    st.session_state.selected_tab = "📈 BI Estratégico"
elif radio_clicked:
    # Usuário clicou explicitamente no menu → sai do BI se estava lá
    selected_tab = selected_radio
    st.session_state.selected_tab = selected_radio
elif st.session_state.selected_tab == "📈 BI Estratégico":
    # Widget da página BI disparou re-run, mas radio não foi clicado → mantém BI
    selected_tab = "📈 BI Estratégico"
else:
    selected_tab = selected_radio
    st.session_state.selected_tab = selected_radio

# Trava visual para o separador
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
            key="admin_painel_selector",
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
        default=all_competencias[:1] if all_competencias else None,
        key="comp_sel_painel"
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
    
    # --- BLOCO A: INSERÇÃO DE DADOS (ADMIN) ---
    st.markdown("### 📥 Inserção de Dados (Em Massa ou Individual)")
    
    # 1. ADICIONADA A 4ª ABA PARA CUSTOS
    tab_xlsx, tab_texto, tab_indiv, tab_custo = st.tabs(["📊 Importar Planilha (XLSX)", "📋 Copiar e Colar (Texto)", "👤 Lançamento Individual", "💰 Inserir Custo"])

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
        st.write("**Ordem obrigatória das colunas:** Data | Projeto | Email | Tipo | Horas | Descrição")
        cola_texto = st.text_area("Cole os dados do Excel aqui (separados por colunas):", height=150)
        if cola_texto and st.button("🚀 Processar Texto", type="primary"):
            try:
                df_p = pd.read_csv(io.StringIO(cola_texto), sep='\t', names=["data", "p", "e", "t", "h", "d"])
                count_imported = 0
                with conn.session as s:
                    for r in df_p.itertuples():
                        email_colab = str(r.e).strip()
                        v_h = auth_db.get(email_colab, {}).get("valor_hora", 0)
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
                st.error("Erro na leitura do texto. Verifique se copiou na ordem correta.")

    # OPÇÃO 3: LANÇAMENTO INDIVIDUAL (ADMIN)
    with tab_indiv:
        st.info("Insira um lançamento manualmente para um colaborador.")
        with st.form("form_lancamento_admin", clear_on_submit=True):
            c0, c1, c2 = st.columns(3)
            target_user_visual = c0.selectbox("👤 Colaborador Alvo", opcoes_visuais_login)
            input_projeto = c1.selectbox("Projeto", lista_projetos_ativos)
            input_tipo = c2.selectbox("Tipo de Atividade", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design", "Apoio"])
            
            c3, c4, c5 = st.columns([1, 1, 2])
            input_data = c3.date_input("Data REAL da Atividade", datetime.now())
            input_horas = c4.number_input("Horas (HH.MM)", min_value=0.0, step=0.10, format="%.2f")
            input_desc = c5.text_input("Descrição Detalhada")
            status_inicial = st.selectbox("Status do Lançamento", ["Aprovado", "Pendente"], index=0)
            
            if st.form_submit_button("🚀 Gravar Lançamento Individual", type="primary"):
                if input_horas > 0 and input_desc:
                    try:
                        target_email = login_visual_map[target_user_visual]
                        competencia_str = input_data.strftime("%Y-%m")
                        data_full_str = input_data.strftime("%Y-%m-%d")
                        valor_hora_alvo = auth_db[target_email]["valor_hora"]
                        
                        with conn.session as s:
                            s.execute(
                                text("""
                                    INSERT INTO lancamentos 
                                    (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico, status_aprovaca, foi_editado) 
                                    VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v, :st, FALSE)
                                """),
                                {
                                    "id": str(uuid.uuid4()), "e": target_email, "p": input_projeto, "h": input_horas, 
                                    "c": competencia_str, "d_atv": data_full_str, "t": input_tipo, "d": input_desc, 
                                    "v": valor_hora_alvo, "st": status_inicial
                                }
                            )
                            s.commit()
                        st.success(f"✅ Lançamento inserido com sucesso!")
                        time.sleep(1.5); st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
                else:
                    st.warning("⚠️ Preencha as horas (> 0) e a descrição.")

    # 2. NOVA OPÇÃO 4: CUSTO OPERACIONAL
    with tab_custo:
        st.info("Registre um custo direto (ex: Servidor, Ferramentas). O valor refletirá nos relatórios de BI e Pagamentos.")
        with st.form("form_custo_admin", clear_on_submit=True):
            c0, c1 = st.columns(2)
            # Admin escolhe quem pagou/reembolsou (ou seleciona ele mesmo se for da empresa)
            target_user_visual = c0.selectbox("👤 Responsável pelo Custo", opcoes_visuais_login, help="A quem este custo está atrelado para registro ou reembolso.")
            input_projeto_custo = c1.selectbox("Projeto Atrelado", lista_projetos_ativos)
            
            c3, c4, c5 = st.columns([1, 1, 2])
            input_data_custo = c3.date_input("Data do Custo", datetime.now())
            # Recebe o Valor em Reais
            input_valor_custo = c4.number_input("Valor Total (R$)", min_value=0.0, step=10.0, format="%.2f")
            input_desc_custo = c5.text_input("Descrição (Ex: AWS, Banco de Dados)")
            
            status_inicial_custo = st.selectbox("Status", ["Aprovado", "Pendente"], index=0)
            
            if st.form_submit_button("🚀 Gravar Custo Operacional", type="primary"):
                if input_valor_custo > 0 and input_desc_custo:
                    try:
                        target_email = login_visual_map[target_user_visual]
                        competencia_str = input_data_custo.strftime("%Y-%m")
                        data_full_str = input_data_custo.strftime("%Y-%m-%d")
                        
                        with conn.session as s:
                            # A mágica: Salva como 1 hora, mas joga o valor total na coluna de "valor_hora_historico"
                            s.execute(
                                text("""
                                    INSERT INTO lancamentos 
                                    (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico, status_aprovaca, foi_editado) 
                                    VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v, :st, FALSE)
                                """),
                                {
                                    "id": str(uuid.uuid4()), "e": target_email, "p": input_projeto_custo, 
                                    "h": 1.0, # Horas = 1
                                    "c": competencia_str, "d_atv": data_full_str, 
                                    "t": "Custo Operacional", "d": f"[CUSTO] {input_desc_custo}", 
                                    "v": input_valor_custo, # Valor da Nota/Custo
                                    "st": status_inicial_custo
                                }
                            )
                            s.commit()
                        st.success(f"✅ Custo de R$ {input_valor_custo:,.2f} registrado com sucesso!")
                        time.sleep(1.5); st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
                else:
                    st.warning("⚠️ Preencha o valor e a descrição.")

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
        df_p = df_p[['foi_editado', 'descricao', 'Nome', 'projeto', 'tipo', 'Data Real', 'horas', 'id']]
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
                "foi_editado": st.column_config.CheckboxColumn("⚠️ Editado?", disabled=True),
                "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos_ativos, required=True),
                # 3. Adicionado "Custo Operacional" na lista de opções para evitar erros de edição
                "tipo": st.column_config.SelectboxColumn("Item (Tipo)", options=["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design", "Apoio", "Custo Operacional", "Outros"], required=True)
            }
        )
        
        c1, c2 = st.columns(2)
        if c1.button("Aprovar Selecionados", type="primary"):
            df_to_approve = ed_p[ed_p["✅"] == True]
            if not df_to_approve.empty:
                with conn.session as s:
                    for r in df_to_approve.itertuples():
                        s.execute(
                            text("UPDATE lancamentos SET status_aprovaca='Aprovado', foi_editado=FALSE, projeto=:p, tipo=:t, horas=:h, descricao=:d WHERE id=:id"), 
                            {"p": r.projeto, "t": r.tipo, "h": r.horas, "d": r.descricao, "id": r.id}
                        )
                    s.commit()
                st.toast("Aprovado e atualizado!")
                time.sleep(0.5); st.rerun()
                
        if c2.button("Rejeitar Selecionados"):
            ids = ed_p[ed_p["🗑️"] == True]["id"].tolist()
            if ids:
                with conn.session as s:
                    s.execute(text("UPDATE lancamentos SET status_aprovaca='Negado' WHERE id IN :ids"), {"ids": tuple(ids)})
                    s.commit()
                st.toast("Rejeitado!")
                time.sleep(0.5); st.rerun()
    else:
        st.info("Nada pendente.")

    st.divider()
    
   # --- BLOCO C: APROVADOS (EDIÇÃO TOTAL + EXCLUSÃO + SYNC DATA) ---
    st.markdown("### ✅ Histórico de Aprovados (Edição e Exclusão)")
    st.caption("Ajuste datas, projetos, tipos (itens) ou exclua itens aprovados indevidamente.")
    
    f_a = st.selectbox("Filtrar Aprovados:", lista_filtro_pend, key="fa_adm")
    
    df_a = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Aprovado'].copy()
    if f_a != "Todos":
        e_a = f_a.split('(')[-1].replace(')', '')
        df_a = df_a[df_a['colaborador_email'] == e_a]
        
    if not df_a.empty:
        df_a = df_a[['descricao', 'Nome', 'projeto', 'tipo', 'competencia', 'Data Real', 'horas', 'status_aprovaca', 'id']]
        df_a.insert(0, "Excluir", False)
        
        ed_a = st.data_editor(
            df_a, 
            use_container_width=True, 
            hide_index=True, 
            key="adm_aprov",
            column_config={
                "Excluir": st.column_config.CheckboxColumn("🗑️ Excluir", width="small"),
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
                "Data Real": st.column_config.DateColumn("Data Ativ.", format="DD/MM/YYYY"),
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos_ativos, required=True),
                "tipo": st.column_config.SelectboxColumn("Item (Tipo)", options=["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design", "Apoio", "Custo Operacional", "Outros"], required=True)
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
                
                # 2. Executa as Atualizações
                for r in df_to_update.itertuples():
                    try:
                        # Tenta pegar a data de várias formas para não dar None
                        d_val = getattr(r, 'Data_Real', None)
                        if d_val is None:
                            # Se falhar pelo nome, tenta pegar pela posição (Data Real costuma ser a 7ª coluna no itertuples aqui)
                            d_val = r[7] 
                        
                        # Se mesmo assim for nulo, pula a linha para não dar erro de strftime
                        if pd.isna(d_val):
                            continue
                            
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
                                SET status_aprovaca=:s, horas=:h, descricao=:d, projeto=:p, tipo=:t, competencia=:c, data_atividade=:da 
                                WHERE id=:id
                            """),
                            {"s": r.status_aprovaca, "h": r.horas, "d": r.descricao, "p": r.projeto, "t": r.tipo, "c": c_s, "da": d_s, "id": r.id}
                        )
                        count_updates += 1
                    except Exception as e:
                        st.error(f"Erro no ID {r.id}: {e}")
                s.commit()
            
            st.success(f"Processado: {count_updates} atualizados!")
            time.sleep(1)
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
# ABA 6: PAGAMENTOS (COM CÁLCULO DE SALDO DEVEDOR)
# ==============================================================================
elif selected_tab == "💸 Pagamentos":
    st.subheader("💸 Consolidação Financeira")
    
    # Puxa os dados base (apenas aprovados)
    df_pay_base = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Aprovado'].copy()
    
    if not df_pay_base.empty:
        # Garante colunas necessárias
        if 'observacao_financeira' not in df_pay_base.columns: df_pay_base['observacao_financeira'] = ""
        if 'valor_pago' not in df_pay_base.columns: df_pay_base['valor_pago'] = 0.0

        # --- FILTRO DE COMPETÊNCIA ---
        all_comps_pay = sorted(df_pay_base['competencia'].astype(str).unique(), reverse=True)
        comp_sel_pay = st.multiselect(
            "📅 Filtrar Competência(s):", all_comps_pay, 
            default=all_comps_pay[:1] if all_comps_pay else None,
            key="filtro_comp_pagamentos"
        )
        
        # Aplica o filtro
        if comp_sel_pay:
            df_pay = df_pay_base[df_pay_base['competencia'].isin(comp_sel_pay)].copy()
        else:
            df_pay = pd.DataFrame()
            
        if not df_pay.empty:
            # Cálculos Financeiros
            df_pay['h_dec'] = df_pay['horas'].apply(convert_hhmm_to_decimal)
            df_pay['valor_bruto'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
            df_pay['valor_pago'] = df_pay['valor_pago'].fillna(0.0)
            df_pay['saldo'] = df_pay['valor_bruto'] - df_pay['valor_pago']
            
            # --- STATUS CORREÇÃO ---
            status_conhecidos = ["Pago", "Liberado para pagamento", "Parcial"]
            if 'status_pagamento' not in df_pay.columns:
                df_pay['status_pagamento'] = 'Em aberto'
            else:
                df_pay['status_pagamento'] = df_pay['status_pagamento'].apply(
                    lambda x: str(x).strip() if str(x).strip() in status_conhecidos else 'Em aberto'
                )
            
            # --- KPIS DO TOPO ---
            total_devido = df_pay['valor_bruto'].sum()
            total_pago = df_pay['valor_pago'].sum()
            total_restante = total_devido - total_pago
            
            c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
            c_kpi1.metric("Valor Total (Bruto)", f"R$ {total_devido:,.2f}")
            c_kpi2.metric("Já Pago", f"R$ {total_pago:,.2f}")
            c_kpi3.metric("Falta Pagar", f"R$ {total_restante:,.2f}", delta=f"-{(total_pago/total_devido)*100:.1f}%" if total_devido > 0 else "0%")
            
            st.divider()

            # --- AGRUPAMENTO POR COLABORADOR ---
            df_g = df_pay.groupby(['competencia', 'colaborador_email']).agg({
                'valor_bruto': 'sum',
                'valor_pago': 'sum',
                'saldo': 'sum',
                'horas': 'sum'
            }).reset_index()

            # Verifica se TODOS os lançamentos do grupo têm status='Pago'
            # (evita o problema de 'first' pegar um status 'Pendente' antes de um 'Pago')
            todos_pagos = (
                df_pay.groupby(['competencia', 'colaborador_email'])['status_pagamento']
                .apply(lambda x: (x == 'Pago').all())
                .reset_index()
            )
            todos_pagos.columns = ['competencia', 'colaborador_email', '_todos_pagos']
            df_g = df_g.merge(todos_pagos, on=['competencia', 'colaborador_email'])

            # Quitado = saldo zerado OU todos os lançamentos marcados como Pago
            df_g['_quitado'] = (df_g['saldo'] <= 0.01) | df_g['_todos_pagos']
            df_g = df_g.sort_values(['_quitado', 'competencia'], ascending=[True, False])

            secao_pendente_iniciada = False
            secao_quitado_iniciada = False

            for idx, row in df_g.iterrows():
                nm = email_to_name_map.get(row['colaborador_email'], row['colaborador_email'])

                # Detalhes do grupo
                det = df_pay[(df_pay['competencia'] == row['competencia']) & (df_pay['colaborador_email'] == row['colaborador_email'])]

                # Definição visual do status do card
                # Se todos são Pago, usa 'Pago'; senão pega o status mais frequente (mode)
                if row['_todos_pagos']:
                    s_at = 'Pago'
                elif not det.empty:
                    mode_series = det['status_pagamento'].mode()
                    s_at = mode_series.iloc[0] if not mode_series.empty else "Em aberto"
                else:
                    s_at = "Em aberto"
                saldo_grupo = row['saldo']

                # Cabeçalho de seção (apenas uma vez por grupo)
                if not row['_quitado'] and not secao_pendente_iniciada:
                    st.markdown("#### 🔴 Em Aberto / Parcial / Liberados")
                    secao_pendente_iniciada = True
                elif row['_quitado'] and not secao_quitado_iniciada:
                    st.divider()
                    st.markdown("#### 🟢 Quitados")
                    secao_quitado_iniciada = True

                # Ícone e Cor baseados no saldo e status
                valor_ref = row['valor_pago'] if row['valor_pago'] > 0.01 else row['valor_bruto']
                if row['_quitado']:
                    badge = f"🟢 QUITADO | R$ {valor_ref:,.2f} pago"
                elif row['valor_pago'] > 0:
                    badge = f"🟡 PARCIAL | Pago R$ {row['valor_pago']:,.2f} | Falta R$ {saldo_grupo:,.2f}"
                else:
                    badge = f"🔴 ABERTO | R$ {row['valor_bruto']:,.2f} a pagar"
                
                # Preview da observação
                obs_txt = ""
                obs_val = det['observacao_financeira'].iloc[0]
                if pd.notna(obs_val) and str(obs_val).strip() != "":
                    obs_txt = f" | 📝 {str(obs_val)}"

                with st.expander(f"{badge} | 📅 {row['competencia']} | 👤 {nm}{obs_txt}"):
                    
                    # Tabela detalhada
                    st.dataframe(
                        det[['descricao', 'Data Real', 'horas', 'valor_bruto', 'valor_pago', 'saldo', 'status_pagamento']],
                        use_container_width=True, hide_index=True,
                        column_config={
                            "valor_bruto": st.column_config.NumberColumn("Valor Bruto", format="R$ %.2f"),
                            "valor_pago": st.column_config.NumberColumn("Pago", format="R$ %.2f"),
                            "saldo": st.column_config.NumberColumn("Saldo", format="R$ %.2f"),
                            "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
                        }
                    )
                    
                    # CONTROLES DE AÇÃO
                    ops = ["Em aberto", "Liberado para pagamento", "Parcial", "Pago"]
                    ix = ops.index(s_at) if s_at in ops else 0
                    
                    c_up1, c_up2, c_up3 = st.columns([2, 2, 1])
                    ns = c_up1.selectbox("Status", ops, index=ix, key=f"stat_{idx}")
                    
                    # Inputs condicionais
                    novo_valor_pago = row['valor_pago'] # Valor padrão é o que já está no banco
                    nova_obs = obs_val if pd.notna(obs_val) else ""
                    
                    if ns == "Parcial":
                        novo_valor_pago = c_up2.number_input(
                            "Valor Pago Total (R$):", 
                            min_value=0.0, 
                            max_value=float(row['valor_bruto']),
                            value=float(row['valor_pago']),
                            step=10.0,
                            key=f"val_pay_{idx}",
                            help="Informe o valor TOTAL acumulado que já foi pago para este grupo."
                        )
                        nova_obs = st.text_input("Observação Financeira:", value=str(nova_obs), key=f"obs_pay_{idx}")
                    
                    elif ns == "Pago":
                        # Se marcou Pago, o valor pago vira o valor bruto automaticamente
                        novo_valor_pago = row['valor_bruto']
                        c_up2.info(f"Será baixado o total: R$ {novo_valor_pago:,.2f}")
                    
                    elif ns == "Em aberto":
                        novo_valor_pago = 0.0
                        c_up2.warning("O valor pago será zerado.")

                    # BOTÃO DE ATUALIZAR
                    if c_up3.button("Salvar Baixa", key=f"btn_{idx}", type="primary"):
                        try:
                            total_bruto_grupo = row['valor_bruto']
                            ratio = (novo_valor_pago / total_bruto_grupo) if total_bruto_grupo > 0 else 0

                            # Usa engine direto (conn._instance) para garantir commit no PostgreSQL
                            rows_updated = 0
                            with conn._instance.connect() as db_conn:
                                for _, det_row in det.iterrows():
                                    vp = float(det_row['valor_bruto']) * ratio
                                    result = db_conn.execute(
                                        text(
                                            "UPDATE lancamentos "
                                            "SET status_pagamento=:s, observacao_financeira=:o, valor_pago=:vp "
                                            "WHERE id=:id"
                                        ),
                                        {"s": ns, "o": nova_obs, "vp": vp, "id": str(det_row['id']).strip()}
                                    )
                                    rows_updated += result.rowcount
                                db_conn.commit()

                            if rows_updated > 0:
                                st.toast(f"✅ {rows_updated} linha(s) atualizada(s)!")
                            else:
                                st.warning("⚠️ Nenhuma linha foi atualizada. Verifique os dados.")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar: {e}")

        else:
            st.info("👆 Selecione pelo menos uma competência acima.")
    else:
        st.info("Nenhum lançamento aprovado no sistema.")
        
# ==============================================================================
# ABA 7: BI ESTRATÉGICO
# ==============================================================================
elif selected_tab == "📈 BI Estratégico":
    st.subheader("📈 Inteligência de Negócios")
    
    comps = sorted(df_lancamentos['competencia'].astype(str).unique(), reverse=True) if not df_lancamentos.empty else []
    sel_bi = st.multiselect("Filtrar Competências:", comps, default=comps[:2] if comps else None, key="bi_comp_filter")
    
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
    
    # --- GESTÃO DE USUÁRIOS ---
    st.write("👥 **Gestão de Usuários**")
    
    # Adiciona a coluna de exclusão no dataframe visual
    df_u_edit = df_u_login.copy()
    df_u_edit.insert(0, "Excluir", False)
    
    ed_u = st.data_editor(
        df_u_edit, 
        num_rows="dynamic", 
        hide_index=True, 
        key="usuarios_editor_fix",
        column_config={
            "Excluir": st.column_config.CheckboxColumn("🗑️ Excl", width="small", default=False),
            "email": st.column_config.TextColumn("Login (Email)", required=True),
            "nome": st.column_config.TextColumn("Nome de Exibição"),
            "senha": st.column_config.TextColumn("Senha (Texto)", required=True),
            "is_admin": st.column_config.CheckboxColumn("Admin", default=False),
            "valor_hora": st.column_config.NumberColumn("Valor Hora", default=0.0)
        }
    )
    
    if st.button("Salvar Usuários", type="primary"):
        # MÁGICA AQUI: Garante que as linhas novas não sejam ignoradas por causa do nulo (NaN)
        ed_u["Excluir"] = ed_u["Excluir"].fillna(False)
        
        ids_to_delete = ed_u[ed_u["Excluir"] == True]["email"].tolist()
        df_to_update = ed_u[ed_u["Excluir"] == False]
        count_u, count_del = 0, 0
        
        with conn.session as s:
            # 1. Processa Exclusões
            if ids_to_delete:
                s.execute(text("DELETE FROM usuarios WHERE email IN :emails"), {"emails": tuple(ids_to_delete)})
                count_del = len(ids_to_delete)
                
            # 2. Processa Inserções/Atualizações
            for r in df_to_update.itertuples():
                if pd.isna(r.email) or str(r.email).strip() == "":
                    continue
                    
                nm = getattr(r, 'nome', str(r.email).split('@')[0])
                if pd.isna(nm) or str(nm).strip() == "": 
                    nm = str(r.email).split('@')[0]
                
                v_hora = float(r.valor_hora) if pd.notna(r.valor_hora) else 0.0
                senha_str = str(r.senha) if pd.notna(r.senha) else "123mudar"
                is_adm = bool(r.is_admin) if pd.notna(r.is_admin) else False
                
                s.execute(
                    text("""
                        INSERT INTO usuarios (email, valor_hora, senha, is_admin, nome) 
                        VALUES (:e, :v, :s, :a, :n) 
                        ON CONFLICT (email) 
                        DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a, nome=:n
                    """), 
                    {"e": str(r.email).strip(), "v": v_hora, "s": senha_str, "a": is_adm, "n": nm}
                )
                count_u += 1
            s.commit()
            
        st.success(f"Salvo! {count_u} atualizados/inseridos, {count_del} excluídos.")
        time.sleep(1.5)
        st.rerun()
        
    st.divider()
    
    # --- GESTÃO DE PROJETOS ---
    st.write("📁 **Gestão de Projetos**")
    
    df_p_edit = df_projetos.copy()
    df_p_edit.insert(0, "Excluir", False)
    
    ed_p = st.data_editor(
        df_p_edit, 
        num_rows="dynamic", 
        hide_index=True,
        key="projetos_editor_fix",
        column_config={
            "Excluir": st.column_config.CheckboxColumn("🗑️ Excl", width="small", default=False),
            "nome": st.column_config.TextColumn("Nome do Projeto", required=True)
        }
    )
    
    if st.button("Salvar Projetos"):
        # MÁGICA AQUI: Salva-vidas do checkbox nulo
        ed_p["Excluir"] = ed_p["Excluir"].fillna(False)
        
        ids_del = ed_p[ed_p["Excluir"] == True]["nome"].tolist()
        df_upd = ed_p[ed_p["Excluir"] == False]
        
        with conn.session as s:
            if ids_del:
                s.execute(text("DELETE FROM projetos WHERE nome IN :ids"), {"ids": tuple(ids_del)})
            for r in df_upd.itertuples():
                if pd.notna(r.nome) and str(r.nome).strip() != "": 
                    s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": str(r.nome).strip()})
            s.commit()
        st.success("Projetos salvos com sucesso!")
        time.sleep(1)
        st.rerun()

    st.divider()
    
    # --- DADOS BANCÁRIOS ---
    st.write("🏦 **Dados Bancários**")
    
    df_b_edit = df_bancos.copy()
    df_b_edit.insert(0, "Excluir", False)
    
    ed_b = st.data_editor(
        df_b_edit, 
        num_rows="dynamic", 
        hide_index=True,
        key="bancos_editor_fix",
        column_config={
            "Excluir": st.column_config.CheckboxColumn("🗑️ Excl", width="small", default=False),
            "tipo_chave": st.column_config.SelectboxColumn("Tipo", options=["CPF", "CNPJ", "Email", "Aleatoria", "Agencia/Conta"])
        }
    )
    
    if st.button("Salvar Bancos"):
        # MÁGICA AQUI: Salva-vidas do checkbox nulo
        ed_b["Excluir"] = ed_b["Excluir"].fillna(False)
        
        ids_del = ed_b[ed_b["Excluir"] == True]["colaborador_email"].tolist()
        df_upd = ed_b[ed_b["Excluir"] == False]
        
        with conn.session as s:
            if ids_del:
                s.execute(text("DELETE FROM dados_bancarios WHERE colaborador_email IN :ids"), {"ids": tuple(ids_del)})
            for r in df_upd.itertuples():
                if pd.isna(r.colaborador_email) or str(r.colaborador_email).strip() == "":
                    continue
                    
                tk = getattr(r, 'tipo_chave', 'CPF')
                c_pix = getattr(r, 'chave_pix', '') if pd.notna(getattr(r, 'chave_pix', '')) else ''
                banco_val = getattr(r, 'banco', '') if pd.notna(getattr(r, 'banco', '')) else ''
                
                s.execute(
                    text("""
                        INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) 
                        VALUES (:e, :b, :t, :c) 
                        ON CONFLICT (colaborador_email) 
                        DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c
                    """), 
                    {"e": str(r.colaborador_email).strip(), "b": banco_val, "t": tk, "c": c_pix}
                )
            s.commit()
        st.success("Dados bancários salvos com sucesso!")
        time.sleep(1)
        st.rerun()

# ==============================================================================
# RODAPÉ
# ==============================================================================
st.markdown("---")
st.markdown(
    "<p style='text-align: center; color: gray; font-size: 12px;'>"
    "OnCall Humana - Developed by Pedro Reis | v12.5 Infinity Stable | "
    f"Status: Online | {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    "</p>", 
    unsafe_allow_html=True
)