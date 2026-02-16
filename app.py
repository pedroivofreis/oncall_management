import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io
from sqlalchemy import text

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="OnCall Humana - Enterprise", layout="wide", page_icon="🛡️")

# CONEXÃO COM RETRY
def get_connection():
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0)
        return c
    except:
        st.error("Erro ao acordar o banco. Verifique o status no Neon.")
        st.stop()

conn = get_connection()

# --- CARREGAMENTO DE DADOS ---
def get_all_data(): return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)
def get_config_users(): return conn.query("SELECT * FROM usuarios", ttl=0)
def get_config_projs(): return conn.query("SELECT * FROM projetos", ttl=0)
def get_bancos(): return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# --- LOGIN ---
df_u_login = get_config_users()
dict_users = {row.email: {"valor": float(row.valor_hora), "senha": str(row.senha)} for row in df_u_login.itertuples()}
ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.stop()

# --- VARIÁVEIS ---
df_lan = get_all_data()
lista_projetos = get_config_projs()['nome'].tolist()
lista_funcoes = ["Front", "Back", "Projetos", "QA", "Dados", "Full Stack"]

# --- INTERFACE EM ABAS ---
tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel", "🛡️ Aprovações", "💸 Pagamentos", "📈 BI", "⚙️ Configurações"])

# === ABA 1: LANÇAMENTOS (INDIVIDUAL + MASSA) ===
with tabs[0]:
    with st.expander("📥 Importar registros via Excel (.xlsx)"):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=["projeto", "horas", "data", "tipo", "descricao"]).to_excel(writer, index=False)
        st.download_button("📂 Baixar Modelo", data=buffer.getvalue(), file_name="modelo.xlsx")
        up_file = st.file_uploader("Upload", type=["xlsx"], label_visibility="collapsed")
        if up_file and st.button("🚀 Confirmar Importação"):
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
        desc = st.text_input("Descrição")
        if st.form_submit_button("🚀 Gravar"):
            with conn.session as s:
                s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                          {"id": str(uuid.uuid4()), "e": user_email, "p": p, "h": h, "c": d.strftime("%Y-%m"), "t": t, "d": desc, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Gravado!"); time.sleep(1); st.rerun()

# === ABA 3: APROVAÇÕES (ADMIN) ===
with tabs[2]:
    if user_email in ADMINS:
        st.subheader("🛡️ Painel de Aprovação")
        # Editor com colunas específicas para aprovação
        df_adm = st.data_editor(df_lan, use_container_width=True, hide_index=True, 
                                column_config={"status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Negado"])})
        if st.button("💾 Salvar Aprovações"):
            with conn.session as s:
                for r in df_adm.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h WHERE id = :id"), {"s": r.status_aprovaca, "h": r.horas, "id": r.id})
                s.commit()
            st.success("Status atualizados!"); st.rerun()

# === ABA 4: PAGAMENTOS (GESTOR FINANCEIRO) ===
with tabs[3]:
    if user_email in ADMINS:
        st.subheader("💸 Fechamento de Competência")
        df_pag = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
        if not df_pag.empty:
            df_pag['total_r$'] = df_pag['horas'] * df_lan['valor_hora_historico']
            competencias = sorted(df_pag['competencia'].unique(), reverse=True)
            sel_comp = st.selectbox("Mês de Referência:", competencias)
            
            df_mes = df_pag[df_pag['competencia'] == sel_comp]
            st.write(f"Total a pagar em {sel_comp}: R$ {df_mes['total_r$'].sum():,.2f}")
            
            # Gerenciar pagamento linha a linha ou em massa
            df_final = st.data_editor(df_mes[['id', 'colaborador_email', 'projeto', 'total_r$', 'status_pagamento']], 
                                      use_container_width=True, hide_index=True,
                                      column_config={"status_pagamento": st.column_config.SelectboxColumn("Pagamento", options=["Em aberto", "Pago", "Parcial"])})
            
            if st.button("💰 Confirmar Pagamentos"):
                with conn.session as s:
                    for r in df_final.itertuples():
                        s.execute(text("UPDATE lancamentos SET status_pagamento = :sp WHERE id = :id"), {"sp": r.status_pagamento, "id": r.id})
                    s.commit()
                st.success("Financeiro atualizado!"); st.rerun()

# === ABA 6: CONFIGURAÇÕES (RESOLVENDO O ERRO DE INTEGRIDADE) ===
with tabs[5]:
    if user_email in ADMINS:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("👥 Usuários e Funções")
            # Usando UPSERT para não deletar e quebrar o banco
            new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Usuários"):
                with conn.session as s:
                    for r in new_u.itertuples():
                        s.execute(text("INSERT INTO usuarios (email, valor_hora, senha, funcao) VALUES (:e, :v, :s, :f) ON CONFLICT (email) DO UPDATE SET valor_hora = :v, senha = :s, funcao = :f"), 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha, "f": r.funcao})
                    s.commit()
                st.success("Usuários sincronizados!"); st.rerun()
        
        with c2:
            st.subheader("🏦 Dados Bancários")
            df_b = get_bancos()
            new_b = st.data_editor(df_b, num_rows="dynamic", hide_index=True)
            if st.button("Salvar Bancos"):
                with conn.session as s:
                    for r in new_b.itertuples():
                        s.execute(text("INSERT INTO dados_bancarios (colaborador_email, banco_nome, banco_numero, agencia, conta, chave_pix) VALUES (:e, :bn, :bnum, :ag, :ct, :pix) ON CONFLICT (colaborador_email) DO UPDATE SET banco_nome=:bn, banco_numero=:bnum, agencia=:ag, conta=:ct, chave_pix=:pix"),
                                  {"e": r.colaborador_email, "bn": r.banco_nome, "bnum": r.banco_numero, "ag": r.agencia, "ct": r.conta, "pix": r.chave_pix})
                    s.commit()
                st.success("Dados bancários salvos!"); st.rerun()