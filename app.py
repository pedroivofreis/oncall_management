import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# Nome do projeto conforme solicitado
st.set_page_config(page_title="Oncall Management - v6.8 (by Pedro Reis)", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- 2. CARREGAMENTO E AJUSTE DE COLUNAS (CRUCIAL) ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
    
    # ORDEM EXATA CONFORME SUA PLANILHA (image_974b88)
    # A=id, B=data_registro, C=colaborador_email, D=projeto, E=horas, F=descricão, G=status_aprovaca...
    colunas_reais = [
        "id", "data_registro", "colaborador_email", "projeto", 
        "horas", "descricão", "status_aprovaca", "data_decisao", 
        "competencia", "tipo"
    ]
    
    # Filtra apenas colunas que existem para evitar erro de reindexação
    df_lancamentos = df_lancamentos[[c for c in colunas_reais if c in df_lancamentos.columns]]
    
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# --- 3. CONFIGURAÇÕES & USUÁRIOS ---
try:
    raw_p = df_config["projetos"].dropna().unique().tolist()
    lista_projetos = [str(x).strip() for x in raw_p if str(x).strip() not in ["", "nan", "None"]]
    if not lista_projetos: lista_projetos = ["Sistema de horas"]

    # Mapeamento de Valor Hora (P1)
    df_u = df_config[["emails_autorizados", "valor_hora"]].copy()
    df_u["valor_hora"] = pd.to_numeric(df_u["valor_hora"], errors="coerce").fillna(0.0)
    
    dict_valores = {}
    lista_emails = []
    for _, row in df_u.iterrows():
        email = str(row["emails_autorizados"]).strip()
        if "@" in email:
            lista_emails.append(email)
            dict_valores[email] = float(row["valor_hora"])

    ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
except Exception:
    st.error("Erro ao processar configurações.")
    st.stop()

# --- 4. LOGIN SEGURO (SENHA: Humana1002*) ---
st.sidebar.title("🔐 Acesso")
email_detectado = None
try:
    if hasattr(st, "context"): email_detectado = st.context.user.email
    elif hasattr(st, "user"): email_detectado = st.user.get("email")
except: email_detectado = None

user_email = None
autenticado = False

if email_detectado:
    user_email = email_detectado
    autenticado = True
else:
    user_email = st.sidebar.selectbox("Identifique-se:", options=["Selecione..."] + sorted(lista_emails))
    if user_email != "Selecione...":
        if user_email in ADMINS:
            senha = st.sidebar.text_input("Senha Admin", type="password")
            if senha == "Humana1002*": autenticado = True
            elif senha: st.sidebar.error("Senha incorreta!")
        else: autenticado = True

if not autenticado:
    st.info("👈 Identifique-se na lateral para continuar.")
    st.stop()

# --- 5. INTERFACE ---
st.title("Oncall Management - v6.8 (by Pedro Reis)")
abas_lista = ["📝 Lançar", "🛡️ Painel da Clau", "📊 BI & Financeiro", "⚙️ Configurações"] if user_email in ADMINS else ["📝 Lançar"]
abas = st.tabs(abas_lista)

# === ABA 1: LANÇAR ===
with abas[0]:
    st.markdown(f"**Olá, {user_email.split('@')[0]}!** 👋")
    with st.form("novo_lan", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        proj = col1.selectbox("Projeto", lista_projetos)
        tipo_ativ = col2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Testes", "Reunião", "Outros"])
        data_f = col3.date_input("Data da Atividade", value=datetime.now())
        
        c4, c5 = st.columns([1, 2])
        hrs = c4.number_input("Horas", min_value=0.5, step=0.5)
        # Note que o nome da coluna no CSV/Sheet deve ser exatamente 'descricão' para bater com seu layout
        desc = c5.text_area("Descrição detalhada")
        
        if st.form_submit_button("Enviar para Aprovação"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": data_f.strftime("%Y-%m-%d") + " " + datetime.now().strftime("%H:%M:%S"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": hrs,
                "descricão": desc, # Bate com a planilha (F)
                "status_aprovaca": "Pendente", # Bate com a planilha (G)
                "data_decisao": "",
                "competencia": data_f.strftime("%Y-%m"),
                "tipo": tipo_ativ
            }])
            # Envia respeitando a ordem das colunas para disparar o e-mail corretamente no Apps Script
            df_final = pd.concat([df_lancamentos, novo], ignore_index=True).astype(str)
            conn.update(worksheet="lancamentos", data=df_final)
            st.success("Enviado com sucesso! A Clau receberá a notificação por e-mail. 📧")
            time.sleep(1)
            st.rerun()

# === ÁREA ADMIN ===
if user_email in ADMINS:
    with abas[1]:
        st.subheader("🛡️ Painel de Aprovação")
        df_edit = st.data_editor(
            df_lancamentos,
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Rejeitado"]),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Testes", "Reunião", "Outros"]),
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos)
            },
            disabled=["id", "colaborador_email", "data_registro"], hide_index=True
        )
        if st.button("Salvar Decisões"):
            # Atualiza data_decisao para os que mudaram de Pendente
            for i, row in df_edit.iterrows():
                if row["status_aprovaca"] != "Pendente" and not row["data_decisao"]:
                    df_edit.at[i, "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
            conn.update(worksheet="lancamentos", data=df_edit.astype(str))
            st.success("Status atualizados!"); st.rerun()

    with abas[2]:
        st.subheader("📊 BI & Financeiro")
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * df_bi["colaborador_email"].map(dict_valores).fillna(0)
        
        apr = df_bi[df_bi["status_aprovaca"] == "Aprovado"]
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🏗️ Custo por Projeto")
            st.bar_chart(apr.groupby("projeto")["custo"].sum(), color="#2e7d32")
        with c2:
            st.markdown("### 🛠️ Horas por Tipo")
            st.bar_chart(apr.groupby("tipo")["horas"].sum())

    with abas[3]:
        st.subheader("⚙️ Configurações")
        st.data_editor(df_config, num_rows="dynamic", key="config_edit")
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=st.session_state.config_edit.astype(str))
            st.success("Configurações salvas!"); st.rerun()