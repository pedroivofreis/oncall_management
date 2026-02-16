import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão de Horas", layout="wide")

try:
    user_email = st.user.email
except:
    user_email = "pedro@exemplo.com"

ADMINS = ["pedroivofreis@gmail.com", "claudiele@exemplo.com"] # Substitua pelos e-mails reais

conn = st.connection("gsheets", type=GSheetsConnection)

if user_email in ADMINS:
    abas = st.tabs(["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 Dashboard BI"])
else:
    abas = st.tabs(["🚀 Lançar Horas"])

with abas[0]:
    st.header("Novo Lançamento de Horas")
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        projeto = col1.selectbox("Projeto", ["Eskolare", "Humana", "Clau a Viajante", "Freelance"])
        horas = col2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        descricao = st.text_area("O que você desenvolveu?")
        enviar = st.form_submit_button("Enviar para Aprovação")
        
        if enviar:
            novo_dado = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "email": user_email,
                "projeto": projeto,
                "horas": horas,
                "descricao": descricao,
                "status": "Pendente"
            }])
            df_atual = conn.read()
            df_final = pd.concat([df_atual, novo_dado], ignore_index=True)
            conn.update(data=df_final)
            st.success("Lançamento registrado! ✅")

if user_email in ADMINS:
    with abas[1]:
        st.header("Aprovações")
        df_gestao = conn.read()
        pendentes = df_gestao[df_gestao['status'] == 'Pendente']
        if not pendentes.empty:
            df_editado = st.data_editor(pendentes, use_container_width=True)
            if st.button("Salvar Decisões"):
                df_gestao.update(df_editado)
                conn.update(data=df_gestao)
                st.rerun()
        else:
            st.info("Nenhum lançamento pendente.")

    with abas[2]:
        st.header("Visão Geral")
        df_bi = conn.read()
        df_aprovado = df_bi[df_bi['status'] == 'Aprovado']
        c1, c2 = st.columns(2)
        c1.metric("Horas Aprovadas", f"{df_aprovado['horas'].sum()}h")
        c2.metric("Lançamentos Pendentes", len(df_bi[df_bi['status'] == 'Pendente']))
        st.bar_chart(df_aprovado.groupby("projeto")["horas"].sum())