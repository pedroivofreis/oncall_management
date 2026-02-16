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
        st.error("Erro ao conectar ao banco. Verifique o Neon.")
        st.stop()

conn = get_connection()

# --- 3. CARREGAMENTO DE DADOS ---
def get_all_data(): return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)
def get_config_users(): return conn.query("SELECT * FROM usuarios", ttl=0)
def get_config_projs(): return conn.query("SELECT * FROM projetos", ttl=0)
def get_bancos(): return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# --- 4. LOGIN ---
df_u_login = get_config_users()
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha), "funcao": str(row.funcao)} for row in df_u_login.itertuples()}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione o seu utilizador.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.stop()

# --- 5. VARIAVEIS GLOBAIS ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()
lista_funcoes = ["Front", "Back", "Projetos", "QA", "Dados", "Full Stack"]

# --- 6. INTERFACE ---
tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel", "🛡️ Aprovações", "💸 Pagamentos", "📈 BI", "⚙️ Configurações"])

# === ABA 1: LANÇAMENTOS ===
with tabs[0]:
    with st.expander("📥 Importar registros via Excel (.xlsx)"):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=["projeto", "horas", "data", "tipo", "descricao"]).to_excel(writer, index=False)
        st.download_button("📂 Baixar Modelo", data=buffer.getvalue(), file_name="modelo.xlsx")
        
        up_file = st.file_uploader("Upload", type=["xlsx"], label_visibility="collapsed")
        if up_file and st.button("🚀 Importar"):
            df_m = pd.read_excel(up_file)
            with conn.session as s:
                for r in df_m.itertuples():
                    s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                              {"id": str(uuid.uuid4()), "e": user_email, "p": r.projeto, "h": r.horas, "c": pd.to_datetime(r.data).strftime("%Y-%m"), "t": r.tipo, "d": r.descricao, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Importado!"); time.sleep(1); st.rerun()

    with st.form("f_ind", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        p = c1.selectbox("Projeto", lista_projetos)
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "Reunião", "QA", "Banco de Dados"])
        d = c3.date_input("Data", datetime.now())
        h = st.number_input("Horas", min_value=0.5, step=0.5)
        desc = st.text_input("O que foi feito?")
        if st.form_submit_button("🚀 Gravar"):
            with conn.session as s:
                s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                          {"id": str(uuid.uuid4()), "e": user_email, "p": p, "h": h, "c": d.strftime("%Y-%m"), "t": t, "d": desc, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Gravado!"); time.sleep(1); st.rerun()

# === ABA 3: APROVAÇÕES (ADMIN) ===
with tabs[2]:
    if user_email in ADMINS:
        st.subheader("🛡️ Aprovação de Horas")
        df_edit = st.data_editor(df_lan, use_container_width=True, hide_index=True)
        if st.button("💾 Sincronizar Aprovações"):
            with conn.session as s:
                for r in df_edit.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, projeto = :p, horas = :h WHERE id = :id"),
                             {"s": r.status_aprovaca, "p": r.projeto, "h": r.horas, "id": r.id})
                s.commit()
            st.rerun()

# === ABA 4: PAGAMENTOS (NOVA!) ===
with tabs[3]:
    if user_email in ADMINS:
        st.subheader("💸 Gestão de Pagamentos por Competência")
        df_aprovados = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
        df_aprovados['total_r$'] = df_aprovados['horas'] * df_aprovados['valor_hora_historico']
        
        comp_sel = st.selectbox("Selecione a Competência:", sorted(df_aprovados['competencia'].unique(), reverse=True))
        df_comp = df_aprovados[df_aprovados['competencia'] == comp_sel]
        
        # Agrupar por colaborador para ver o quanto pagar a cada um
        resumo_pag = df_comp.groupby('colaborador_email').agg({'horas': 'sum', 'total_r$': 'sum'}).reset_index()
        
        st.write(f"Resumo de {comp_sel}:")
        df_pag_final = st.data_editor(df_comp[['id', 'colaborador_email', 'projeto', 'horas', 'total_r$', 'status_pagamento']], use_container_width=True, hide_index=True)
        
        if st.button("✅ Confirmar Pagamentos Selecionados"):
            with conn.session as s:
                for r in df_pag_final.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_pagamento = :sp WHERE id = :id"), {"sp": r.status_pagamento, "id": r.id})
                s.commit()
            st.success("Status de pagamento atualizado!"); st.rerun()

# === ABA 6: CONFIGURAÇÕES (MASTER) ===
with tabs[5]:
    if user_email in ADMINS:
        c1, c2 = st.columns(2)
        with c1:
            st.write("👥 **Utilizadores e Funções**")
            new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Utilizadores"):
                with conn.session as s:
                    s.execute(text("DELETE FROM usuarios"))
                    for r in new_u.itertuples():
                        s.execute(text("INSERT INTO usuarios (email, valor_hora, senha, funcao) VALUES (:e, :v, :s, :f)"), 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha, "f": r.funcao})
                    s.commit()
                st.rerun()
        
        with c2:
            st.write("🏦 **Dados Bancários**")
            df_b = get_bancos()
            new_b = st.data_editor(df_b, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Dados Bancários"):
                with conn.session as s:
                    s.execute(text("DELETE FROM dados_bancarios"))
                    for r in new_b.itertuples():
                        s.execute(text("INSERT INTO dados_bancarios (colaborador_email, banco_nome, banco_numero, agencia, conta, chave_pix) VALUES (:e, :bn, :bnum, :ag, :ct, :pix)"),
                                  {"e": r.colaborador_email, "bn": r.banco_nome, "bnum": r.banco_numero, "ag": r.agencia, "ct": r.conta, "pix": r.chave_pix})
                    s.commit()
                st.rerun() 