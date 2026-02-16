import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão de Horas - OnCall", layout="wide")

# Autenticação
try:
    user_email = st.user.email
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
conn = st.connection("gsheets", type=GSheetsConnection)

# --- CARREGAR CONFIGURAÇÕES ---
try:
    df_config = conn.read(worksheet="config", ttl=0) # ttl=0 força ler dado novo
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])

# Projetos Globais (Coluna A) e Usuários (Coluna B)
lista_projetos = df_config["projetos"].dropna().unique().tolist()
if not lista_projetos:
    lista_projetos = ["Sistema de horas"]

lista_autorizados = df_config["emails_autorizados"].dropna().unique().tolist()

# Trava de Segurança
if user_email not in ADMINS and user_email not in lista_autorizados:
    st.error(f"Acesso negado para {user_email}. Peça autorização à gestora.")
    st.stop()

# Abas de navegação
tabs = ["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI", "⚙️ Configurações"] if user_email in ADMINS else ["🚀 Lançar Horas"]
abas = st.tabs(tabs)

with abas[0]:
    st.header("Novo Lançamento")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        projeto = col1.selectbox("Projeto", lista_projetos)
        horas = col2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        descricao = st.text_area("O que você desenvolveu?")
        
        if st.form_submit_button("Enviar Lançamento"):
            novo_reg = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "colaborador_email": user_email,
                "projeto": projeto,
                "horas": horas,
                "descricao": descricao,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            
            try:
                # Tenta ler e anexar o novo dado
                df_atual = conn.read(worksheet="lancamentos", ttl=0)
                df_final = pd.concat([df_atual, novo_reg], ignore_index=True)
                conn.update(worksheet="lancamentos", data=df_final)
                st.success("Enviado com sucesso! ✅")
            except Exception as e:
                st.error(f"Erro ao salvar: Verifique se o app é EDITOR na planilha. Detalhe: {e}")

if user_email in ADMINS:
    with abas[3]:
        st.header("Configurações")
        st.write("Aqui a Clau define Projetos Globais e Valores Individuais.")
        df_edit = st.data_editor(df_config, num_rows="dynamic", use_container_width=True)
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=df_edit)
            st.success("Salvo! ⚙️")
            st.rerun()