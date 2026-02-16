import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io
from sqlalchemy import text

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="OnCall Humana - Pro Edition", layout="wide", page_icon="🛡️")

# --- 2. CONEXÃO COM O BANCO (COM AUTO-DESPERTAR) ---
def get_connection():
    tentativas = 3
    for i in range(tentativas):
        try:
            c = st.connection("postgresql", type="sql")
            # Força o banco a acordar do modo 'Idle'
            c.query("SELECT 1", ttl=0) 
            return c
        except Exception:
            if i < tentativas - 1:
                st.toast(f"Acordando o banco Neon... Tentativa {i+1}", icon="⏳")
                time.sleep(5)
            else:
                st.error("Falha ao conectar ao banco de dados. Verifique os Secrets.")
                st.stop()

conn = get_connection()

# --- 3. FUNÇÕES DE BUSCA DE DADOS ---
def get_all_data(): return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)
def get_config_users(): return conn.query("SELECT * FROM usuarios", ttl=0)
def get_config_projs(): return conn.query("SELECT * FROM projetos", ttl=0)

# --- 4. LOGIN E SEGURANÇA ---
df_u_login = get_config_users()
# Mapeia as credenciais vindas do banco Neon
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in df_u_login.itertuples()}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário para entrar.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.stop()

# --- 5. CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()

# --- 6. INTERFACE EM ABAS (VERSÃO 100% COMPLETA) ---
tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel", "🛡️ Admin Geral", "📈 BI Financeiro", "⚙️ Configurações"])

# === ABA 1: LANÇAMENTOS (CLEAN & MASSA) ===
with tabs[0]:
    st.subheader("📝 Novo Registro")
    
    # Opção Compacta para Importação via Excel
    with st.expander("📥 Importar registros via Excel (.xlsx)"):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=["projeto", "horas", "data", "tipo", "descricao"]).to_excel(writer, index=False)
        st.download_button("📂 Baixar Planilha Modelo", data=buffer.getvalue(), file_name="modelo_oncall.xlsx")
        
        up_file = st.file_uploader("Upload", type=["xlsx"], label_visibility="collapsed")
        if up_file:
            if st.button("🚀 Confirmar Importação em Massa"):
                df_m = pd.read_excel(up_file)
                with conn.session as s:
                    for r in df_m.itertuples():
                        comp = pd.to_datetime(r.data).strftime("%Y-%m")
                        # SQL corrigido para evitar o ArgumentError
                        s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                                  {"id": str(uuid.uuid4()), "e": user_email, "p": r.projeto, "h": r.horas, "c": comp, "t": r.tipo, "d": r.descricao, "v": dict_users[user_email]["valor"]})
                    s.commit()
                st.success("✅ Importado com sucesso!"); time.sleep(1); st.rerun()

    # Formulário Individual de Lançamento
    with st.form("f_ind", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        p = c1.selectbox("Projeto", lista_projetos if lista_projetos else ["Sustentação"])
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "Reunião", "Design", "QA"])
        d = c3.date_input("Data", datetime.now())
        c4, c5 = st.columns([1, 4])
        h = c4.number_input("Horas", min_value=0.5, step=0.5)
        desc = c5.text_input("O que você fez hoje?")
        
        if st.form_submit_button("🚀 Gravar Lançamento"):
            # Uso da função text() para compatibilidade total com o Neon
            query = text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)")
            params = {"id": str(uuid.uuid4()), "e": user_email, "p": p, "h": h, "c": d.strftime("%Y-%m"), "t": t, "d": desc, "v": dict_users[user_email]["valor"]}
            with conn.session as s:
                s.execute(query, params)
                s.commit()
            st.success("✅ Lançamento realizado!"); time.sleep(1); st.rerun()

# === ABA 2: MEU PAINEL (VISÃO COLABORADOR) ===
with tabs[1]:
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    if not meus.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totais", f"{meus['horas'].sum():.1f}h")
        c2.metric("Aprovadas", f"{meus[meus['status_aprovaca']=='Aprovado']['horas'].sum():.1f}h")
        c3.metric("Valor Estimado", f"R$ {(meus['horas'] * meus['valor_hora_historico']).sum():.2f}")
        st.dataframe(meus, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum lançamento encontrado.")

# === ABA 3: ADMIN (VISÃO GESTOR) ===
with tabs[2]:
    if user_email in ADMINS:
        st.subheader("🛡️ Gestão de Aprovações")
        df_editado = st.data_editor(df_lan, use_container_width=True, hide_index=True)
        if st.button("💾 Sincronizar Tudo"):
            with conn.session as s:
                for r in df_editado.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, projeto = :p, horas = :h, tipo = :t WHERE id = :id"),
                             {"s": r.status_aprovaca, "p": r.projeto, "h": r.horas, "t": r.tipo, "id": r.id})
                s.commit()
            st.success("Banco de dados atualizado!"); time.sleep(1); st.rerun()

# === ABA 4: BI FINANCEIRO (DASHBOARDS) ===
with tabs[3]:
    if user_email in ADMINS and not df_lan.empty:
        st.subheader("📈 BI de Custos e Alocação")
        df_bi = df_lan.copy()
        df_bi["custo"] = df_bi["horas"] * df_bi["valor_hora_historico"]
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Custo por Projeto (R$)**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        with col2:
            st.write("**Horas por Colaborador**")
            st.bar_chart(df_bi.groupby("colaborador_email")["horas"].sum())
            
        st.write("**Resumo Mensal de Alocação**")
        st.dataframe(df_bi.groupby(["competencia", "projeto"])["horas"].sum().unstack().fillna(0))

# === ABA 5: CONFIGURAÇÕES (GESTÃO MASTER) ===
with tabs[4]:
    if user_email in ADMINS:
        c1, c2 = st.columns(2)
        with c1:
            st.write("👥 **Gestão de Usuários (E-mail, R$/H, Senha)**")
            new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    s.execute(text("DELETE FROM usuarios"))
                    for r in new_u.itertuples():
                        if r.email: s.execute(text("INSERT INTO usuarios (email, valor_hora, senha) VALUES (:e, :v, :s)"), {"e": r.email, "v": r.valor_hora, "s": r.senha})
                    s.commit()
                st.rerun()
        with c2:
            st.write("📁 **Lista de Projetos Ativos**")
            new_p = st.data_editor(get_config_projs(), num_rows="dynamic", hide_index=True)
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    s.execute(text("DELETE FROM projetos"))
                    for r in new_p.itertuples():
                        if r.nome: s.execute(text("INSERT INTO projetos (nome) VALUES (:n)"), {"n": r.nome})
                    s.commit()
                st.rerun()