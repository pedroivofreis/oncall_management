import streamlit as st
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="OnCall Neon SQL", layout="wide", page_icon="⚡")

# CONEXÃO DIRETA COM O NEON
conn = st.connection("postgresql", type="sql")

# LEITURA DOS DADOS
def carregar_dados(user_email):
    query = f"SELECT * FROM lancamentos WHERE colaborador_email = '{user_email}' ORDER BY data_registro DESC"
    return conn.query(query, ttl=0)

# LOGIN
usuarios_df = conn.query("SELECT * FROM usuarios", ttl=0)
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in usuarios_df.itertuples()}

st.sidebar.title("⚡ OnCall SQL")
email_input = st.sidebar.selectbox("E-mail", ["Selecione..."] + list(dict_users.keys()))

if email_input == "Selecione...":
    st.info("👈 Faça login para continuar.")
    st.stop()

senha_input = st.sidebar.text_input("Senha", type="password")
if senha_input != dict_users[email_input]["senha"]:
    st.stop()

# INTERFACE
t1, t2 = st.tabs(["📝 NOVO LANÇAMENTO", "📊 MEUS DADOS"])

with t1:
    projs = conn.query("SELECT nome FROM projetos", ttl=0)['nome'].tolist()
    with st.form("form_sql", clear_on_submit=True):
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", projs)
        t = c2.selectbox("Tipo", ["Front", "Back", "Infra", "Reunião"])
        d = c1.date_input("Data", datetime.now())
        h = c2.number_input("Horas", step=0.5, min_value=0.5)
        desc = st.text_area("Descrição")
        
        if st.form_submit_button("💾 SALVAR NO BANCO"):
            # O SQL INSERT é atômico: ou grava tudo ou nada. Nunca apaga cabeçalho!
            sql = """
                INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico)
                VALUES (:id, :email, :proj, :hrs, :comp, :tipo, :desc, :v_h)
            """
            params = {
                "id": str(uuid.uuid4()), "email": email_input, "proj": p, "hrs": h,
                "comp": d.strftime("%Y-%m"), "tipo": t, "desc": desc, "v_h": dict_users[email_input]["valor"]
            }
            with conn.session as s:
                s.execute(sql, params)
                s.commit()
            st.success("✅ Gravado com sucesso no Neon!")
            st.rerun()

with t2:
    st.dataframe(carregar_dados(email_input), use_container_width=True)