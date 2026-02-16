import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão OnCall", layout="wide")

# Identificação do usuário logado
try:
    user_email = st.user.email
except:
    user_email = "pedroivofernandesreis@gmail.com"

# Administradores
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# Tenta estabelecer a conexão
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Erro na conexão com o Google Sheets. Verifique seus Secrets.")
    st.stop()

# --- CARREGAR DADOS ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])

try:
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
except:
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "colaborador_email", "projeto", "horas", "descricao", "status_aprovaca", "data_decisao"])

# Listas globais
lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos: lista_projetos = ["Sistema de horas"]

# Trava de segurança básica
if user_email not in ADMINS and user_email not in df_config["emails_autorizados"].values:
    st.warning(f"Acesso restrito para {user_email}. Contate o administrador.")
    st.stop()

# Menu de Abas
abas_labels = ["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"] if user_email in ADMINS else ["🚀 Lançar Horas"]
abas = st.tabs(abas_labels)

with abas[0]:
    st.header("Lançamento de Horas")
    with st.form("form_novo", clear_on_submit=True):
        col1, col2 = st.columns(2)
        proj_sel = col1.selectbox("Projeto", lista_projetos)
        horas_sel = col2.number_input("Horas", min_value=0.5, step=0.5)
        desc_sel = st.text_area("O que você desenvolveu?")
        
        if st.form_submit_button("Enviar"):
            novo_dado = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "colaborador_email": user_email,
                "projeto": proj_sel,
                "horas": horas_sel,
                "descricao": desc_sel,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            df_final = pd.concat([df_lancamentos, novo_dado], ignore_index=True).astype(str)
            conn.update(worksheet="lancamentos", data=df_final)
            st.success("Enviado com sucesso! ✅")

if user_email in ADMINS:
    with abas[3]:
        st.header("Configurações do Sistema")
        df_conf_edit = st.data_editor(df_config, num_rows="dynamic")
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=df_conf_edit.astype(str))
            st.success("Configurações atualizadas!")