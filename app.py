import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io
from sqlalchemy import text

# --- 1. CONFIGURAÇÃO (PRIMEIRA LINHA) ---
st.set_page_config(page_title="OnCall Humana - Master 4.7", layout="wide", page_icon="🛡️")

# --- 2. CONEXÃO ---
def get_connection():
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0) 
        return c
    except:
        st.error("Erro ao conectar ao banco Neon.")
        st.stop()

conn = get_connection()

# --- 3. CARREGAMENTO ---
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
    st.stop()

is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

# --- 5. DADOS GLOBAIS ---
df_lan = get_all_data()
df_projs = get_config_projs()
df_banc = get_bancos()
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação"]

# --- 6. INTERFACE ---
tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel", "🛡️ Admin Aprovações", "💸 Pagamentos", "📈 BI Estratégico", "⚙️ Configurações"]) if is_user_admin else st.tabs(["📝 Lançamentos", "📊 Meu Painel"])

# === ABA 1: LANÇAMENTOS ===
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

# === ABA 2: MEU PAINEL (RESTAURADO) ===
with tabs[1]:
    st.subheader("📊 Meu Financeiro e Histórico")
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    if not meus.empty:
        meus["total_r$"] = meus["horas"] * meus["valor_hora_historico"]
        c1, c2 = st.columns(2)
        c1.metric("Minhas Horas Totais", f"{meus['horas'].sum():.1f}h")
        c2.metric("Meu Valor a Receber", f"R$ {meus['total_r$'].sum():,.2f}")
        st.dataframe(meus[['data_registro', 'projeto', 'horas', 'total_r$', 'status_aprovaca', 'status_pagamento', 'descricao']], use_container_width=True, hide_index=True)

if is_user_admin:
    # === ABA 3: ADMIN (LIXEIRA E EDIÇÃO) ===
    with tabs[2]:
        st.subheader("🛡️ Gestão de Aprovações")
        st.info("💡 Marque a 🗑️ e clique em 'Excluir Selecionados' para apagar permanentemente.")
        df_adm_v = df_lan.copy()
        df_adm_v.insert(0, "🗑️", False)
        df_ed = st.data_editor(df_adm_v, use_container_width=True, hide_index=True,
                               column_config={"status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Negado"]), "🗑️": st.column_config.CheckboxColumn("Excluir?")})
        c1, c2 = st.columns(2)
        if c1.button("💾 Sincronizar Alterações"):
            with conn.session as s:
                for r in df_ed.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h, projeto = :p WHERE id = :id"), {"s": r.status_aprovaca, "h": r.horas, "p": r.projeto, "id": r.id})
                s.commit()
            st.rerun()
        if c2.button("🔥 EXCLUIR SELECIONADOS", type="primary"):
            ids_x = df_ed[df_ed["🗑️"] == True]["id"].tolist()
            if ids_x:
                with conn.session as s:
                    s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": tuple(ids_x)})
                    s.commit()
                st.rerun()

    # === ABA 4: PAGAMENTOS (RESTAURADO) ===
    with tabs[3]:
        st.subheader("💸 Consolidação Financeira")
        df_ap = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
        if not df_ap.empty:
            df_ap['total_r$'] = df_ap['horas'] * df_ap['valor_hora_historico']
            df_g = df_ap.groupby(['competencia', 'colaborador_email']).agg({'total_r$': 'sum', 'horas': 'sum'}).reset_index()
            for idx, row in df_g.iterrows():
                with st.expander(f"📅 {row['competencia']} | 👤 {row['colaborador_email']} | R$ {row['total_r$']:,.2f}"):
                    det = df_ap[(df_ap['competencia'] == row['competencia']) & (df_ap['colaborador_email'] == row['colaborador_email'])]
                    st.table(det[['data_registro', 'projeto', 'horas', 'total_r$']])
                    st.selectbox("Status", ["Em aberto", "Pago", "Parcial"], key=f"pay_{idx}")

    # === ABA 5: BI (GRÁFICOS POR TIPO E PROJETO) ===
    with tabs[4]:
        st.subheader("📈 BI Estratégico")
        df_bi = df_lan.copy()
        df_bi["custo"] = df_bi["horas"] * df_bi["valor_hora_historico"]
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Linhas no Banco", len(df_bi))
        k2.metric("Horas Totais", f"{df_bi['horas'].sum():.1f}h")
        k3.metric("Custo Total", f"R$ {df_bi['custo'].sum():,.2f}")
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Horas por Tipo de Atividade**")
            st.bar_chart(df_bi.groupby("tipo")["horas"].sum())
        with c2:
            st.write("**Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
        
        st.write("**Ranking por Colaborador**")
        st.dataframe(df_bi.groupby("colaborador_email").agg({'horas': 'sum', 'custo': 'sum'}).sort_values('horas', ascending=False), use_container_width=True)

    # === ABA 6: CONFIGURAÇÕES (BANCOS RESTAURADO) ===
    with tabs[5]:
        st.subheader("⚙️ Configurações Master")
        st.write("🏦 **Dados Bancários para Pagamento**")
        new_b = st.data_editor(df_banc, num_rows="dynamic", hide_index=True)
        if st.button("Salvar Bancos"):
            with conn.session as s:
                for r in new_b.itertuples():
                    s.execute(text("INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) VALUES (:e, :b, :t, :c) ON CONFLICT (colaborador_email) DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c"), {"e": r.colaborador_email, "b": r.banco, "t": r.tipo_chave, "c": r.chave_pix})
                s.commit()
            st.success("Bancos Salvos!")
        
        c1, c2 = st.columns(2)
        with c1:
            st.write("👥 **Usuários e Admins**")
            new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    for r in new_u.itertuples():
                        s.execute(text("INSERT INTO usuarios (email, valor_hora, senha, is_admin) VALUES (:e, :v, :s, :a) ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a"), {"e": r.email, "v": r.valor_hora, "s": r.senha, "a": r.is_admin})
                    s.commit()
                st.rerun()
        with c2:
            st.write("📁 **Gestão de Projetos**")
            new_p = st.data_editor(df_projs, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    for r in new_p.itertuples():
                        s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
                    s.commit()
                st.rerun()

# --- FOOTER ---
st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>OnCall Humana by Pedro Reis | v4.7 Master Pro</p>", unsafe_allow_html=True)