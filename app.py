import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io
from sqlalchemy import text

# --- 1. CONFIGURAÇÃO (PRIMEIRA LINHA) ---
st.set_page_config(page_title="OnCall Humana - v4.6", layout="wide", page_icon="🛡️")

# --- 2. CONEXÃO COM O BANCO ---
def get_connection():
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0) 
        return c
    except:
        st.error("Erro ao conectar ao banco Neon.")
        st.stop()

conn = get_connection()

# --- 3. CARREGAMENTO DE DADOS (TTL=0 PARA DADO REAL) ---
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

SUPER_ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.error("Senha incorreta.")
    st.stop()

is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

# --- 5. CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
df_projs = get_config_projs()
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação"]

# --- 6. INTERFACE EM ABAS ---
labels = ["📝 Lançamentos", "📊 Meu Painel", "🛡️ Admin Aprovações", "💸 Pagamentos", "📈 BI Estratégico", "⚙️ Configurações"] if is_user_admin else ["📝 Lançamentos", "📊 Meu Painel"]
tabs = st.tabs(labels)

# === ABA 1: LANÇAMENTOS (UPLOAD SEGURO) ===
with tabs[0]:
    st.subheader("📝 Registro de Atividades")
    with st.expander("📥 Importação em Massa (.xlsx)"):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=["data", "projeto", "tipo", "horas", "descricao"]).to_excel(writer, index=False)
        st.download_button("📂 Baixar Modelo", data=buffer.getvalue(), file_name="modelo.xlsx")
        up_file = st.file_uploader("Upload", type=["xlsx"], label_visibility="collapsed")
        if up_file and st.button("🚀 Confirmar Importação"):
            df_m = pd.read_excel(up_file)
            with conn.session as s:
                for r in df_m.itertuples():
                    s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                              {"id": str(uuid.uuid4()), "e": user_email, "p": r.projeto, "h": r.horas, "c": pd.to_datetime(r.data).strftime("%Y-%m"), "t": r.tipo, "d": r.descricao, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Importado!"); time.sleep(0.5); st.rerun()

    with st.form("f_ind", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        p, t, d = c1.selectbox("Projeto", lista_projetos), c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Banco de Dados"]), c3.date_input("Data", datetime.now())
        h, desc = st.number_input("Horas", min_value=0.5, step=0.5), st.text_input("Descrição")
        if st.form_submit_button("🚀 Gravar"):
            with conn.session as s:
                s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                          {"id": str(uuid.uuid4()), "e": user_email, "p": p, "h": h, "c": d.strftime("%Y-%m"), "t": t, "d": desc, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Gravado!"); time.sleep(0.5); st.rerun()

# === ABA 2: MEU PAINEL (RESTABELECIDO) ===
with tabs[1]:
    st.subheader(f"📊 Painel de {user_email.split('@')[0].upper()}")
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    if not meus.empty:
        meus["total_r$"] = meus["horas"] * meus["valor_hora_historico"]
        c1, c2 = st.columns(2)
        c1.metric("Minhas Horas Totais", f"{meus['horas'].sum():.1f}h")
        c2.metric("Meu Valor Acumulado", f"R$ {meus['total_r$'].sum():,.2f}")
        st.dataframe(meus[['data_registro', 'projeto', 'horas', 'total_r$', 'status_aprovaca', 'status_pagamento', 'descricao']], use_container_width=True, hide_index=True)

# --- ADMIN SECTION ---
if is_user_admin:
    # === ABA 3: ADMIN (BOTÃO DE EXCLUSÃO CIRÚRGICA) ===
    with tabs[2]:
        st.subheader("🛡️ Gestão de Aprovações")
        st.metric("Total de Linhas no Banco (Real)", len(df_lan))
        
        df_adm_v = df_lan.copy()
        df_adm_v.insert(0, "🗑️", False)
        
        df_ed = st.data_editor(df_adm_v, use_container_width=True, hide_index=True,
                               column_config={"status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Negado"]), "🗑️": st.column_config.CheckboxColumn("Excluir?")})
        
        c1, c2 = st.columns(2)
        if c1.button("💾 Salvar Alterações"):
            with conn.session as s:
                for r in df_ed.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h, projeto = :p WHERE id = :id"), 
                             {"s": r.status_aprovaca, "h": r.horas, "p": r.projeto, "id": r.id})
                s.commit()
            st.success("Alterações salvas!"); time.sleep(0.5); st.rerun()
            
        if c2.button("🔥 EXCLUIR MARCADOS", type="primary"):
            ids_excluir = df_ed[df_ed["🗑️"] == True]["id"].tolist()
            if ids_excluir:
                with conn.session as s:
                    s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": tuple(ids_excluir)})
                    s.commit()
                st.success(f"{len(ids_excluir)} registros removidos!"); time.sleep(0.5); st.rerun()

    # === ABA 5: BI (SCORECARDS E GRÁFICOS FIXOS) ===
    with tabs[4]:
        st.subheader("📈 BI Estratégico")
        df_bi = df_lan.copy()
        df_bi["custo"] = df_bi["horas"] * df_bi["valor_hora_historico"]
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Registros", len(df_bi))
        k2.metric("Total Horas", f"{df_bi['horas'].sum():.1f}h")
        k3.metric("Custo Total", f"R$ {df_bi['custo'].sum():,.2f}")
        k4.metric("Status Pago", f"R$ {df_bi[df_bi['status_pagamento'] == 'Pago']['custo'].sum():,.2f}")
        
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.write("**Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        with col_g2:
            st.write("**Horas por Colaborador**")
            st.bar_chart(df_bi.groupby("colaborador_email")["horas"].sum())

    # === ABA 6: CONFIGURAÇÕES ===
    with tabs[5]:
        st.subheader("⚙️ Configurações Master")
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("👥 **Usuários e Admins**")
            new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    for r in new_u.itertuples():
                        s.execute(text("INSERT INTO usuarios (email, valor_hora, senha, is_admin) VALUES (:e, :v, :s, :a) ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a"), 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha, "a": r.is_admin})
                    s.commit()
                st.rerun()
        with c2:
            st.write("📁 **Projetos**")
            new_p = st.data_editor(df_projs, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    for r in new_p.itertuples():
                        s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
                    s.commit()
                st.rerun()

# --- FOOTER ---
st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>OnCall Humana by Pedro Reis | v4.6 Enterprise</p>", unsafe_allow_html=True)