import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io
from sqlalchemy import text

# --- 1. CONFIGURAÇÃO (PRIMEIRA LINHA SEMPRE) ---
st.set_page_config(page_title="OnCall Humana - Master Pro", layout="wide", page_icon="🛡️")

# --- 2. CONEXÃO COM O BANCO (AUTO-DESPERTAR) ---
def get_connection():
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0) # Acorda o banco do modo 'Idle'
        return c
    except:
        st.error("Erro ao conectar ao banco Neon. Verifique o console.")
        st.stop()

conn = get_connection()

# --- 3. CARREGAMENTO DE DADOS ---
def get_all_data(): return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)
def get_config_users(): return conn.query("SELECT * FROM usuarios", ttl=0)
def get_config_projs(): return conn.query("SELECT * FROM projetos", ttl=0)
def get_bancos(): return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# --- 4. LOGIN E PERMISSÕES (PEDRO E CLAU) ---
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

is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

# --- 5. CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
df_projs = get_config_projs()
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação"]

# --- 6. INTERFACE EM ABAS (VISÃO 100%) ---
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
        if up_file and st.button("🚀 Confirmar Importação"):
            df_m = pd.read_excel(up_file)
            with conn.session as s:
                for r in df_m.itertuples():
                    s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                              {"id": str(uuid.uuid4()), "e": user_email, "p": r.projeto, "h": r.horas, "c": pd.to_datetime(r.data).strftime("%Y-%m"), "t": r.tipo, "d": r.descricao, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Dados importados!"); time.sleep(1); st.rerun()

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

# === ABA 3: ADMIN (BOTÕES DE EXCLUSÃO CIRÚRGICA) ===
if is_user_admin:
    with tabs[2]:
        st.subheader("🛡️ Gestão de Lançamentos")
        df_adm_view = df_lan.copy()
        df_adm_view.insert(0, "🗑️", False) # Coluna para lixeira
        
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

    # === ABA 5: BI ESTRATÉGICO (VISÃO 212+ LINHAS) ===
    with tabs[4]:
        st.subheader("📈 BI Estratégico")
        df_bi = df_lan.copy()
        df_bi["custo"] = df_bi["horas"] * df_bi["valor_hora_historico"]
        
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Linhas no Banco", len(df_bi)) # Conferência em tempo real
        s2.metric("Horas Totais", f"{df_bi['horas'].sum():.1f}h")
        s3.metric("Custo Total", f"R$ {df_bi['custo'].sum():,.2f}")
        s4.metric("A Receber (Aprovado)", f"R$ {df_bi[df_bi['status_aprovaca']=='Aprovado']['custo'].sum():,.2f}")
        
        st.bar_chart(df_bi.groupby("projeto")["custo"].sum())

    # === ABA 6: CONFIGURAÇÕES (UPSERT - SEM ERRO DE INTEGRIDADE) ===
    with tabs[5]:
        st.subheader("⚙️ Configurações Master")
        c1, c2 = st.columns(2)
        with c1:
            st.write("👥 **Usuários e Admins**")
            new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    for r in new_u.itertuples():
                        # O comando abaixo atualiza se existir e insere se não existir
                        s.execute(text("""
                            INSERT INTO usuarios (email, valor_hora, senha, funcao, is_admin) 
                            VALUES (:e, :v, :s, :f, :a) 
                            ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, funcao=:f, is_admin=:a
                        """), {"e": r.email, "v": r.valor_hora, "s": r.senha, "f": r.funcao, "a": r.is_admin})
                    s.commit()
                st.success("Usuários salvos!"); st.rerun()
        with c2:
            st.write("📁 **Gestão de Projetos**")
            new_p = st.data_editor(df_projs, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Projetos"):
                with conn.session as s:
                    for r in new_p.itertuples():
                        s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
                    s.commit()
                st.success("Projetos salvos!"); st.rerun()

# --- FOOTER ---
st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>by Pedro Reis | Versão 3.0.6 Enterprise</p>", unsafe_allow_html=True)