import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io

# --- 1. CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="OnCall Humana - Pro Edition", layout="wide", page_icon="🛡️")

# 2. CONEXÃO COM O NEON (COM RETRY LOGIC PARA ACORDAR O BANCO)
def get_connection():
    tentativas = 3
    for i in range(tentativas):
        try:
            c = st.connection("postgresql", type="sql")
            c.query("SELECT 1", ttl=0) 
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

# --- 4. SEGURANÇA E LOGIN ---
df_u_login = get_config_users()
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in df_u_login.itertuples()}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("E-mail:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário para acessar o sistema.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.warning("Senha incorreta.")
    st.stop()

# --- 5. CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()

# --- 6. INTERFACE EM ABAS ---
tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel", "🛡️ Admin Geral", "📈 BI Financeiro", "⚙️ Configurações"])

# === ABA 1: LANÇAMENTOS (LINHA POR LINHA + MASSA) ===
with tabs[0]:
    col_ind, col_mass = st.columns([1, 1])
    
    with col_ind:
        st.subheader("Individual (Linha por Linha)")
        with st.form("form_lancar", clear_on_submit=True):
            p = st.selectbox("Projeto", lista_projetos if lista_projetos else ["Sustentação"])
            t = st.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "Reunião", "Design", "QA"])
            d = st.date_input("Data da Atividade", datetime.now())
            h = st.number_input("Horas", min_value=0.5, step=0.5)
            desc = st.text_area("Descrição")
            
            if st.form_submit_button("🚀 Gravar Lançamento"):
                sql = """INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) 
                         VALUES (:id, :email, :proj, :hrs, :comp, :tipo, :desc, :v_h)"""
                params = {"id": str(uuid.uuid4()), "email": user_email, "proj": p, "hrs": h, 
                          "comp": d.strftime("%Y-%m"), "tipo": t, "desc": desc, "v_h": dict_users[user_email]["valor"]}
                with conn.session as s:
                    s.execute(sql, params)
                    s.commit()
                st.success("✅ Gravado!")
                time.sleep(1); st.rerun()

    with col_mass:
        st.subheader("Subir em Massa (.xlsx)")
        # Gerar modelo Excel para download
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=["projeto", "horas", "data", "tipo", "descricao"]).to_excel(writer, index=False)
        st.download_button(label="📥 Baixar Planilha Modelo", data=buffer.getvalue(), file_name="modelo_oncall_humana.xlsx", mime="application/vnd.ms-excel")
        
        arquivo_excel = st.file_uploader("Upload de Lançamentos", type=["xlsx"])
        if arquivo_excel:
            df_massa = pd.read_excel(arquivo_excel)
            st.write("Prévia dos dados:", df_massa.head(3))
            if st.button("🚀 Confirmar Importação em Massa"):
                try:
                    with conn.session as s:
                        for r in df_massa.itertuples():
                            # Converte data para string YYYY-MM
                            comp_massa = pd.to_datetime(r.data).strftime("%Y-%m")
                            s.execute("""INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) 
                                         VALUES (:id, :email, :proj, :hrs, :comp, :tipo, :desc, :v_h)""",
                                      {"id": str(uuid.uuid4()), "email": user_email, "proj": r.projeto, "hrs": r.horas, 
                                       "comp": comp_massa, "tipo": r.tipo, "desc": r.descricao, "v_h": dict_users[user_email]["valor"]})
                        s.commit()
                    st.success(f"✅ {len(df_massa)} lançamentos importados com sucesso!")
                    time.sleep(1); st.rerun()
                except Exception as e:
                    st.error(f"Erro no formato dos dados: {e}")

# === ABA 2: MEU PAINEL ===
with tabs[1]:
    st.dataframe(df_lan[df_lan["colaborador_email"] == user_email], use_container_width=True, hide_index=True)

# === ABA 3: ADMIN (APROVAÇÕES) ===
with tabs[2]:
    if user_email in ADMINS:
        st.subheader("🛡️ Gestão de Aprovações")
        df_edit_adm = st.data_editor(df_lan, use_container_width=True, hide_index=True)
        if st.button("💾 Sincronizar Alterações Admin"):
            with conn.session as s:
                for r in df_edit_adm.itertuples():
                    s.execute("UPDATE lancamentos SET status_aprovaca = :status, projeto = :proj, horas = :hrs WHERE id = :id", 
                             {"status": r.status_aprovaca, "proj": r.projeto, "hrs": r.horas, "id": r.id})
                s.commit()
            st.rerun()

# === ABA 5: CONFIGURAÇÕES (PROJETOS E USUÁRIOS) ===
with tabs[4]:
    if user_email in ADMINS:
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("📁 Configuração de Projetos")
            df_p_cfg = get_config_projs()
            new_p_cfg = st.data_editor(df_p_cfg, num_rows="dynamic", hide_index=True, key="cfg_proj")
            if st.button("💾 Salvar Lista de Projetos"):
                with conn.session as s:
                    s.execute("DELETE FROM projetos")
                    for r in new_p_cfg.itertuples():
                        if r.nome: s.execute("INSERT INTO projetos (nome) VALUES (:n)", {"n": r.nome})
                    s.commit()
                st.success("Projetos atualizados!")
                time.sleep(1); st.rerun()

        with c2:
            st.subheader("👥 Configuração de Usuários")
            df_u_cfg = get_config_users()
            # Permite editar E-mail, Valor/Hora e Senha
            new_u_cfg = st.data_editor(df_u_cfg, num_rows="dynamic", hide_index=True, key="cfg_user")
            if st.button("💾 Salvar Usuários e Senhas"):
                with conn.session as s:
                    s.execute("DELETE FROM usuarios")
                    for r in new_u_cfg.itertuples():
                        if r.email: s.execute("INSERT INTO usuarios (email, valor_hora, senha) VALUES (:e, :v, :s)", 
                                              {"e": r.email, "v": r.valor_hora, "s": r.senha})
                    s.commit()
                st.success("Credenciais e valores atualizados!")
                time.sleep(1); st.rerun()