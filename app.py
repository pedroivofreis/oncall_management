import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io
from sqlalchemy import text

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="OnCall Humana - Master Pro", layout="wide", page_icon="🛡️")

# --- 2. CONEXÃO COM O BANCO (AUTO-DESPERTAR) ---
def get_connection():
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0)
        return c
    except:
        st.error("Erro ao conectar ao banco Neon. Verifique o status 'Active' no Console.")
        st.stop()

conn = get_connection()

# --- 3. FUNÇÕES DE CARREGAMENTO (SEM CACHE PARA EVITAR PERDA) ---
def get_all_data(): return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)
def get_config_users(): return conn.query("SELECT * FROM usuarios", ttl=0)
def get_config_projs(): return conn.query("SELECT * FROM projetos", ttl=0)
def get_bancos(): return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# --- 4. LOGIN E SEGURANÇA DE ACESSO ---
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
    st.info("👈 Selecione seu usuário para entrar.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.error("Senha incorreta.")
    st.stop()

# Definição de Permissão
is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

# --- 5. CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
df_projs = get_config_projs()
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação"]

# --- 6. INTERFACE EM ABAS (DINÂMICA) ---
if is_user_admin:
    tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel", "🛡️ Admin Aprovações", "💸 Pagamentos", "📈 BI Estratégico", "⚙️ Configurações"])
else:
    tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel"])

# === ABA 1: LANÇAMENTOS (INDIVIDUAL + MASSA) ===
with tabs[0]:
    st.subheader("📝 Registro de Atividades")
    
    with st.expander("📥 Importação em Massa (Excel .xlsx)"):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=["projeto", "horas", "data", "tipo", "descricao"]).to_excel(writer, index=False)
        st.download_button("📂 Baixar Modelo .xlsx", data=buffer.getvalue(), file_name="modelo_oncall.xlsx")
        
        up_file = st.file_uploader("Upload", type=["xlsx"], label_visibility="collapsed")
        if up_file and st.button("🚀 Confirmar Importação em Massa"):
            df_m = pd.read_excel(up_file)
            with conn.session as s:
                for r in df_m.itertuples():
                    s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                              {"id": str(uuid.uuid4()), "e": user_email, "p": r.projeto, "h": r.horas, "c": pd.to_datetime(r.data).strftime("%Y-%m"), "t": r.tipo, "d": r.descricao, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Dados importados com sucesso!"); time.sleep(1); st.rerun()

    with st.form("f_ind", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        p = c1.selectbox("Projeto", lista_projetos)
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "Reunião", "QA", "Banco de Dados", "Dados"])
        d = c3.date_input("Data", datetime.now())
        h = st.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_input("O que você desenvolveu hoje?")
        if st.form_submit_button("🚀 Gravar Lançamento"):
            with conn.session as s:
                s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                          {"id": str(uuid.uuid4()), "e": user_email, "p": p, "h": h, "c": d.strftime("%Y-%m"), "t": t, "d": desc, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Gravado com sucesso!"); time.sleep(1); st.rerun()

# === ABA 2: MEU PAINEL (VISÃO COLABORADOR) ===
with tabs[1]:
    st.subheader("📊 Meu Painel Financeiro")
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    if not meus.empty:
        meus["total_r$"] = meus["horas"] * meus["valor_hora_historico"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Minhas Horas", f"{meus['horas'].sum():.1f}h")
        c2.metric("Valor Acumulado", f"R$ {meus['total_r$'].sum():,.2f}")
        c3.metric("Lançamentos", len(meus))
        st.dataframe(meus[['data_registro', 'projeto', 'horas', 'total_r$', 'status_aprovaca', 'status_pagamento']], use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum lançamento encontrado.")

# --- SEÇÃO EXCLUSIVA ADMIN ---
if is_user_admin:
    # === ABA 3: ADMIN APROVAÇÕES (LÓGICA SEGURA DE EDIÇÃO E EXCLUSÃO) ===
    with tabs[2]:
        st.subheader("🛡️ Gestão e Aprovação")
        st.info("💡 Para apagar: marque a lixeira 🗑️ e clique em 'Excluir Selecionados'. Para editar, mude o valor e clique em 'Sincronizar'.")
        
        df_adm_view = df_lan.copy()
        df_adm_view.insert(0, "🗑️", False)
        
        df_adm_ed = st.data_editor(df_adm_view, use_container_width=True, hide_index=True,
                                 column_config={
                                     "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Negado"]),
                                     "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos),
                                     "🗑️": st.column_config.CheckboxColumn("Excluir?")
                                 })
        
        c1, c2 = st.columns(2)
        if c1.button("💾 Sincronizar Alterações"):
            with conn.session as s:
                for r in df_adm_ed.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h, projeto = :p WHERE id = :id"), 
                             {"s": r.status_aprovaca, "h": r.horas, "p": r.projeto, "id": r.id})
                s.commit()
            st.success("Banco de dados atualizado!"); time.sleep(1); st.rerun()
            
        if c2.button("🔥 EXCLUIR SELECIONADOS", type="primary"):
            ids_excluir = df_adm_ed[df_adm_ed["🗑️"] == True]["id"].tolist()
            if ids_excluir:
                with conn.session as s:
                    s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": tuple(ids_excluir)})
                    s.commit()
                st.success(f"{len(ids_excluir)} registros removidos!"); time.sleep(1); st.rerun()

    # === ABA 4: PAGAMENTOS (GESTOR FINANCEIRO) ===
    with tabs[3]:
        st.subheader("💸 Controle Financeiro")
        df_pag = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
        if not df_pag.empty:
            df_pag['total_r$'] = df_pag['horas'] * df_pag['valor_hora_historico']
            comp_sel = st.selectbox("Mês de Referência:", sorted(df_pag['competencia'].unique(), reverse=True))
            df_m = df_pag[df_pag['competencia'] == comp_sel]
            
            p1, p2, p3 = st.columns(3)
            p1.metric("A Pagar (Mês)", f"R$ {df_m[df_m['status_pagamento'] != 'Pago']['total_r$'].sum():,.2f}")
            p2.metric("Pago (Mês)", f"R$ {df_m[df_m['status_pagamento'] == 'Pago']['total_r$'].sum():,.2f}")
            
            df_pago = st.data_editor(df_m[['id', 'colaborador_email', 'projeto', 'total_r$', 'status_pagamento']], use_container_width=True, hide_index=True,
                                     column_config={"status_pagamento": st.column_config.SelectboxColumn("Pagamento", options=["Em aberto", "Pago", "Parcial"])})
            if st.button("💰 Confirmar Baixa"):
                with conn.session as s:
                    for r in df_pago.itertuples():
                        s.execute(text("UPDATE lancamentos SET status_pagamento = :sp WHERE id = :id"), {"sp": r.status_pagamento, "id": r.id})
                    s.commit()
                st.rerun()

    # === ABA 5: BI ESTRATÉGICO (VISÃO 100%) ===
    with tabs[4]:
        st.subheader("📈 BI Estratégico")
        df_bi = df_lan.copy()
        df_bi["custo"] = df_bi["horas"] * df_bi["valor_hora_historico"]
        
        # Filtros de BI
        sel_comp = st.multiselect("Filtrar Meses:", sorted(df_bi['competencia'].unique(), reverse=True))
        if sel_comp: df_bi = df_bi[df_bi['competencia'].isin(sel_comp)]
            
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Linhas no Banco", len(df_bi))
        s2.metric("Horas Totais", f"{df_bi['horas'].sum():.1f}h")
        s3.metric("Custo Total", f"R$ {df_bi['custo'].sum():,.2f}")
        s4.metric("Total Pago", f"R$ {df_bi[df_bi['status_pagamento'] == 'Pago']['custo'].sum():,.2f}")
        
        c1, c2 = st.columns(2)
        with c1: st.bar_chart(df_bi.groupby("projeto")["custo"].sum()); st.write("Custo por Projeto")
        with c2: st.bar_chart(df_bi.groupby("colaborador_email")["horas"].sum()); st.write("Horas por Colaborador")

    # === ABA 6: CONFIGURAÇÕES (MASTER) ===
    with tabs[5]:
        st.subheader("⚙️ Configurações")
        c1, c2 = st.columns(2)
        with c1:
            st.write("👥 **Usuários e Admins**")
            new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    for r in new_u.itertuples():
                        s.execute(text("INSERT INTO usuarios (email, valor_hora, senha, funcao, is_admin) VALUES (:e, :v, :s, :f, :a) ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, funcao=:f, is_admin=:a"), 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha, "f": r.funcao, "a": r.is_admin})
                    s.commit()
                st.rerun()
        with c2:
            st.write("📁 **Projetos**")
            new_p = st.data_editor(df_projs, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    s.execute(text("DELETE FROM projetos"))
                    for r in new_p.itertuples():
                        if r.nome: s.execute(text("INSERT INTO projetos (nome) VALUES (:n)"), {"n": r.nome})
                    s.commit()
                st.rerun()

# --- FOOTER ---
st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>by Pedro Reis | Versão 3.0.5 Enterprise</p>", unsafe_allow_html=True)