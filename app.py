"""
==============================================================================
ONCALL HUMANA - SYSTEM MASTER v12.0 "FINAL STABLE"
==============================================================================
Desenvolvido por: Pedro Reis
Data: Fevereiro/2026
Versão: 12.0 Enterprise Edition (Procedural & Robust)

DESCRIÇÃO TÉCNICA:
Sistema de ERP para gestão de horas, pagamentos e projetos.
Esta versão corrige erros de sintaxe da v9.0 e expande a segurança
e o tratamento de dados, mantendo a arquitetura linear que funcionava.

FUNCIONALIDADES CRÍTICAS:
1. Mapeamento de Nomes (Visualização amigável).
2. Tratamento de Data Real vs Competência Financeira.
3. Edição pelo Usuário com Flag de Auditoria (foi_editado).
4. Painel Administrativo Bipartido com Bulk Import inteligente.

TECNOLOGIAS:
Streamlit, Pandas, SQLAlchemy, PostgreSQL (Neon).
==============================================================================
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
    page_title="OnCall Humana - Master v12.0",
    layout="wide",
    page_icon="🛡️",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.oncall.com.br/help',
        'Report a bug': "mailto:suporte@oncall.com.br",
        'About': "# OnCall Humana ERP v12.0\nSistema Oficial."
    }
)

# ==============================================================================
# 2. ESTILIZAÇÃO CSS AVANÇADA (ENTERPRISE UI)
# ==============================================================================
st.markdown("""
<style>
    /* Ajuste do container principal */
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
    }

    /* Botões Primários */
    button[kind="primary"] {
        font-weight: bold;
        border: 1px solid rgba(255, 75, 75, 0.5);
    }
    
    /* Alerta de Edição */
    .edited-alert {
        color: #ff4b4b;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 3. GERENCIAMENTO DE CONEXÃO COM O BANCO DE DADOS
# ==============================================================================
def get_connection():
    """
    Estabelece conexão segura com o banco de dados Neon (PostgreSQL).
    Retorna o objeto de conexão ou para a aplicação em erro.
    """
    try:
        # Cria a conexão usando a engine nativa do Streamlit
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
conn = get_connection()

# ==============================================================================
# 4. BIBLIOTECA DE FUNÇÕES UTILITÁRIAS (HELPER FUNCTIONS)
# ==============================================================================

def convert_hhmm_to_decimal(pseudo_hour):
    """
    Converte o formato visual HH.MM (Ex: 2.30) para Decimal (2.50).
    Isso é fundamental para que o cálculo financeiro (Horas * Valor) seja exato.
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
        
        # Proteção: Se minutos >= 60, assume decimal puro
        if minutos >= 60:
            return float(pseudo_hour)
            
        # Cálculo: Horas + (Minutos / 60)
        return horas_inteiras + (minutos / 60.0)
    except Exception:
        return 0.0

def normalize_text_fields(text_val):
    """
    Padroniza strings para garantir consistência no Banco de Dados e BI.
    Remove espaços extras e resolve variações comuns de escrita.
    """
    if not isinstance(text_val, str):
        return "Outros"
        
    t = text_val.strip().lower()
    
    # Mapeamento de normalização
    if "back" in t and "end" in t: return "Back-end"
    if "front" in t and "end" in t: return "Front-end"
    if "dados" in t or "data" in t: return "Eng. Dados"
    if "infra" in t: return "Infraestrutura"
    if "qa" in t or "test" in t: return "QA / Testes"
    if "banco" in t: return "Banco de Dados"
    if "reuni" in t: return "Reunião"
    if "gest" in t: return "Gestão"
    if "design" in t: return "Design/UX"
    
    return text_val.capitalize()

# ==============================================================================
# 5. DATA ACCESS LAYER (DAL) - FUNÇÕES DE LEITURA
# ==============================================================================

def fetch_all_launch_data(): 
    """Busca a tabela completa de lançamentos."""
    query = "SELECT * FROM lancamentos ORDER BY competencia DESC, data_atividade DESC, data_registro DESC"
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
# Cria um dicionário {email: Nome Real} para exibir nomes em vez de e-mails.
email_to_name_map = {}

if not df_u_login.empty:
    for row in df_u_login.itertuples():
        nome_db = getattr(row, 'nome', None)
        if nome_db and str(nome_db).strip() != "":
            email_to_name_map[row.email] = str(nome_db).strip()
        else:
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

SUPER_ADMINS_LIST = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- SIDEBAR: TELA DE LOGIN ---
st.sidebar.title("🛡️ OnCall Humana")
st.sidebar.caption("v12.0 Final Stable")
st.sidebar.markdown("---")

if not auth_db:
    st.error("Tabela de usuários vazia.")
    st.stop()

# 1. Lista de chaves (emails)
lista_emails_sistema = list(auth_db.keys())

# 2. Lista de exibição (Nome + Email)
opcoes_visuais_login = [f"{email_to_name_map.get(e, e)} ({e})" for e in lista_emails_sistema]

# 3. Mapa reverso (Visual -> Email)
login_visual_map = dict(zip(opcoes_visuais_login, lista_emails_sistema))

# 4. Widget Selectbox (AQUI ESTAVA O ERRO DE SINTAXE ANTERIOR, AGORA CORRIGIDO)
user_selection_visual = st.sidebar.selectbox(
    "👤 Identifique-se:", 
    ["..."] + opcoes_visuais_login
)

# Bloqueio inicial se não selecionado
if user_selection_visual == "...":
    st.info("👈 Selecione seu usuário no menu lateral.")
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
    st.sidebar.success(f"Admin: {current_user_name}")
else:
    st.sidebar.info(f"Bem-vindo(a), {current_user_name}")

# ==============================================================================
# 7. MENU DE NAVEGAÇÃO
# ==============================================================================
st.sidebar.divider()
st.sidebar.subheader("📍 Menu")

if is_admin_session:
    app_menu_options = [
        "📝 Lançamentos", 
        "🗂️ Histórico Pessoal", # Admin também pode ver o seu
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
        "📊 Meu Painel"
    ]

selected_tab = st.sidebar.radio("Ir para:", app_menu_options)

# ==============================================================================
# 8. PREPARAÇÃO DE DADOS GLOBAL
# ==============================================================================
try:
    df_lancamentos = fetch_all_launch_data()
    df_projetos = fetch_projects_data()
    df_bancos = fetch_banking_data()
except Exception as e:
    st.error(f"Erro ao carregar dados globais: {e}")
    st.stop()

lista_projetos_ativos = df_projetos['nome'].tolist() if not df_projetos.empty else ["Sustentação", "Projetos", "Outros"]
colaboradores_unicos_email = sorted(df_lancamentos['colaborador_email'].unique()) if not df_lancamentos.empty else []
lista_colaboradores_visual = [f"{email_to_name_map.get(e, e)} ({e})" for e in colaboradores_unicos_email]

# --- TRATAMENTO E ENRIQUECIMENTO DO DATAFRAME ---
if not df_lancamentos.empty:
    # 1. Coluna Nome
    df_lancamentos['Nome'] = df_lancamentos['colaborador_email'].map(email_to_name_map).fillna(df_lancamentos['colaborador_email'])
    
    # 2. Data Real
    if 'data_atividade' in df_lancamentos.columns:
        df_lancamentos['Data Real'] = pd.to_datetime(df_lancamentos['data_atividade'], errors='coerce').dt.date
    else:
        df_lancamentos['Data Real'] = pd.NaT

    df_lancamentos['Importado Em'] = pd.to_datetime(df_lancamentos['data_registro']).dt.date
    df_lancamentos['Data Real'] = df_lancamentos['Data Real'].fillna(df_lancamentos['Importado Em'])
    
    # 3. Flag de Edição (Garante que a coluna existe no DF mesmo se nula no banco)
    if 'foi_editado' not in df_lancamentos.columns:
        df_lancamentos['foi_editado'] = False
    else:
        df_lancamentos['foi_editado'] = df_lancamentos['foi_editado'].fillna(False).astype(bool)

# ==============================================================================
# ABA 1: LANÇAMENTOS
# ==============================================================================
if selected_tab == "📝 Lançamentos":
    st.subheader(f"📝 Registro de Atividade - {current_user_name}")
    
    with st.expander("ℹ️ Guia de Preenchimento", expanded=False):
        st.markdown("""
        * **Data Real:** Dia da execução.
        * **Horas:** Use `.` para minutos (ex: 1.30 = 1h30min).
        * **Descrição:** Detalhe a entrega.
        """)
    
    with st.form("form_lancamento_main", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        input_projeto = c1.selectbox("Projeto", lista_projetos_ativos)
        input_tipo = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Gestão", "Design", "Apoio"])
        input_data = c3.date_input("Data REAL da Atividade", datetime.now())
        
        c4, c5 = st.columns([1, 2])
        input_horas = c4.number_input("Horas (HH.MM)", min_value=0.0, step=0.10, format="%.2f")
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
                                "id": str(uuid.uuid4()), "e": current_user_email, "p": input_projeto, 
                                "h": input_horas, "c": competencia_str, "d_atv": data_full_str, 
                                "t": input_tipo, "d": input_desc, "v": valor_hora_atual
                            }
                        )
                        s.commit()
                    st.toast(f"Salvo: {input_horas}h em {data_full_str}", icon="✅")
                    time.sleep(1.5); st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
            else:
                st.warning("Preencha horas e descrição.")

# ==============================================================================
# ABA NOVA: HISTÓRICO PESSOAL (EDIÇÃO DE PENDENTES)
# ==============================================================================
elif selected_tab == "🗂️ Histórico Pessoal":
    st.subheader(f"🗂️ Meus Registros - {current_user_name}")
    st.info("💡 Você pode editar lançamentos que ainda estão **Pendentes**. A edição notificará o administrador.")
    
    # Filtra dados apenas do usuário logado
    my_df = df_lancamentos[df_lancamentos['colaborador_email'] == current_user_email].copy()
    
    if not my_df.empty:
        tab_pend, tab_aprov, tab_neg = st.tabs(["⏳ Pendentes (Editável)", "✅ Aprovados", "❌ Negados"])
        
        # --- PENDENTES (EDITÁVEL) ---
        with tab_pend:
            my_pend = my_df[my_df['status_aprovaca'] == 'Pendente'].copy()
            if not my_pend.empty:
                # Editor de dados
                edited_my_pend = st.data_editor(
                    my_pend[['descricao', 'projeto', 'Data Real', 'horas', 'tipo', 'id']],
                    use_container_width=True, hide_index=True, key="user_edit_pend",
                    column_config={
                        "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "horas": st.column_config.NumberColumn("HH.MM", format="%.2f"),
                        "id": None # Oculta ID
                    }
                )
                
                if st.button("💾 Salvar Minhas Edições"):
                    count = 0
                    with conn.session as s:
                        for row in edited_my_pend.itertuples():
                            try:
                                # Converte data (pode vir como string do editor)
                                d_val = row.Data_Real if hasattr(row, 'Data_Real') else row._3
                                if isinstance(d_val, str): d_val = datetime.strptime(d_val, "%Y-%m-%d").date()
                                elif isinstance(d_val, pd.Timestamp): d_val = d_val.date()
                                
                                c_s = d_val.strftime("%Y-%m")
                                d_s = d_val.strftime("%Y-%m-%d")
                                
                                # Atualiza e seta flag 'foi_editado' para TRUE
                                s.execute(
                                    text("""
                                        UPDATE lancamentos 
                                        SET descricao=:d, projeto=:p, horas=:h, data_atividade=:da, competencia=:c, foi_editado=TRUE 
                                        WHERE id=:id
                                    """),
                                    {"d": row.descricao, "p": row.projeto, "h": row.horas, "da": d_s, "c": c_s, "id": row.id}
                                )
                                count += 1
                            except Exception as e: st.error(f"Erro linha {row.id}: {e}")
                        s.commit()
                    
                    if count > 0:
                        st.toast("Edições salvas! Admin notificado.", icon="⚠️")
                        time.sleep(1.5); st.rerun()
            else:
                st.info("Você não tem itens pendentes.")

        # --- APROVADOS (READ ONLY) ---
        with tab_aprov:
            st.dataframe(
                my_df[my_df['status_aprovaca'] == 'Aprovado'][['descricao', 'Data Real', 'horas', 'valor_hora_historico']],
                use_container_width=True, hide_index=True, column_config={"Data Real": st.column_config.DateColumn("Data")}
            )

        # --- NEGADOS (READ ONLY) ---
        with tab_neg:
            st.dataframe(
                my_df[my_df['status_aprovaca'] == 'Negado'][['descricao', 'Data Real', 'horas']],
                use_container_width=True, hide_index=True
            )
    else:
        st.info("Nenhum histórico encontrado.")

# ==============================================================================
# ABA 3: PAINEL GERENCIAL (ADMIN/USER)
# ==============================================================================
elif "Painel" in selected_tab or "Gestão" in selected_tab:
    st.subheader("📊 Painel Financeiro")
    
    target_email = current_user_email
    target_name = current_user_name
    
    if is_admin_session:
        c_sel, _ = st.columns([2, 2])
        # Lista sem o próprio admin (para não duplicar visualmente)
        others = [x for x in lista_colaboradores_visual if current_user_email not in x]
        lista_adm = [f"{current_user_name} ({current_user_email})"] + others
        
        sel_vis = c_sel.selectbox("👁️ (Admin) Visualizar:", lista_adm)
        target_email = sel_vis.split('(')[-1].replace(')', '')
        target_name = email_to_name_map.get(target_email, target_email)
    
    st.markdown(f"**Analisando:** `{target_name}`")
    
    # Filtro Competência
    if not df_lancamentos.empty:
        all_comps = sorted(df_lancamentos['competencia'].astype(str).unique(), reverse=True)
    else: all_comps = []
    
    c_f1, c_f2 = st.columns([1, 3])
    sel_comps = c_f1.multiselect("📅 Filtrar Competências:", all_comps, default=all_comps[:1] if all_comps else None)
    
    # Filtragem
    df_painel = df_lancamentos[df_lancamentos["colaborador_email"] == target_email].copy()
    
    if not df_painel.empty and sel_comps:
        df_painel = df_painel[df_painel['competencia'].isin(sel_comps)]
    
    if not df_painel.empty and sel_comps:
        df_painel['h_dec'] = df_painel['horas'].apply(convert_hhmm_to_decimal)
        df_painel['val_total'] = df_painel['h_dec'] * df_painel['valor_hora_historico']
        
        k1, k2, k3, k4 = st.columns(4)
        h_p = df_painel[df_painel['status_aprovaca'] == 'Pendente']['horas'].sum()
        h_a = df_painel[df_painel['status_aprovaca'] == 'Aprovado']['horas'].sum()
        h_pg = df_painel[df_painel['status_pagamento'] == 'Pago']['horas'].sum()
        vt = df_painel['val_total'].sum()
        
        k1.metric("Pendente", f"{h_p:.2f}h")
        k2.metric("Aprovado", f"{h_a:.2f}h")
        k3.metric("Pago", f"{h_pg:.2f}h")
        k4.metric("Valor Total", f"R$ {vt:,.2f}")
        
        st.divider()
        st.dataframe(
            df_painel[['descricao', 'Data Real', 'competencia', 'projeto', 'horas', 'val_total', 'status_aprovaca', 'status_pagamento']],
            use_container_width=True, hide_index=True,
            column_config={
                "val_total": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
            }
        )
    else:
        st.warning("Selecione uma competência.")

# ==============================================================================
# ABA 4: ADMIN APROVAÇÕES
# ==============================================================================
elif selected_tab == "🛡️ Admin Aprovações":
    st.subheader("🛡️ Central de Gestão Operacional")
    
    # --- BULK IMPORT ---
    with st.expander("📥 Importação em Massa (Excel)", expanded=False):
        cola = st.text_area("Data | Projeto | Email | Horas | Tipo | Desc", height=100)
        if cola and st.button("Gravar Massa"):
            try:
                df_p = pd.read_csv(io.StringIO(cola), sep='\t', names=["data", "p", "e", "h", "t", "d"])
                with conn.session as s:
                    for r in df_p.itertuples():
                        v = auth_db.get(r.e, {}).get("valor_hora", 0)
                        try:
                            dt = pd.to_datetime(r.data, dayfirst=True)
                            c_s, d_s = dt.strftime("%Y-%m"), dt.strftime("%Y-%m-%d")
                        except:
                            now = datetime.now()
                            c_s, d_s = now.strftime("%Y-%m"), now.strftime("%Y-%m-%d")
                        
                        s.execute(
                            text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, data_atividade, tipo, descricao, valor_hora_historico, status_aprovaca, foi_editado) VALUES (:id, :e, :p, :h, :c, :d_atv, :t, :d, :v, 'Pendente', FALSE)"),
                            {"id": str(uuid.uuid4()), "e": r.e, "p": r.p, "h": r.h, "c": c_s, "d_atv": d_s, "t": r.t, "d": r.d, "v": v}
                        )
                    s.commit()
                st.success("Importado!"); time.sleep(1); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

    st.divider()
    
    # --- PENDENTES ---
    st.markdown("### 🕒 Fila de Pendentes")
    
    c_chk, c_fil = st.columns([1, 3])
    sel_all = c_chk.checkbox("Selecionar Todos")
    lista_f = ["Todos"] + lista_colaboradores_visual
    f_p = c_fil.selectbox("Filtrar:", lista_f, key="fp_adm")
    
    df_p = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Pendente'].copy()
    if f_p != "Todos":
        e_p = f_p.split('(')[-1].replace(')', '')
        df_p = df_p[df_p['colaborador_email'] == e_p]
        
    if not df_p.empty:
        df_p = df_p[['foi_editado', 'descricao', 'Nome', 'projeto', 'Data Real', 'horas', 'id']]
        df_p.insert(0, "✅", sel_all)
        df_p.insert(1, "🗑️", False)
        
        ed_p = st.data_editor(
            df_p, use_container_width=True, hide_index=True, key="adm_pend",
            column_config={
                "✅": st.column_config.CheckboxColumn("Apv", width="small"),
                "🗑️": st.column_config.CheckboxColumn("Rej", width="small"),
                "foi_editado": st.column_config.CheckboxColumn("⚠️ Editado?", disabled=True, help="Usuário alterou este item."),
                "Data Real": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
            }
        )
        
        c1, c2 = st.columns(2)
        if c1.button("Aprovar Selecionados"):
            ids = ed_p[ed_p["✅"] == True]["id"].tolist()
            if ids:
                with conn.session as s:
                    s.execute(text("UPDATE lancamentos SET status_aprovaca='Aprovado', foi_editado=FALSE WHERE id IN :ids"), {"ids": tuple(ids)})
                    s.commit()
                st.toast("Aprovado!"); time.sleep(0.5); st.rerun()
        if c2.button("Rejeitar Selecionados"):
            ids = ed_p[ed_p["🗑️"] == True]["id"].tolist()
            if ids:
                with conn.session as s:
                    s.execute(text("UPDATE lancamentos SET status_aprovaca='Negado' WHERE id IN :ids"), {"ids": tuple(ids)})
                    s.commit()
                st.toast("Rejeitado!"); time.sleep(0.5); st.rerun()
    else:
        st.info("Nada pendente.")

    st.divider()
    
    # --- APROVADOS (SYNC DATA) ---
    st.markdown("### ✅ Histórico de Aprovados")
    f_a = st.selectbox("Filtrar Aprovados:", lista_f, key="fa_adm")
    
    df_a = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Aprovado'].copy()
    if f_a != "Todos":
        e_a = f_a.split('(')[-1].replace(')', '')
        df_a = df_a[df_a['colaborador_email'] == e_a]
        
    if not df_a.empty:
        df_a = df_a[['descricao', 'Nome', 'projeto', 'competencia', 'Data Real', 'horas', 'status_aprovaca', 'id']]
        
        ed_a = st.data_editor(
            df_a, use_container_width=True, hide_index=True, key="adm_aprov",
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Aprovado", "Pendente", "Negado"], required=True),
                "Data Real": st.column_config.DateColumn("Data Ativ.", format="DD/MM/YYYY"),
                "competencia": st.column_config.TextColumn("Comp. (Auto)")
            }
        )
        if st.button("Salvar Edições"):
            count = 0
            with conn.session as s:
                for r in ed_a.itertuples():
                    try:
                        # Sync Data -> Competencia
                        d_val = getattr(r, "Data_Real")
                        if isinstance(d_val, str): d_obj = datetime.strptime(d_val, "%Y-%m-%d").date()
                        elif isinstance(d_val, pd.Timestamp): d_obj = d_val.date()
                        else: d_obj = d_val
                        
                        c_s, d_s = d_obj.strftime("%Y-%m"), d_obj.strftime("%Y-%m-%d")
                        
                        s.execute(
                            text("UPDATE lancamentos SET status_aprovaca=:s, horas=:h, descricao=:d, projeto=:p, competencia=:c, data_atividade=:da WHERE id=:id"),
                            {"s": r.status_aprovaca, "h": r.horas, "d": r.descricao, "p": r.projeto, "c": c_s, "da": d_s, "id": r.id}
                        )
                        count += 1
                    except: pass
                s.commit()
            st.success(f"{count} atualizados!"); time.sleep(1); st.rerun()

    # --- REJEITADOS ---
    st.divider()
    with st.expander("❌ Lixeira / Rejeitados"):
        df_n = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Negado'].copy()
        if not df_n.empty:
            df_n = df_n[['descricao', 'Nome', 'Data Real', 'status_aprovaca', 'id']]
            ed_n = st.data_editor(df_n, use_container_width=True, hide_index=True, column_config={"status_aprovaca": st.column_config.SelectboxColumn("Ação", options=["Negado", "Pendente"])})
            if st.button("Recuperar"):
                with conn.session as s:
                    for r in ed_n.itertuples():
                        if r.status_aprovaca != "Negado":
                            s.execute(text("UPDATE lancamentos SET status_aprovaca=:s WHERE id=:id"), {"s": r.status_aprovaca, "id": r.id})
                    s.commit()
                st.rerun()

# ==============================================================================
# ABA 5: PAGAMENTOS
# ==============================================================================
elif selected_tab == "💸 Pagamentos":
    st.subheader("💸 Consolidação Financeira")
    
    df_pay = df_lancamentos[df_lancamentos['status_aprovaca'] == 'Aprovado'].copy()
    if not df_pay.empty:
        df_pay['h_dec'] = df_pay['horas'].apply(convert_hhmm_to_decimal)
        df_pay['r$'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
        
        df_g = df_pay.groupby(['competencia', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        df_g = df_g.sort_values(['competencia'], ascending=False)
        
        tot = df_pay[df_pay['status_pagamento'] != 'Pago']['r$'].sum()
        st.metric("Total Pendente", f"R$ {tot:,.2f}")
        
        for idx, row in df_g.iterrows():
            nm = email_to_name_map.get(row['colaborador_email'], row['colaborador_email'])
            with st.expander(f"📅 {row['competencia']} | 👤 {nm} | R$ {row['r$']:,.2f}"):
                det = df_pay[(df_pay['competencia'] == row['competencia']) & (df_pay['colaborador_email'] == row['colaborador_email'])]
                
                st.dataframe(det[['descricao', 'Data Real', 'horas', 'r$', 'status_pagamento']], use_container_width=True, hide_index=True,
                             column_config={"r$": st.column_config.NumberColumn("Valor", format="R$ %.2f")})
                
                s_at = det['status_pagamento'].iloc[0]
                ops = ["Em aberto", "Pago", "Parcial"]
                ix = ops.index(s_at) if s_at in ops else 0
                
                c1, c2 = st.columns([3, 1])
                ns = c1.selectbox("Status", ops, index=ix, key=f"p_{idx}")
                if c2.button("Atualizar", key=f"b_{idx}"):
                    with conn.session as s:
                        ids = tuple(det['id'].tolist())
                        s.execute(text("UPDATE lancamentos SET status_pagamento=:s WHERE id IN :ids"), {"s": ns, "ids": ids})
                        s.commit()
                    st.toast("Pago!"); time.sleep(0.5); st.rerun()
    else: st.info("Vazio.")

# ==============================================================================
# ABA 6: BI
# ==============================================================================
elif selected_tab == "📈 BI Estratégico":
    st.subheader("📈 BI Humana")
    
    comps = sorted(df_lancamentos['competencia'].astype(str).unique(), reverse=True) if not df_lancamentos.empty else []
    sel_bi = st.multiselect("Competências:", comps, default=comps[:2] if comps else None)
    
    df_bi = df_lancamentos.copy()
    if sel_bi and not df_bi.empty:
        df_bi = df_bi[df_bi['competencia'].isin(sel_bi)]
        df_bi['tipo_norm'] = df_bi['tipo'].apply(normalize_text_fields)
        df_bi['h_dec'] = df_bi['horas'].apply(convert_hhmm_to_decimal)
        df_bi["custo"] = df_bi['h_dec'] * df_bi["valor_hora_historico"]
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Horas", f"{df_bi['horas'].sum():.2f}")
        m2.metric("Custo", f"R$ {df_bi['custo'].sum():,.2f}")
        m3.metric("Pago", f"R$ {df_bi[df_bi['status_pagamento']=='Pago']['custo'].sum():,.2f}")
        m4.metric("Registros", len(df_bi))
        
        c1, c2 = st.columns(2)
        with c1: st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        with c2: st.bar_chart(df_bi.groupby("tipo_norm")["horas"].sum())
        
        st.write("**Ranking (Por Nome)**")
        r = df_bi.groupby("Nome").agg({'horas': 'sum', 'custo': 'sum'}).sort_values('horas', ascending=False)
        st.dataframe(r, use_container_width=True, column_config={"custo": st.column_config.NumberColumn("R$", format="%.2f")})
    else: st.info("Selecione competência.")

# ==============================================================================
# ABA 7: CONFIGURAÇÕES
# ==============================================================================
elif selected_tab == "⚙️ Configurações":
    st.subheader("⚙️ Configurações")
    
    st.write("👥 **Usuários**")
    # TYPE=PASSWORD REMOVIDO PARA EVITAR ERRO DO STREAMLIT NOVO
    ed_u = st.data_editor(
        df_u_login, num_rows="dynamic", hide_index=True, 
        column_config={
            "email": st.column_config.TextColumn("Login", disabled=True),
            "nome": st.column_config.TextColumn("Nome Exibição"),
            "senha": st.column_config.TextColumn("Senha (Texto)"),
            "is_admin": st.column_config.CheckboxColumn("Admin"),
            "valor_hora": st.column_config.NumberColumn("Valor")
        }
    )
    if st.button("Salvar Usuários"):
        with conn.session as s:
            for r in ed_u.itertuples():
                nm = getattr(r, 'nome', r.email.split('@')[0])
                s.execute(text("INSERT INTO usuarios (email, valor_hora, senha, is_admin, nome) VALUES (:e, :v, :s, :a, :n) ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a, nome=:n"), 
                          {"e": r.email, "v": r.valor_hora, "s": str(r.senha), "a": bool(r.is_admin), "n": nm})
            s.commit()
        st.success("Salvo!"); st.rerun()
        
    st.divider(); st.write("📁 **Projetos**")
    ed_p = st.data_editor(df_projetos, num_rows="dynamic", hide_index=True)
    if st.button("Salvar Projetos"):
        with conn.session as s:
            for r in ed_p.itertuples():
                if r.nome: s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
            s.commit()
        st.success("Salvo!"); st.rerun()

    st.divider(); st.write("🏦 **Bancos**")
    ed_b = st.data_editor(df_bancos, num_rows="dynamic", hide_index=True, column_config={"tipo_chave": st.column_config.SelectboxColumn("Tipo", options=["CPF", "CNPJ", "Email"])})
    if st.button("Salvar Bancos"):
        with conn.session as s:
            for r in ed_b.itertuples():
                s.execute(text("INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) VALUES (:e, :b, :t, :c) ON CONFLICT (colaborador_email) DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c"), 
                          {"e": r.colaborador_email, "b": r.banco, "t": getattr(r, 'tipo_chave', 'CPF'), "c": r.chave_pix})
            s.commit()
        st.success("Salvo!"); st.rerun()

st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>OnCall Humana | v12.0 Final Stable</p>", unsafe_allow_html=True)