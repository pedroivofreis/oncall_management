import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO DA PÁGINA (DEVE SER A PRIMEIRA LINHA) ---
st.set_page_config(page_title="OnCall Humana - Pro Edition", layout="wide", page_icon="🛡️")

# 1. CONEXÃO COM O BANCO NEON
# Certifique-se de que o requirements.txt tenha: streamlit, pandas, psycopg2-binary, sqlalchemy
try:
    conn = st.connection("postgresql", type="sql")
except Exception as e:
    st.error("Erro na conexão com o banco. Verifique se os Secrets no Streamlit Cloud estão salvos corretamente.")
    st.stop()

# --- FUNÇÕES DE BUSCA (QUERIES SQL) ---
def get_all_data():
    return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)

def get_config_users():
    return conn.query("SELECT * FROM usuarios", ttl=0)

def get_config_projs():
    return conn.query("SELECT * FROM projetos", ttl=0)

# --- LOGIN E SEGURANÇA ---
df_u = get_config_users()
# Mapeia email -> senha e valor vindo do banco Neon
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in df_u.itertuples()}

# Seus e-mails como Administradores
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

# --- CARREGAMENTO GLOBAL DE DADOS ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()

# --- INTERFACE EM ABAS (COMPLEXIDADE TOTAL) ---
tabs = st.tabs(["📝 Lançar Horas", "📊 Meu Painel", "🛡️ Admin Geral", "📈 BI Financeiro", "⚙️ Setup"])

# === ABA 1: LANÇAMENTOS ===
with tabs[0]:
    st.subheader(f"Novo Registro - {user_email}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projetos if lista_projetos else ["Sustentação"])
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião"])
        d = c1.date_input("Data da Atividade", datetime.now())
        h = c2.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição detalhada da atividade")
        
        if st.form_submit_button("🚀 GRAVAR NO BANCO NEON"):
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
        st.info("Você ainda não possui lançamentos cadastrados.")

# === ABA 3: ADMIN (EDIÇÃO E APROVAÇÃO) ===
with tabs[2]:
    if user_email in ADMINS:
        st.subheader("🛡️ Gestão Administrativa")
        st.info("Edite os dados diretamente na tabela e clique em Sincronizar.")
        # Editor de dados robusto
        df_editado = st.data_editor(df_lan, use_container_width=True, hide_index=True)
        
        if st.button("💾 Sincronizar Edições com o Banco"):
            with conn.session as s:
                for row in df_editado.itertuples():
                    s.execute(
                        "UPDATE lancamentos SET status_aprovaca = :status, projeto = :proj, horas = :hrs, tipo = :tipo, descricao = :desc WHERE id = :id",
                        {"status": row.status_aprovaca, "proj": row.projeto, "hrs": row.horas, "tipo": row.tipo, "desc": row.descricao, "id": row.id}
                    )
                s.commit()
            st.success("Dados sincronizados com sucesso!")
            time.sleep(1)
            st.rerun()

# === ABA 4: BI FINANCEIRO (GRÁFICOS) ===
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
                st.write("**Investimento por Projeto (R$)**")
                st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
            with c2: 
                st.write("**Distribuição de Horas por Tipo**")
                st.bar_chart(df_bi.groupby("tipo")["horas"].sum())
        else:
            st.warning("Aguardando dados para gerar o BI.")

# === ABA 5: SETUP (GESTÃO DE PROJETOS E USUÁRIOS) ===
with tabs[4]:
    if user_email in ADMINS:
        st.subheader("⚙️ Configurações Globais")
        col_u, col_p = st.columns(2)
        
        with col_u:
            st.write("👥 **Usuários & Senhas**")
            # Gerencie novos médicos ou mude senhas por aqui
            new_u = st.data_editor(df_u, num_rows="dynamic", hide_index=True, key="users_editor")
            if st.button("Atualizar Lista de Usuários"):
                with conn.session as s:
                    s.execute("DELETE FROM usuarios")
                    for r in new_u.itertuples():
                        s.execute("INSERT INTO usuarios (email, valor_hora, senha) VALUES (:e, :v, :s)", 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha})
                    s.commit()
                st.success("Usuários atualizados!")
                time.sleep(1); st.rerun()
                
        with col_p:
            st.write("📁 **Projetos Ativos**")
            df_p_current = get_config_projs()
            new_p = st.data_editor(df_p_current, num_rows="dynamic", hide_index=True, key="projs_editor")
            if st.button("Atualizar Lista de Projetos"):
                with conn.session as s:
                    s.execute("DELETE FROM projetos")
                    for r in new_p.itertuples():
                        s.execute("INSERT INTO projetos (nome) VALUES (:n)", {"n": r.nome})
                    s.commit()
                st.success("Projetos atualizados!")
                time.sleep(1); st.rerun()