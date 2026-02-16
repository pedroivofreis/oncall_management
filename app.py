import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="OnCall Humana - Neon SQL", layout="wide", page_icon="🛡️")

# 1. CONEXÃO COM O NEON
conn = st.connection("postgresql", type="sql")

# --- FUNÇÕES DE BUSCA ---
def get_all_data():
    return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)

def get_config_users():
    return conn.query("SELECT * FROM usuarios", ttl=0)

def get_config_projs():
    return conn.query("SELECT * FROM projetos", ttl=0)

# --- LOGIN E SEGURANÇA ---
df_u = get_config_users()
# Mapeia email -> senha e valor_hora vindo do Banco
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in df_u.itertuples()}

# Seus e-mails como ADM
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("Selecione seu e-mail:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário para entrar.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.error("Senha incorreta.")
    st.stop()

# --- CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()

# --- INTERFACE ---
tabs = st.tabs(["📝 Lançar Horas", "📊 Meu Painel", "🛡️ Admin", "📈 BI Financeiro", "⚙️ Setup"])

# === ABA 1: LANÇAR ===
with tabs[0]:
    st.subheader(f"Novo Lançamento - {user_email}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projetos if lista_projetos else ["Nenhum projeto cadastrado"])
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião"])
        d = c1.date_input("Data", datetime.now())
        h = c2.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição da Atividade")
        
        if st.form_submit_button("🚀 ENVIAR PARA O BANCO"):
            query = """
                INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico)
                VALUES (:id, :email, :proj, :hrs, :comp, :tipo, :desc, :v_h)
            """
            params = {
                "id": str(uuid.uuid4()), "email": user_email, "proj": p, "hrs": h,
                "comp": d.strftime("%Y-%m"), "tipo": t, "desc": desc, 
                "v_h": dict_users[user_email]["valor"]
            }
            with conn.session as s:
                s.execute(query, params)
                s.commit()
            st.success("✅ Gravado com sucesso!")
            time.sleep(1); st.rerun()

# === ABA 2: DASHBOARD PESSOAL ===
with tabs[1]:
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    if not meus.empty:
        st.dataframe(meus, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum registro encontrado.")

# === ABA 3: ADMIN (SÓ VOCÊ E CLAU) ===
with tabs[2]:
    if user_email in ADMINS:
        st.subheader("🛡️ Gestão Geral")
        df_editado = st.data_editor(df_lan, use_container_width=True, hide_index=True)
        if st.button("💾 Sincronizar Edições"):
            with conn.session as s:
                for row in df_editado.itertuples():
                    s.execute(
                        "UPDATE lancamentos SET status_aprovaca = :status, projeto = :proj, horas = :hrs WHERE id = :id",
                        {"status": row.status_aprovaca, "proj": row.projeto, "hrs": row.horas, "id": row.id}
                    )
                s.commit()
            st.success("Alterações salvas!")
            time.sleep(1); st.rerun()

# === ABA 4: BI FINANCEIRO ===
with tabs[3]:
    if user_email in ADMINS:
        st.subheader("📈 BI")
        if not df_lan.empty:
            df_bi = df_lan.copy()
            df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
            st.bar_chart(df_bi.groupby("projeto")["horas"].sum())
        else:
            st.warning("Sem dados para o BI.")

# === ABA 5: SETUP (CONFIGURAÇÕES) ===
with tabs[4]:
    if user_email in ADMINS:
        st.subheader("⚙️ Setup do Sistema")
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Usuários e Senhas**")
            new_u = st.data_editor(df_u, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    s.execute("DELETE FROM usuarios")
                    for r in new_u.itertuples():
                        s.execute("INSERT INTO usuarios (email, valor_hora, senha) VALUES (:e, :v, :s)", 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha})
                    s.commit()
                st.rerun()
        with c2:
            st.write("**Projetos**")
            df_p = get_config_projs()
            new_p = st.data_editor(df_p, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    s.execute("DELETE FROM projetos")
                    for r in new_p.itertuples():
                        s.execute("INSERT INTO projetos (nome) VALUES (:n)", {"n": r.nome})
                    s.commit()
                st.rerun()