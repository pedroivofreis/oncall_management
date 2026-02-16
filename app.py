import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO BÁSICA ---
st.set_page_config(page_title="OnCall v25 - Back to Basics", layout="wide", page_icon="🚀")

# Colunas exatas da sua planilha nova
COLS = [
    "id", "data_registro", "colaborador_email", "projeto", "horas", 
    "status_aprovaca", "data_decisao", "competencia", "tipo", 
    "descricão", "email_enviado", "valor_hora_historico"
]

# --- CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- LEITURA SIMPLES (Sem travas que apagam) ---
def ler_dados():
    conn.clear()
    try:
        df = conn.read(worksheet="banco_horas", ttl=0)
        if df is None or df.empty:
            return pd.DataFrame(columns=COLS)
        return df
    except:
        return pd.DataFrame(columns=COLS)

df_lan = ler_dados()

# --- CONFIGURAÇÕES DE ACESSO ---
dict_users = {
    "pedroivofernandesreis@gmail.com": {"valor": 100, "senha": "123"},
    "claudiele.andrade@gmail.com": {"valor": 150, "senha": "456"}
}
lista_projs = ["Sustentação", "Projeto A", "Projeto B", "Consultoria", "Outros"]

# --- SIDEBAR LOGIN ---
st.sidebar.title("🚀 OnCall Phoenix")
user = st.sidebar.selectbox("Usuário", ["Selecione..."] + list(dict_users.keys()))
if user == "Selecione...": st.stop()
senha = st.sidebar.text_input("Senha", type="password")
if senha != dict_users[user]["senha"]: st.stop()

# --- INTERFACE ---
t1, t2, t3 = st.tabs(["📝 LANÇAR", "🛡️ ADMIN", "📊 BI"])

with t1:
    with st.form("form_lancar"):
        st.markdown("### Novo Lançamento")
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projs)
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "Reunião"])
        d = c1.date_input("Data", datetime.now())
        h = c2.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição")
        
        if st.form_submit_button("GRAVAR REGISTRO"):
            novo = {
                "id": str(uuid.uuid4()), 
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colaborador_email": user, 
                "projeto": p, 
                "horas": str(h),
                "status_aprovaca": "Pendente", 
                "data_decisao": "", 
                "competencia": d.strftime("%Y-%m"),
                "tipo": t, 
                "descricão": desc, 
                "email_enviado": "", 
                "valor_hora_historico": str(dict_users[user]["valor"])
            }
            # Lógica simples: Pega o que leu e adiciona o novo
            df_atualizado = pd.concat([df_lan, pd.DataFrame([novo])], ignore_index=True)
            
            # Grava e reinicia
            conn.update(worksheet="banco_horas", data=df_atualizado.fillna("").astype(str))
            st.success("Gravado!")
            time.sleep(1)
            st.rerun()

with t2:
    if user in ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]:
        st.markdown("### Edição Master")
        # Editor sem formulário, salvando direto no botão (como na versão que deu certo)
        df_editado = st.data_editor(df_lan, num_rows="dynamic", use_container_width=True)
        if st.button("💾 SALVAR ALTERAÇÕES"):
            conn.update(worksheet="banco_horas", data=df_editado.fillna("").astype(str))
            st.success("Planilha Atualizada!")
            time.sleep(1)
            st.rerun()

with t3:
    # BI Simples para não sobrecarregar
    if not df_lan.empty:
        df_lan["horas"] = pd.to_numeric(df_lan["horas"], errors="coerce").fillna(0)
        st.bar_chart(df_lan.groupby("projeto")["horas"].sum())
        st.dataframe(df_lan, use_container_width=True)