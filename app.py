import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io
from sqlalchemy import text

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="OnCall Humana - Enterprise", layout="wide", page_icon="🛡️")

# --- 2. CONEXÃO (AUTO-DESPERTAR) ---
def get_connection():
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0)
        return c
    except:
        st.error("Erro ao conectar ao banco Neon.")
        st.stop()

conn = get_connection()

# --- 3. CARREGAMENTO DE DADOS ---
def get_all_data(): return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)
def get_config_users(): return conn.query("SELECT * FROM usuarios", ttl=0)
def get_config_projs(): return conn.query("SELECT * FROM projetos", ttl=0)
def get_bancos(): return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# --- 4. LOGIN E PERMISSÕES ---
df_u_login = get_config_users()
dict_users = {row.email: {
    "valor": float(row.valor_hora), 
    "senha": str(row.senha), 
    "is_admin": getattr(row, 'is_admin', False)
} for row in df_u_login.itertuples()}

# Admins Mestres
SUPER_ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário para entrar.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.stop()

is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

# --- 5. CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
df_projs = get_config_projs()
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação"]

# --- 6. INTERFACE EM ABAS ---
if is_user_admin:
    tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel", "🛡️ Admin Geral", "💸 Pagamentos", "📈 BI Financeiro", "⚙️ Configurações"])
else:
    tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel"])

# === ABA 1: LANÇAMENTOS ===
with tabs[0]:
    st.subheader("📝 Registro de Atividades")
    with st.form("f_ind", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        p = c1.selectbox("Projeto", lista_projetos)
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "Reunião", "QA", "Banco de Dados", "Dados"])
        d = c3.date_input("Data", datetime.now())
        h = st.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_input("O que você desenvolveu?")
        if st.form_submit_button("🚀 Gravar Lançamento"):
            with conn.session as s:
                s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                          {"id": str(uuid.uuid4()), "e": user_email, "p": p, "h": h, "c": d.strftime("%Y-%m"), "t": t, "d": desc, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Gravado!"); time.sleep(1); st.rerun()

# === ABA 2: MEU PAINEL FINANCEIRO ===
with tabs[1]:
    st.subheader("📊 Meu Painel Financeiro")
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    if not meus.empty:
        meus["total_r$"] = meus["horas"] * meus["valor_hora_historico"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Horas Totais", f"{meus['horas'].sum():.1f}h")
        c2.metric("Valor Acumulado", f"R$ {meus['total_r$'].sum():,.2f}")
        c3.metric("Lançamentos", len(meus))
        st.dataframe(meus[['data_registro', 'projeto', 'horas', 'total_r$', 'status_aprovaca', 'status_pagamento']], use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum lançamento encontrado.")

# --- ABAS ADMIN ---
if is_user_admin:
    with tabs[2]: # Admin Geral
        st.subheader("🛡️ Gestão de Aprovações")
        df_edit = st.data_editor(df_lan, use_container_width=True, hide_index=True,
                                 column_config={"status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Negado"])})
        if st.button("💾 Sincronizar Aprovações"):
            with conn.session as s:
                for r in df_edit.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h WHERE id = :id"), {"s": r.status_aprovaca, "h": r.horas, "id": r.id})
                s.commit()
            st.rerun()

    with tabs[3]: # Pagamentos
        st.subheader("💸 Controle Financeiro")
        df_pag = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
        if not df_pag.empty:
            df_pag['total_r$'] = df_pag['horas'] * df_pag['valor_hora_historico']
            comp = st.selectbox("Competência:", sorted(df_pag['competencia'].unique(), reverse=True))
            df_m = df_pag[df_pag['competencia'] == comp]
            df_pago = st.data_editor(df_m[['id', 'colaborador_email', 'projeto', 'total_r$', 'status_pagamento']], use_container_width=True, hide_index=True,
                                     column_config={"status_pagamento": st.column_config.SelectboxColumn("Status", options=["Em aberto", "Pago", "Parcial"])})
            if st.button("💰 Confirmar Pagamentos"):
                with conn.session as s:
                    for r in df_pago.itertuples():
                        s.execute(text("UPDATE lancamentos SET status_pagamento = :sp WHERE id = :id"), {"sp": r.status_pagamento, "id": r.id})
                    s.commit()
                st.rerun()

    with tabs[4]: # BI
        st.subheader("📈 BI e Custos")
        df_bi = df_lan.copy()
        df_bi["custo"] = df_bi["horas"] * df_bi["valor_hora_historico"]
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        with c2:
            st.write("**Horas por Colaborador**")
            st.bar_chart(df_bi.groupby("colaborador_email")["horas"].sum())

    with tabs[5]: # Configurações (AQUI ADICIONAMOS A GESTÃO DE PROJETOS)
        st.subheader("⚙️ Configurações do Sistema")
        c1, c2 = st.columns(2)
        
        with c1:
            st.write("👥 **Usuários e Admins**")
            new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    for r in new_u.itertuples():
                        s.execute(text("""INSERT INTO usuarios (email, valor_hora, senha, funcao, is_admin) 
                                         VALUES (:e, :v, :s, :f, :a) 
                                         ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, funcao=:f, is_admin=:a"""), 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha, "f": r.funcao, "a": r.is_admin})
                    s.commit()
                st.rerun()

        with c2:
            st.write("📁 **Gestão de Projetos**")
            new_p = st.data_editor(df_projs, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    s.execute(text("DELETE FROM projetos")) # Projetos não têm dependências, pode-se usar delete.
                    for r in new_p.itertuples():
                        if r.nome: s.execute(text("INSERT INTO projetos (nome) VALUES (:n)"), {"n": r.nome})
                    s.commit()
                st.rerun()
        
        st.divider()
        st.write("🏦 **Dados Bancários**")
        df_b = get_bancos()
        new_b = st.data_editor(df_b, num_rows="dynamic", hide_index=True)
        if st.button("Salvar Dados Bancários"):
            with conn.session as s:
                for r in new_b.itertuples():
                    s.execute(text("""INSERT INTO dados_bancarios (colaborador_email, banco_nome, banco_numero, agencia, conta, chave_pix) 
                                     VALUES (:e, :bn, :bnum, :ag, :ct, :pix) 
                                     ON CONFLICT (colaborador_email) DO UPDATE SET banco_nome=:bn, banco_numero=:bnum, agencia=:ag, conta=:ct, chave_pix=:pix"""),
                              {"e": r.colaborador_email, "bn": r.banco_nome, "bnum": r.banco_numero, "ag": r.agencia, "ct": r.conta, "pix": r.chave_pix})
                s.commit()
            st.rerun()