import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão OnCall", layout="wide")

# Fallback para o seu e-mail
try:
    user_email = st.user.email
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# Conexão com tratamento de erro
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Erro Crítico de Conexão. Verifique os Secrets.")
    st.stop()

# Carregamento de Configurações
try:
    df_config = conn.read(worksheet="config", ttl=0)
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])

lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos:
    lista_projetos = ["Sistema de horas"]

# Trava de segurança
if user_email not in ADMINS and user_email not in df_config["emails_autorizados"].values:
    st.warning(f"Acesso restrito para {user_email}.")
    st.stop()

# Menu
abas = st.tabs(["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"]) if user_email in ADMINS else st.tabs(["🚀 Lançar Horas"])

with abas[0]:
    st.header("Novo Lançamento")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        proj = col1.selectbox("Projeto", lista_projetos)
        horas = col2.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("O que você desenvolveu?")
        
        if st.form_submit_button("Enviar"):
            novo_reg = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "colaborador_email": user_email,
                "projeto": proj,
                "horas": float(horas),
                "descricao": str(desc),
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            
            try:
                df_atual = conn.read(worksheet="lancamentos", ttl=0).dropna(how="all")
                df_final = pd.concat([df_atual, novo_reg], ignore_index=True).astype(str)
                conn.update(worksheet="lancamentos", data=df_final)
                st.success("Lançamento enviado! ✅")
            except Exception as e:
                st.error("Erro ao salvar. Verifique se o app é EDITOR na planilha.")
                st.exception(e)