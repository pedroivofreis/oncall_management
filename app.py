import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid

# --- CONFIGURAÇÃO E LOGIN ---
st.set_page_config(page_title="MVP Gestão de Horas", layout="wide")

# No Streamlit Cloud, isso pega o e-mail do login do Google
# Para testes locais, você pode mockar: user_email = "pedro@exemplo.com"
user_email = st.experimental_user.email 
ADMINS = ["pedro@eskolare.com", "claudiele@exemplo.com"] # Coloque os e-mails reais aqui

# Conexão com o Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- NAVEGAÇÃO ---
st.sidebar.write(f"Logado como: **{user_email}**")
if user_email in ADMINS:
    abas = st.tabs(["🚀 Lançar Horas", "🛡️ Painel da Clau", "📊 BI & Custos"])
else:
    abas = st.tabs(["🚀 Lançar Horas"])

# --- ABA 1: COLABORADOR ---
with abas[0]:
    st.header("Novo Lançamento de Horas")
    
    with st.form("form_horas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        projeto = col1.selectbox("Projeto", ["Eskolare", "Humana", "Clau a Viajante", "Freelance"])
        horas = col2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        descricao = st.text_area("O que você desenvolveu?")
        
        enviar = st.form_submit_button("Enviar para Aprovação")
        
        if enviar:
            # Criando o novo registro
            novo_dado = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "email": user_email,
                "projeto": projeto,
                "horas": horas,
                "descricao": descricao,
                "status": "Pendente"
            }])
            
            # Lendo dados atuais e dando append
            df_atual = conn.read()
            df_final = pd.concat([df_atual, novo_dado], ignore_index=True)
            conn.update(data=df_final)
            
            st.success("Lançamento registrado! Avisando a Clau... ✅")
            # Dica: Aqui você dispararia o seu webhook do n8n para o WhatsApp

# --- ABA 2: GESTÃO (CLAU) ---
if user_email in ADMINS:
    with abas[1]:
        st.header("Aprovações da Gestora")
        df_gestao = conn.read()
        
        # Filtrar apenas o que está pendente
        pendentes = df_gestao[df_gestao['status'] == 'Pendente']
        
        if not pendentes.empty:
            st.write("Edite o status abaixo para 'Aprovado' ou 'Reprovado':")
            df_editado = st.data_editor(pendentes, key="editor_gestao", use_container_width=True)
            
            if st.button("Salvar Decisões"):
                # Atualiza o dataframe original com as edições
                df_gestao.update(df_editado)
                conn.update(data=df_gestao)
                st.rerun()
        else:
            st.success("Tudo em dia! Nenhum lançamento pendente.")

# --- ABA 3: DASHBOARD ---
    with abas[2]:
        st.header("Análise de Operação")
        df_bi = conn.read()
        df_aprovado = df_bi[df_bi['status'] == 'Aprovado']
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Horas Aprovadas", f"{df_aprovado['horas'].sum()}h")
        c2.metric("Projetos Ativos", df_aprovado['projeto'].nunique())
        c3.metric("Lançamentos Pendentes", len(df_bi[df_bi['status'] == 'Pendente']))
        
        st.subheader("Esforço por Projeto")
        st.bar_chart(df_aprovado.groupby("projeto")["horas"].sum())