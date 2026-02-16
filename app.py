import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão de Horas - OnCall", layout="wide")

# Autenticação (Ajustado para o seu e-mail correto)
try:
    user_email = st.user.email
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
conn = st.connection("gsheets", type=GSheetsConnection)

# --- CARREGAR CONFIGURAÇÕES ---
try:
    df_config = conn.read(worksheet="config")
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])

# LISTA GLOBAL DE PROJETOS (Coluna A da aba config)
lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos:
    lista_projetos = ["Sistema de horas"] # Backup caso a lista esteja vazia

# LISTA DE USUÁRIOS AUTORIZADOS (Coluna B da aba config)
lista_autorizados = df_config["emails_autorizados"].dropna().unique().tolist()

# Bloqueio de Segurança
if user_email not in ADMINS and user_email not in lista_autorizados:
    st.error(f"Acesso negado para {user_email}. Solicite autorização.")
    st.stop()

# Navegação (Abas de Admin aparecem se você estiver em ADMINS)
if user_email in ADMINS:
    abas = st.tabs(["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"])
else:
    abas = st.tabs(["🚀 Lançar Horas"])

# --- ABA 1: LANÇAMENTO (Aparece para todos os autorizados) ---
with abas[0]:
    st.header("Novo Lançamento de Horas")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        # Qualquer usuário pode escolher qualquer projeto da lista global
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
            df_atual = conn.read(worksheet="lancamentos")
            conn.update(worksheet="lancamentos", data=pd.concat([df_atual, novo_reg], ignore_index=True))
            st.success("Lançamento enviado! ✅")

# --- ABA 4: CONFIGURAÇÕES (Apenas Admins) ---
if user_email in ADMINS:
    with abas[3]:
        st.header("Painel de Controle")
        st.write("Abaixo, a Clau define os projetos globais e os valores/hora individuais.")
        df_config_edit = st.data_editor(df_config, num_rows="dynamic", use_container_width=True)
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=df_config_edit)
            st.success("Configurações salvas!")
            st.rerun()