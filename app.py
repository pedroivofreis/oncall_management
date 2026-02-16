import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="OnCall Pro - Neon SQL", layout="wide", page_icon="⚡")

# 1. CONEXÃO COM O NEON
conn = st.connection("postgresql", type="sql")

# --- FUNÇÕES DE BUSCA (QUERIES) ---
def get_all_data():
    return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)

def get_config_users():
    return conn.query("SELECT * FROM usuarios", ttl=0)

def get_config_projs():
    return conn.query("SELECT * FROM projetos", ttl=0)

# --- LOGIN E SEGURANÇA ---
df_u = get_config_users()
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in df_u.itertuples()}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("⚡ OnCall Management")
user_email = st.sidebar.selectbox("Usuário:", ["Selecione..."] + list(dict_users.keys()))

if user_email == "Selecione...":
    st.info("👈 Faça login para acessar o sistema.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.stop()

# --- CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()

# --- INTERFACE EM ABAS ---
tabs = st.tabs(["📝 Lançar", "📊 Meu Dash", "🛡️ Painel Admin", "📈 BI Financeiro", "⚙️ Configurações"])

# === ABA 1: LANÇAMENTOS ===
with tabs[0]:
    st.subheader(f"Novo Registro - {user_email}")
    with st.form("form_lancar", clear_on_submit=True):
        c1, c2 = st.columns(2)
        p = c1.selectbox("Projeto", lista_projetos)
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião"])
        d = c1.date_input("Data da Atividade", datetime.now())
        h = c2.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        desc = st.text_area("Descrição detalhada")
        
        if st.form_submit_button("🚀 GRAVAR NO BANCO"):
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
            st.success("✅ Gravado com sucesso no Neon!")
            time.sleep(1); st.rerun()

# === ABA 2: MEU DASHBOARD (VISÃO DO COLABORADOR) ===
with tabs[1]:
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    if not meus.empty:
        meus["horas"] = pd.to_numeric(meus["horas"], errors="coerce").fillna(0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Pendentes", f"{meus[meus['status_aprovaca']=='Pendente']['horas'].sum():.1f}h")
        c2.metric("Horas Aprovadas", f"{meus[meus['status_aprovaca']=='Aprovado']['horas'].sum():.1f}h")
        c3.metric("Horas Pagas", f"{meus[meus['status_aprovaca']=='Pago']['horas'].sum():.1f}h")
        
        st.dataframe(meus, use_container_width=True, hide_index=True)
    else:
        st.info("Você ainda não possui lançamentos.")

# === ABA 3: ADMIN (SÓ ADMINS) ===
with tabs[2]:
    if user_email in ADMINS:
        st.subheader("🛡️ Gestão de Lançamentos")
        st.write("Edite os dados diretamente na tabela abaixo:")
        
        # O data_editor agora é o coração do Admin
        df_editado = st.data_editor(df_lan, use_container_width=True, hide_index=True, key="admin_editor")
        
        if st.button("💾 Salvar Alterações em Massa"):
            # Lógica para sincronizar as edições do DataFrame com o Banco SQL
            # Para simplificar, deletamos e reinserimos (ou usamos UPSERT se preferir)
            # Mas aqui vamos fazer um UPDATE por ID
            with conn.session as s:
                for row in df_editado.itertuples():
                    s.execute(
                        "UPDATE lancamentos SET status_aprovaca = :status, projeto = :proj, horas = :hrs WHERE id = :id",
                        {"status": row.status_aprovaca, "proj": row.projeto, "hrs": row.horas, "id": row.id}
                    )
                s.commit()
            st.success("Banco de dados sincronizado!")
            time.sleep(1); st.rerun()

# === ABA 4: BI FINANCEIRO ===
with tabs[3]:
    if user_email in ADMINS:
        st.subheader("📈 Inteligência de Custos")
        df_bi = df_lan.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["valor_hora_historico"] = pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(0)
        df_bi["custo_total"] = df_bi["horas"] * df_bi["valor_hora_historico"]
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Custo por Projeto (R$)**")
            st.bar_chart(df_bi.groupby("projeto")["custo_total"].sum())
        with col2:
            st.write("**Distribuição de Horas por Tipo**")
            st.bar_chart(df_bi.groupby("tipo")["horas"].sum())
            
        st.write("**Resumo por Colaborador**")
        resumo = df_bi.groupby("colaborador_email")[["horas", "custo_total"]].sum()
        st.table(resumo)

# === ABA 5: CONFIGURAÇÕES ===
with tabs[4]:
    if user_email in ADMINS:
        c1, c2 = st.columns(2)
        with c1:
            st.write("👥 **Gestão de Usuários**")
            new_u = st.data_editor(df_u, num_rows="dynamic", hide_index=True)
            if st.button("Atualizar Usuários"):
                with conn.session as s:
                    s.execute("DELETE FROM usuarios") # Reset simples para config
                    for r in new_u.itertuples():
                        s.execute("INSERT INTO usuarios (email, valor_hora, senha) VALUES (:e, :v, :s)", 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha})
                    s.commit()
                st.rerun()
        with c2:
            st.write("📁 **Gestão de Projetos**")
            df_p = get_config_projs()
            new_p = st.data_editor(df_p, num_rows="dynamic", hide_index=True)
            if st.button("Atualizar Projetos"):
                with conn.session as s:
                    s.execute("DELETE FROM projetos")
                    for r in new_p.itertuples():
                        s.execute("INSERT INTO projetos (nome) VALUES (:n)", {"n": r.nome})
                    s.commit()
                st.rerun()