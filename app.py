import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão OnCall", layout="wide", page_icon="💸")

# --- 1. CONEXÃO SIMPLIFICADA ---
# Removemos toda a "vacina" manual. O Streamlit vai ler direto dos Secrets (que já estão certos).
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- 2. CARREGAMENTO DE DADOS ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
except Exception:
    # Se der erro (tabelas vazias ou não existem), cria DataFrames vazios
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "colaborador_email", "projeto", "horas", "descricao", "status_aprovaca", "data_decisao"])

# --- 3. VARIÁVEIS GLOBAIS ---
try:
    user_email = st.user.email
    if user_email is None: raise Exception()
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# Listas
lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos: lista_projetos = ["Sistema de horas", "Consultoria", "Suporte"]

try:
    valor_hora_padrao = float(df_config["valor_hora"].dropna().iloc[0])
except:
    valor_hora_padrao = 100.0

# --- 4. VERIFICAÇÃO DE ACESSO ---
if user_email not in ADMINS and user_email not in df_config["emails_autorizados"].values:
    st.error(f"🔒 Acesso negado para {user_email}.")
    st.stop()

# --- 5. INTERFACE ---
st.title("🚀 Gestão OnCall")

# Define abas
if user_email in ADMINS:
    abas = st.tabs(["📝 Lançar", "🛡️ Aprovação", "📊 Dashboard", "⚙️ Config"])
else:
    abas = st.tabs(["📝 Lançar"])

# === ABA 1: LANÇAR ===
with abas[0]:
    st.caption(f"Logado como: {user_email}")
    with st.form("form_lan", clear_on_submit=True):
        c1, c2 = st.columns(2)
        proj = c1.selectbox("Projeto", lista_projetos)
        hor = c2.number_input("Horas", min_value=0.5, step=0.5, format="%.1f")
        desc = st.text_area("Descrição da atividade")
        
        if st.form_submit_button("Enviar Registro"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": hor,
                "descricao": desc,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            final = pd.concat([df_lancamentos, novo], ignore_index=True).astype(str)
            conn.update(worksheet="lancamentos", data=final)
            st.success("Sucesso! Registro enviado.")
            st.rerun()

# === ABA 2, 3, 4 (ADMINS) ===
if user_email in ADMINS:
    
    # APROVAÇÃO
    with abas[1]:
        st.subheader("Central de Aprovação")
        pendentes = df_lancamentos[df_lancamentos["status_aprovaca"] == "Pendente"].copy()
        
        if pendentes.empty:
            st.info("Nenhuma pendência.")
        else:
            edited = st.data_editor(
                pendentes,
                column_config={
                    "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Rejeitado"], required=True)
                },
                disabled=["id", "projeto", "descricao", "horas", "colaborador_email"],
                hide_index=True
            )
            
            if st.button("Salvar Status"):
                for i, row in edited.iterrows():
                    if row["status_aprovaca"] != "Pendente":
                        idx = df_lancamentos[df_lancamentos["id"] == row["id"]].index
                        if not idx.empty:
                            df_lancamentos.at[idx[0], "status_aprovaca"] = row["status_aprovaca"]
                            df_lancamentos.at[idx[0], "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
                conn.update(worksheet="lancamentos", data=df_lancamentos.astype(str))
                st.success("Atualizado!")
                st.rerun()
    
    # DASHBOARD
    with abas[2]:
        st.subheader("Performance Financeira")
        # Tratamento de dados para evitar erro no gráfico
        df_dash = df_lancamentos.copy()
        df_dash["horas"] = pd.to_numeric(df_dash["horas"], errors="coerce").fillna(0)
        
        aprovados = df_dash[df_dash["status_aprovaca"] == "Aprovado"]
        total = aprovados["horas"].sum()
        
        k1, k2 = st.columns(2)
        k1.metric("Horas Aprovadas", f"{total}h")
        k2.metric("Faturamento Estimado", f"R$ {total * valor_hora_padrao:,.2f}")
        
        if not aprovados.empty:
            st.bar_chart(aprovados.groupby("projeto")["horas"].sum())
        else:
            st.info("Aprove horas para ver os gráficos.")

    # CONFIGURAÇÃO
    with abas[3]:
        st.subheader("Configurações")
        conf_edit = st.data_editor(df_config, num_rows="dynamic")
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=conf_edit.astype(str))
            st.success("Salvo!")