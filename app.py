import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão OnCall", layout="wide")

# Identificação do usuário
try:
    user_email = st.user.email
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# Tenta conectar (Se o erro PEM sumir, o app abre aqui)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Erro Crítico de Conexão. Verifique os Secrets.")
    st.stop()

# Carregar Dados das Abas
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
except Exception:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "colaborador_email", "projeto", "horas", "descricao", "status_aprovaca", "data_decisao"])

# Listas globais
lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos: lista_projetos = ["Sistema de horas"]

# Verificação de Acesso
if user_email not in ADMINS and user_email not in df_config["emails_autorizados"].values:
    st.warning(f"Acesso restrito para {user_email}. Fale com a Clau.")
    st.stop()

# Navegação
tabs = ["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"] if user_email in ADMINS else ["🚀 Lançar Horas"]
abas = st.tabs(tabs)

with abas[0]:
    st.header("Novo Lançamento")
    with st.form("form_novo", clear_on_submit=True):
        col1, col2 = st.columns(2)
        p_sel = col1.selectbox("Selecione o Projeto", lista_projetos)
        h_sel = col2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        d_sel = st.text_area("O que você desenvolveu?")
        
        if st.form_submit_button("Enviar para Aprovação"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "colaborador_email": user_email,
                "projeto": p_sel,
                "horas": h_sel,
                "descricao": d_sel,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            # Concatena e salva
            df_final = pd.concat([df_lancamentos, novo], ignore_index=True).astype(str)
            conn.update(worksheet="lancamentos", data=df_final)
            st.success("Lançamento enviado! ✅")

if user_email in ADMINS:
    with abas[3]:
        st.header("Configurações do Sistema")
        st.info("Aqui você define Projetos Globais e Colaboradores Autorizados.")
        df_edit = st.data_editor(df_config, num_rows="dynamic")
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=df_edit.astype(str))
            st.success("Salvo com sucesso!")