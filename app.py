import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão de Horas - OnCall", layout="wide")

# Autenticação (Ajustado para o seu e-mail)
try:
    user_email = st.user.email
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
conn = st.connection("gsheets", type=GSheetsConnection)

# --- CARREGAR CONFIGURAÇÕES ---
try:
    df_config = conn.read(worksheet="config")
except Exception:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])

# LISTA GLOBAL DE PROJETOS (Coluna A)
lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos:
    lista_projetos = ["Sistema de hora"] # Nome que você definiu na planilha

# LISTA DE USUÁRIOS AUTORIZADOS (Coluna B)
lista_autorizados = df_config["emails_autorizados"].dropna().unique().tolist()

# Bloqueio de Segurança
if user_email not in ADMINS and user_email not in lista_autorizados:
    st.error(f"Acesso negado para {user_email}. Peça autorização à gestora.")
    st.stop()

# Abas conforme o acesso
if user_email in ADMINS:
    abas = st.tabs(["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"])
else:
    abas = st.tabs(["🚀 Lançar Horas"])

# --- ABA 1: LANÇAMENTO (Qualquer autorizado escolhe qualquer projeto) ---
with abas[0]:
    st.header("Novo Lançamento de Horas")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        projeto_sel = col1.selectbox("Selecione o Projeto", lista_projetos)
        horas_val = col2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        desc_val = st.text_area("O que você desenvolveu?")
        
        if st.form_submit_button("Enviar para Aprovação"):
            novo_reg = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "colaborador_email": user_email,
                "projeto": projeto_sel,
                "horas": horas_val,
                "descricao": desc_val,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            
            try:
                df_atual = conn.read(worksheet="lancamentos")
            except Exception:
                df_atual = pd.DataFrame(columns=["id", "data_registro", "colaborador_email", "projeto", "horas", "descricao", "status_aprovaca", "data_decisao"])
            
            conn.update(worksheet="lancamentos", data=pd.concat([df_atual, novo_reg], ignore_index=True))
            st.success("Lançamento enviado! ✅")

# --- CONTEÚDO ADMIN ---
if user_email in ADMINS:
    with abas[3]:
        st.header("Configurações do Sistema")
        st.write("Defina projetos globais e autorize colaboradores aqui.")
        df_config_edit = st.data_editor(df_config, num_rows="dynamic", use_container_width=True)
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=df_config_edit)
            st.success("Configurações salvas!")
            st.rerun()