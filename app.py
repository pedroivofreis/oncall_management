import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io

# --- 1. CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="OnCall Humana - Pro Edition", layout="wide", page_icon="🛡️")

# 2. CONEXÃO COM O NEON (COM RETRY LOGIC)
def get_connection():
    tentativas = 3
    for i in range(tentativas):
        try:
            c = st.connection("postgresql", type="sql")
            c.query("SELECT 1", ttl=0) # Acorda o banco
            return c
        except Exception:
            if i < tentativas - 1:
                st.toast(f"Acordando o banco Neon... Tentativa {i+1}", icon="⏳")
                time.sleep(5)
            else:
                st.error("Falha ao conectar ao banco de dados.")
                st.stop()

conn = get_connection()

# --- 3. FUNÇÕES DE DADOS ---
def get_all_data():
    return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)

def get_config_users():
    return conn.query("SELECT * FROM usuarios", ttl=0)

def get_config_projs():
    return conn.query("SELECT * FROM projetos", ttl=0)

# --- 4. LOGIN ---
df_u = get_config_users()
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in df_u.itertuples()}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("E-mail:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Faça login para acessar.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.stop()

# --- 5. CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()

# --- 6. INTERFACE (TABS) ---
tabs = st.tabs(["📝 Lançar", "📊 Meu Painel", "🛡️ Admin Geral", "📈 BI Financeiro", "⚙️ Setup & Massa"])

# === TAB 1: LANÇAMENTOS ===
with tabs[0]:
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projetos if lista_projetos else ["Sustentação"])
        t = c2.selectbox("Tipo", ["Front", "Back", "Infra", "Reunião"])
        d = c1.date_input("Data", datetime.now())
        h = c2.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição")
        
        if st.form_submit_button("🚀 GRAVAR REGISTRO"):
            sql = """INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) 
                     VALUES (:id, :email, :proj, :hrs, :comp, :tipo, :desc, :v_h)"""
            params = {"id": str(uuid.uuid4()), "email": user_email, "proj": p, "hrs": h, 
                      "comp": d.strftime("%Y-%m"), "tipo": t, "desc": desc, "v_h": dict_users[user_email]["valor"]}
            with conn.session as s:
                s.execute(sql, params)
                s.commit()
            st.success("✅ Gravado no Neon!")
            time.sleep(1); st.rerun()

# === TAB 3: ADMIN (EDIÇÃO) ===
with tabs[2]:
    if user_email in ADMINS:
        st.subheader("🛡️ Gestão de Lançamentos")
        df_editado = st.data_editor(df_lan, use_container_width=True, hide_index=True)
        if st.button("💾 Sincronizar Alterações"):
            with conn.session as s:
                for r in df_editado.itertuples():
                    s.execute("UPDATE lancamentos SET status_aprovaca = :status, projeto = :proj, horas = :hrs WHERE id = :id", 
                             {"status": r.status_aprovaca, "proj": r.projeto, "hrs": r.horas, "id": r.id})
                s.commit()
            st.rerun()

# === TAB 5: SETUP & UPLOAD EM MASSA ===
with tabs[4]:
    if user_email in ADMINS:
        col1, col2 = st.columns(2)
        
        # --- UPLOAD EM MASSA ---
        with col1:
            st.markdown("### 📥 Importar Lançamentos (CSV)")
            
            # Botão de Download do Modelo
            modelo = pd.DataFrame(columns=["projeto", "horas", "data", "tipo", "descricao"])
            csv = modelo.to_csv(index=False).encode('utf-8')
            st.download_button("📂 Baixar Modelo CSV", data=csv, file_name="modelo_oncall.csv", mime="text/csv")
            
            arquivo = st.file_uploader("Suba o arquivo preenchido", type=["csv"])
            if arquivo:
                df_upload = pd.read_csv(arquivo)
                if st.button("🚀 Confirmar Subida em Massa"):
                    with conn.session as s:
                        for r in df_upload.itertuples():
                            s.execute("""INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) 
                                         VALUES (:id, :email, :proj, :hrs, :comp, :tipo, :desc, :v_h)""",
                                      {"id": str(uuid.uuid4()), "email": user_email, "proj": r.projeto, "hrs": r.horas, 
                                       "comp": str(r.data)[:7], "tipo": r.tipo, "desc": r.descricao, "v_h": dict_users[user_email]["valor"]})
                        s.commit()
                    st.success("✅ Lançamentos importados!")
                    time.sleep(1); st.rerun()

        # --- GESTÃO DE PROJETOS ---
        with col2:
            st.markdown("### 📁 Gestão de Projetos")
            df_p = get_config_projs()
            new_p = st.data_editor(df_p, num_rows="dynamic", hide_index=True)
            if st.button("💾 Salvar Projetos"):
                with conn.session as s:
                    s.execute("DELETE FROM projetos")
                    for r in new_p.itertuples():
                        if r.nome: s.execute("INSERT INTO projetos (nome) VALUES (:n)", {"n": r.nome})
                    s.commit()
                st.success("Projetos atualizados!")
                time.sleep(1); st.rerun()