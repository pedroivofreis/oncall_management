import streamlit as st
import pandas as pd
from datetime import datetime
import uuid

# Configuração da página
st.set_page_config(page_title="OnCall Neon SQL - v1.0", layout="wide", page_icon="⚡")

# 1. CONEXÃO DIRETA (Utilizando a URL do secrets.toml)
conn = st.connection("postgresql", type="sql")

# 2. CARREGAMENTO DINÂMICO DOS USUÁRIOS
# Isso substitui as senhas fixas no código
usuarios_df = conn.query("SELECT * FROM usuarios", ttl=0)
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in usuarios_df.itertuples()}

# 3. SIDEBAR DE LOGIN
st.sidebar.title("⚡ OnCall SQL")
email_input = st.sidebar.selectbox("E-mail", ["Selecione..."] + list(dict_users.keys()))

if email_input == "Selecione...":
    st.info("👈 Selecione seu e-mail para entrar.")
    st.stop()

senha_input = st.sidebar.text_input("Senha", type="password")
if senha_input != dict_users[email_input]["senha"]:
    st.warning("Senha incorreta.")
    st.stop()

# 4. INTERFACE PRINCIPAL
tabs = st.tabs(["📝 NOVO LANÇAMENTO", "📊 MEUS DADOS"])

with tabs[0]:
    # Busca projetos direto do banco que você criou
    projs_df = conn.query("SELECT nome FROM projetos", ttl=0)
    lista_projs = projs_df['nome'].tolist()

    with st.form("form_sql_final", clear_on_submit=True):
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projs)
        t = c2.selectbox("Tipo", ["Front", "Back", "Infra", "Reunião"])
        d = c1.date_input("Data", datetime.now())
        h = c2.number_input("Horas", step=0.5, min_value=0.5)
        desc = st.text_area("Descrição da Atividade")
        
        if st.form_submit_button("💾 SALVAR NO BANCO"):
            # Query de inserção segura
            sql = """
                INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico)
                VALUES (:id, :email, :proj, :hrs, :comp, :tipo, :desc, :v_h)
            """
            params = {
                "id": str(uuid.uuid4()),
                "email": email_input,
                "proj": p,
                "hrs": h,
                "comp": d.strftime("%Y-%m"),
                "tipo": t,
                "desc": desc,
                "v_h": dict_users[email_input]["valor"]
            }
            with conn.session as s:
                s.execute(sql, params)
                s.commit()
            st.success("✅ Gravado com sucesso! Sem erros de cabeçalho.")
            time.sleep(1)
            st.rerun()

with tabs[1]:
    # Consulta apenas os dados do usuário logado
    query_meus = f"SELECT data_registro, projeto, horas, tipo, descricao, status_aprovaca FROM lancamentos WHERE colaborador_email = '{email_input}' ORDER BY data_registro DESC"
    df_visualiza = conn.query(query_meus, ttl=0)
    st.dataframe(df_visualiza, use_container_width=True)