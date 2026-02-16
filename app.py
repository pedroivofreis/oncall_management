import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time

# --- 1. CONFIGURAÇÃO DA PÁGINA (DEVE SER A PRIMEIRA LINHA) ---
st.set_page_config(page_title="OnCall Humana - Pro Edition", layout="wide", page_icon="🛡️")

# --- 2. FUNÇÃO PARA CONECTAR E ACORDAR O NEON (RETRY LOGIC) ---
def get_connection():
    tentativas = 3
    for i in range(tentativas):
        try:
            # Tenta estabelecer a conexão configurada no secrets.toml
            c = st.connection("postgresql", type="sql")
            # Faz uma mini-consulta para validar se o banco está pronto
            c.query("SELECT 1", ttl=0)
            return c
        except Exception:
            if i < tentativas - 1:
                st.toast(f"Acordando o banco de dados Neon... Tentativa {i+1}", icon="⏳")
                time.sleep(5) # Espera 5 segundos para o banco sair do estado 'Idle'
            else:
                st.error("O banco de dados demorou muito para responder. Verifique o status no Console do Neon ou atualize a página.")
                st.stop()

conn = get_connection()

# --- 3. FUNÇÕES DE CONSULTA SQL ---
def get_all_data():
    return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)

def get_config_users():
    return conn.query("SELECT * FROM usuarios", ttl=0)

def get_config_projs():
    return conn.query("SELECT * FROM projetos", ttl=0)

# --- 4. LOGIN E SEGURANÇA ---
df_u = get_config_users()
if df_u.empty:
    st.warning("⚠️ O banco parece estar vazio. Verifique se as tabelas foram criadas no Neon.")
    st.stop()

# Mapeia email -> senha e valor vindo do banco Neon
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in df_u.itertuples()}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário para entrar.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.warning("Aguardando senha correta...")
    st.stop()

# --- 5. CARREGAMENTO DE DADOS E ABAS ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()

tabs = st.tabs(["📝 Lançar", "📊 Meu Painel", "🛡️ Admin Geral", "📈 BI Financeiro", "⚙️ Setup"])

# === ABA 1: LANÇAMENTOS ===
with tabs[0]:
    st.subheader(f"Novo Registro - {user_email}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projetos if lista_projetos else ["Sustentação"])
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião"])
        d = c1.date_input("Data da Atividade", datetime.now())
        h = c2.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição detalhada")
        
        if st.form_submit_button("🚀 GRAVAR NO NEON"):
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
            st.success("✅ Gravado com sucesso no SQL!")
            time.sleep(1)
            st.rerun()

# === ABA 2: MEU PAINEL (HISTÓRICO PESSOAL) ===
with tabs[1]:
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    if not meus.empty:
        st.dataframe(meus, use_container_width=True, hide_index=True)
    else:
        st.info("Você ainda não possui lançamentos.")

# === ABA 3: ADMIN (EDIÇÃO E APROVAÇÃO) ===
with tabs[2]:
    if user_email in ADMINS:
        st.subheader("🛡️ Gestão Administrativa")
        df_editado = st.data_editor(df_lan, use_container_width=True, hide_index=True)
        if st.button("💾 Sincronizar Edições"):
            with conn.session as s:
                for row in df_editado.itertuples():
                    s.execute(
                        "UPDATE lancamentos SET status_aprovaca = :status, projeto = :proj, horas = :hrs, tipo = :tipo, descricao = :desc WHERE id = :id",
                        {"status": row.status_aprovaca, "proj": row.projeto, "hrs": row.horas, "tipo": row.tipo, "desc": row.descricao, "id": row.id}
                    )
                s.commit()
            st.success("Dados atualizados!")
            time.sleep(1); st.rerun()

# === ABA 4: BI FINANCEIRO ===
with tabs[3]:
    if user_email in ADMINS:
        st.subheader("📈 Inteligência de Custos")
        if not df_lan.empty:
            df_bi = df_lan.copy()
            df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
            df_bi["v_h"] = pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(0)
            df_bi["custo"] = df_bi["horas"] * df_bi["v_h"]
            
            c1, c2 = st.columns(2)
            with c1: 
                st.write("**Custo por Projeto (R$)**")
                st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
            with c2: 
                st.write("**Horas por Tipo**")
                st.bar_chart(df_bi.groupby("tipo")["horas"].sum())
        else:
            st.warning("Sem dados para análise no momento.")

# === ABA 5: SETUP (PROJETOS E USUÁRIOS) ===
with tabs[4]:
    if user_email in ADMINS:
        st.subheader("⚙️ Configurações")
        col_u, col_p = st.columns(2)
        with col_u:
            st.write("**Usuários & Senhas**")
            new_u = st.data_editor(df_u, num_rows="dynamic", hide_index=True, key="u_edit")
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    s.execute("DELETE FROM usuarios")
                    for r in new_u.itertuples():
                        s.execute("INSERT INTO usuarios (email, valor_hora, senha) VALUES (:e, :v, :s)", 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha})
                    s.commit()
                st.rerun()
        with col_p:
            st.write("**Projetos**")
            df_p_now = get_config_projs()
            new_p = st.data_editor(df_p_now, num_rows="dynamic", hide_index=True, key="p_edit")
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    s.execute("DELETE FROM projetos")
                    for r in new_p.itertuples():
                        s.execute("INSERT INTO projetos (nome) VALUES (:n)", {"n": r.nome})
                    s.commit()
                st.rerun()