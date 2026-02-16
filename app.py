import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão de Horas", layout="wide")

try:
    user_email = st.user.email
except:
    user_email = "pedroivofernandesreis@gmail.com"

# ADMs oficiais
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

conn = st.connection("gsheets", type=GSheetsConnection)

# --- CARREGAR CONFIGURAÇÕES ---
try:
    df_config = conn.read(worksheet="config")
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])

lista_projetos = df_config["projetos"].dropna().unique().tolist()
lista_autorizados = df_config["emails_autorizados"].dropna().unique().tolist()

# Bloqueio de segurança
if user_email not in ADMINS and user_email not in lista_autorizados:
    st.error(f"Acesso negado para {user_email}. Fale com a Clau.")
    st.stop()

# Definição das Abas
if user_email in ADMINS:
    abas = st.tabs(["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"])
else:
    abas = st.tabs(["🚀 Lançar Horas"])

with abas[0]:
    st.header("Novo Lançamento")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        projeto = col1.selectbox("Projeto", lista_projetos if lista_projetos else ["Padrão"])
        horas = col2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        descricao = st.text_area("O que você desenvolveu?")
        if st.form_submit_button("Enviar Lançamento"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "colaborador_email": user_email,
                "projeto": projeto,
                "horas": horas,
                "descricao": descricao,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            df_atual = conn.read(worksheet="lancamentos")
            conn.update(worksheet="lancamentos", data=pd.concat([df_atual, novo], ignore_index=True))
            st.success("Enviado! ✅")

if user_email in ADMINS:
    with abas[3]:
        st.header("Configurações")
        df_edit = st.data_editor(df_config, num_rows="dynamic", use_container_width=True)
        if st.button("Salvar Tudo"):
            conn.update(worksheet="config", data=df_edit)
            st.success("Salvo! ⚙️")
            st.rerun()
    # As outras abas (Painel e BI) seguem a mesma lógica de leitura/escrita