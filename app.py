import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="OnCall Management", layout="wide")

try:
    user_email = st.user.email
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
conn = st.connection("gsheets", type=GSheetsConnection)

# CARREGAR CONFIG
try:
    df_config = conn.read(worksheet="config", ttl=0)
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])

lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos: lista_projetos = ["Sistema de horas"]

if user_email not in ADMINS and user_email not in df_config["emails_autorizados"].values:
    st.error(f"Acesso negado para {user_email}.")
    st.stop()

abas = st.tabs(["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"]) if user_email in ADMINS else st.tabs(["🚀 Lançar Horas"])

with abas[0]:
    st.header("Novo Lançamento")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        proj = col1.selectbox("Selecione o Projeto", lista_projetos)
        qtd_horas = col2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        desc = st.text_area("O que você desenvolveu?")
        
        if st.form_submit_button("Enviar Lançamento"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": float(qtd_horas),
                "descricao": str(desc),
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            
            try:
                # Lógica robusta de salvamento
                df_atual = conn.read(worksheet="lancamentos", ttl=0).dropna(how="all")
                df_final = pd.concat([df_atual, novo], ignore_index=True).astype(str)
                conn.update(worksheet="lancamentos", data=df_final)
                st.success("Lançamento enviado com sucesso! ✅")
                st.balloons()
            except Exception as e:
                st.error(f"Erro ao salvar. Verifique se o e-mail {conn._service_account_info['client_email']} é EDITOR da planilha.")
                st.write(f"Detalhe técnico: {e}")

if user_email in ADMINS:
    with abas[3]:
        st.header("Configurações")
        df_edit = st.data_editor(df_config, num_rows="dynamic")
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=df_edit.astype(str))
            st.success("Salvo!")