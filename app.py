import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO INICIAL (DEVE SER A PRIMEIRA LINHA) ---
st.set_page_config(page_title="OnCall Humana - Pro Edition", layout="wide", page_icon="🛡️")

# 1. CONEXÃO COM O BANCO NEON
try:
    conn = st.connection("postgresql", type="sql")
except Exception as e:
    st.error("Erro na conexão com o banco. Verifique o secrets.toml.")
    st.stop()

# --- CONSULTAS SQL ---
def get_all_data():
    return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)

def get_config_users():
    return conn.query("SELECT * FROM usuarios", ttl=0)

def get_config_projs():
    return conn.query("SELECT * FROM projetos", ttl=0)

# --- LOGIN ---
df_u = get_config_users()
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in df_u.itertuples()}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.stop()

# --- CARREGAMENTO ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()

# --- ABAS ---
tabs = st.tabs(["📝 Lançar", "📊 Meu Painel", "🛡️ Admin", "📈 BI", "⚙️ Setup"])

with tabs[0]: # LANÇAR
    st.subheader(f"Novo Lançamento - {user_email}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projetos if lista_projetos else ["Sustentação"])
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "Reunião"])
        d = c1.date_input("Data", datetime.now())
        h = c2.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição")
        
        if st.form_submit_button("🚀 GRAVAR NO NEON"):
            query = """
                INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico)
                VALUES (:id, :email, :proj, :hrs, :comp, :tipo, :desc, :v_h)
            """
            params = {
                "id": str(uuid.uuid4()), "email": user_email, "proj": p, "hrs": h,
                "comp": d.strftime("%Y-%m"), "tipo": t, "desc": desc, "v_h": dict_users[user_email]["valor"]
            }
            with conn.session as s:
                s.execute(query, params)
                s.commit()
            st.success("✅ Gravado!")
            time.sleep(1); st.rerun()

with tabs[1]: # DASH PESSOAL
    st.dataframe(df_lan[df_lan["colaborador_email"] == user_email], use_container_width=True, hide_index=True)

with tabs[2]: # ADMIN
    if user_email in ADMINS:
        df_editado = st.data_editor(df_lan, use_container_width=True, hide_index=True)
        if st.button("💾 Sincronizar Alterações"):
            with conn.session as s:
                for row in df_editado.itertuples():
                    s.execute(
                        "UPDATE lancamentos SET status_aprovaca = :status, projeto = :proj, horas = :hrs WHERE id = :id",
                        {"status": row.status_aprovaca, "proj": row.projeto, "hrs": row.horas, "id": row.id}
                    )
                s.commit()
            st.rerun()

with tabs[3]: # BI
    if user_email in ADMINS and not df_lan.empty:
        df_bi = df_lan.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        st.bar_chart(df_bi.groupby("projeto")["horas"].sum())

with tabs[4]: # SETUP
    if user_email in ADMINS:
        c1, c2 = st.columns(2)
        with c1:
            new_u = st.data_editor(df_u, num_rows="dynamic", hide_index=True, key="u_edt")
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    s.execute("DELETE FROM usuarios")
                    for r in new_u.itertuples():
                        s.execute("INSERT INTO usuarios (email, valor_hora, senha) VALUES (:e, :v, :s)", 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha})
                    s.commit()
                st.rerun()
        with c2:
            new_p = st.data_editor(get_config_projs(), num_rows="dynamic", hide_index=True, key="p_edt")
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    s.execute("DELETE FROM projetos")
                    for r in new_p.itertuples():
                        s.execute("INSERT INTO projetos (nome) VALUES (:n)", {"n": r.nome})
                    s.commit()
                st.rerun()