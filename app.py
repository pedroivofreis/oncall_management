import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import uuid
import time
import io
from sqlalchemy import text

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="OnCall Humana - Master v6.0", layout="wide", page_icon="🛡️")

# --- 2. CONEXÃO COM O BANCO NEON ---
def get_connection():
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0) 
        return c
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: {e}")
        st.stop()

conn = get_connection()

# --- 3. LÓGICA DE TEMPO (HH.MM -> DECIMAL) ---
def convert_to_decimal_hours(pseudo_hour):
    """
    Transforma 2.50 (2h 50min) em ~2.83 (decimal para cálculo financeiro).
    """
    try:
        val_str = f"{float(pseudo_hour):.2f}"
        h_part, m_part = map(int, val_str.split('.'))
        return h_part + (m_part / 60)
    except:
        return 0.0

# --- 4. CARREGAMENTO DE DADOS ---
def get_all_data(): return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)
def get_config_users(): return conn.query("SELECT * FROM usuarios", ttl=0)
def get_config_projs(): return conn.query("SELECT * FROM projetos", ttl=0)
def get_bancos(): return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# --- 5. LOGIN E PERMISSÕES ---
df_u_login = get_config_users()
dict_users = {row.email: {
    "valor": float(row.valor_hora), 
    "senha": str(row.senha), 
    "is_admin": bool(getattr(row, 'is_admin', False)) 
} for row in df_u_login.itertuples()}

SUPER_ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("👤 Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário no menu lateral.")
    st.stop()

senha_input = st.sidebar.text_input("🔑 Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.warning("Aguardando senha correta...")
    st.stop()

is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

# --- 6. NAVEGAÇÃO PERSISTENTE (SIDEBAR) ---
st.sidebar.divider()
st.sidebar.subheader("📍 Navegação")
menu = ["📝 Lançamentos", "📊 Meu Painel", "🛡️ Admin Aprovações", "💸 Pagamentos", "📈 BI Estratégico", "⚙️ Configurações"] if is_user_admin else ["📝 Lançamentos", "📊 Meu Painel"]
escolha = st.sidebar.radio("Ir para:", menu)

# --- 7. CARREGAMENTO GLOBAL ---
df_lan = get_all_data()
df_projs = get_config_projs()
df_banc = get_bancos()
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação"]
colaboradores = sorted(df_lan['colaborador_email'].unique())

# === ABA: LANÇAMENTOS ===
if escolha == "📝 Lançamentos":
    st.subheader("📝 Registro Individual")
    st.caption("Nota: Use o formato HH.MM (Ex: 1.30 para 1 hora e 30 minutos)")
    with st.form("f_ind", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        p = c1.selectbox("Projeto", lista_projetos)
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Apoio"])
        d = c3.date_input("Data", datetime.now())
        h = st.number_input("Horas (HH.MM)", min_value=0.0, step=0.01, format="%.2f")
        desc = st.text_input("Descrição do Trabalho")
        if st.form_submit_button("🚀 Gravar no Banco"):
            with conn.session as s:
                s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                          {"id": str(uuid.uuid4()), "e": user_email, "p": p, "h": h, "c": d.strftime("%Y-%m"), "t": t, "d": desc, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Lançamento realizado!"); time.sleep(0.5); st.rerun()

# === ABA: MEU PAINEL (RESTABELECIDO) ===
elif escolha == "📊 Meu Painel":
    st.subheader(f"📊 Painel Financeiro - {user_email}")
    
    # Filtros de Data
    c_f1, c_f2 = st.columns(2)
    data_ini = c_f1.date_input("Início:", datetime.now() - timedelta(days=30))
    data_fim = c_f2.date_input("Fim:", datetime.now())
    
    df_m = df_lan[df_lan["colaborador_email"] == user_email].copy()
    df_m['data_registro'] = pd.to_datetime(df_m['data_registro']).dt.date
    df_m = df_m[(df_m['data_registro'] >= data_ini) & (df_m['data_registro'] <= data_fim)]
    
    if not df_m.empty:
        df_m['h_dec'] = df_m['horas'].apply(convert_to_decimal_hours)
        df_m['r$'] = df_m['h_dec'] * df_m['valor_hora_historico']
        
        # Scorecards Pessoais
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Pendente (h)", f"{df_m[df_m['status_aprovaca'] == 'Pendente']['horas'].sum():.2f}")
        s2.metric("Aprovado (h)", f"{df_m[df_m['status_aprovaca'] == 'Aprovado']['horas'].sum():.2f}")
        s3.metric("Pago (h)", f"{df_m[df_m['status_pagamento'] == 'Pago']['horas'].sum():.2f}")
        s4.metric("Total (R$)", f"R$ {df_m['r$'].sum():,.2f}")
        
        st.dataframe(df_m[['descricao', 'data_registro', 'projeto', 'horas', 'r$', 'status_aprovaca', 'status_pagamento']], 
                     use_container_width=True, hide_index=True, 
                     column_config={"r$": st.column_config.NumberColumn("Valor", format="R$ %.2f"), "horas": "HH.MM"})
    else:
        st.info("Sem dados no período.")

# === ABA: ADMIN APROVAÇÕES (DUAS TABELAS & FILTROS) ===
elif escolha == "🛡️ Admin Aprovações":
    st.subheader("🛡️ Central Admin - Gestão Bipartida")
    
    # IMPORTAÇÃO EM MASSA (O QUE A CLAU USA)
    with st.expander("📥 Importar do Excel (Copy/Paste)"):
        st.write("Colunas: **Data | Projeto | E-mail | Horas (HH.MM) | Tipo | Descrição**")
        cola = st.text_area("Cole as linhas:")
        if cola and st.button("🚀 Processar e Gravar"):
            try:
                df_p = pd.read_csv(io.StringIO(cola), sep='\t', names=["data", "proj", "mail", "hrs", "tipo", "desc"])
                with conn.session as s:
                    for r in df_p.itertuples():
                        v = dict_users.get(r.mail, {}).get("valor", 0)
                        comp = pd.to_datetime(r.data, dayfirst=True).strftime("%Y-%m")
                        s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                                  {"id": str(uuid.uuid4()), "e": r.mail, "p": r.proj, "h": r.hrs, "c": comp, "t": r.tipo, "d": r.desc, "v": v})
                    s.commit()
                st.success("Importado!"); time.sleep(1); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

    st.divider()
    
    # --- TABELA 1: PENDENTES ---
    st.write("### 🕒 Fila de Avaliação (Pendentes)")
    f_p = st.selectbox("Filtrar por Colaborador (Pendente):", ["Todos"] + colaboradores, key="fp")
    df_p = df_lan[df_lan['status_aprovaca'] == 'Pendente'].copy()
    if f_p != "Todos": df_p = df_p[df_p['colaborador_email'] == f_p]
    
    df_p = df_p[['descricao', 'colaborador_email', 'data_registro', 'projeto', 'horas', 'id']]
    df_p.insert(0, "✅", False)
    df_p.insert(1, "🗑️", False)
    
    ed_p = st.data_editor(df_p, use_container_width=True, hide_index=True, key="ed_p",
                          column_config={"✅": st.column_config.CheckboxColumn("Aprovar?"), "🗑️": st.column_config.CheckboxColumn("Excluir?")})
    
    c1, c2 = st.columns(2)
    if c1.button("✔️ APROVAR MARCADOS", use_container_width=True):
        ids = ed_p[ed_p["✅"] == True]["id"].tolist()
        if ids:
            with conn.session as s:
                s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Aprovado' WHERE id IN :ids"), {"ids": tuple(ids)})
                s.commit()
            st.rerun()
    if c2.button("🔥 EXCLUIR MARCADOS", type="primary", use_container_width=True):
        ids = ed_p[ed_p["🗑️"] == True]["id"].tolist()
        if ids:
            with conn.session as s:
                s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": tuple(ids)})
                s.commit()
            st.rerun()

    st.divider()
    
    # --- TABELA 2: APROVADOS (EDIÇÃO) ---
    st.write("### ✅ Histórico de Aprovados (Ajustes)")
    f_a = st.selectbox("Filtrar por Colaborador (Aprovado):", ["Todos"] + colaboradores, key="fa")
    df_a = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    if f_a != "Todos": df_a = df_a[df_a['colaborador_email'] == f_a]
    
    df_a = df_a[['descricao', 'colaborador_email', 'data_registro', 'projeto', 'horas', 'status_aprovaca', 'id']]
    ed_a = st.data_editor(df_a, use_container_width=True, hide_index=True, key="ed_a",
                          column_config={"status_aprovaca": st.column_config.SelectboxColumn("Mudar Status", options=["Aprovado", "Pendente", "Negado"])})
    
    if st.button("💾 Salvar Edições nos Aprovados"):
        with conn.session as s:
            for r in ed_a.itertuples():
                s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h, descricao = :d WHERE id = :id"), 
                         {"s": r.status_aprovaca, "h": r.horas, "d": r.descricao, "id": r.id})
            s.commit()
        st.rerun()

# === ABA: PAGAMENTOS (DRILL-DOWN & R$) ===
elif escolha == "💸 Pagamentos":
    st.subheader("💸 Consolidação de Pagamentos")
    df_pay = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
    if not df_pay.empty:
        df_pay['h_dec'] = df_pay['horas'].apply(convert_to_decimal_hours)
        df_pay['r$'] = df_pay['h_dec'] * df_pay['valor_hora_historico']
        
        df_g = df_pay.groupby(['competencia', 'colaborador_email']).agg({'r$': 'sum', 'horas': 'sum'}).reset_index()
        for idx, row in df_g.iterrows():
            with st.expander(f"📅 {row['competencia']} | 👤 {row['colaborador_email']} | R$ {row['r$']:,.2f}"):
                det = df_pay[(df_pay['competencia'] == row['competencia']) & (df_pay['colaborador_email'] == row['colaborador_email'])]
                st.dataframe(det[['descricao', 'data_registro', 'projeto', 'horas', 'r$']], use_container_width=True, hide_index=True,
                             column_config={"r$": st.column_config.NumberColumn("R$", format="R$ %.2f")})
                n_s = st.selectbox("Mudar Status", ["Em aberto", "Pago", "Parcial"], key=f"pay_{idx}")
                if st.button(f"Confirmar {idx}"):
                    with conn.session as s:
                        s.execute(text("UPDATE lancamentos SET status_pagamento = :s WHERE competencia = :c AND colaborador_email = :e"), {"s": n_s, "c": row['competencia'], "e": row['colaborador_email']})
                        s.commit()
                    st.rerun()

# === ABA: BI ESTRATÉGICO ===
elif escolha == "📈 BI Estratégico":
    st.subheader("📈 Inteligência de Custos")
    df_bi = df_lan.copy()
    df_bi['h_dec'] = df_bi['horas'].apply(convert_to_decimal_hours)
    df_bi["custo"] = df_bi['h_dec'] * df_bi["valor_hora_historico"]
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Horas Totais (HH.MM)", f"{df_bi['horas'].sum():.2f}")
    m2.metric("Custo Total (R$)", f"R$ {df_bi['custo'].sum():,.2f}")
    m3.metric("Lançamentos", len(df_bi))
    
    c1, c2 = st.columns(2)
    with c1: st.write("**Custo por Projeto**"); st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
    with c2: st.write("**Esforço por Tipo**"); st.bar_chart(df_bi.groupby("tipo")["horas"].sum())

# === ABA: CONFIGURAÇÕES ===
elif escolha == "⚙️ Configurações":
    st.subheader("⚙️ Configurações do Sistema")
    st.write("🏦 **Dados Bancários**")
    new_b = st.data_editor(df_banc, num_rows="dynamic", hide_index=True)
    if st.button("💾 Salvar Bancos"):
        with conn.session as s:
            for r in new_b.itertuples():
                s.execute(text("INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) VALUES (:e, :b, :t, :c) ON CONFLICT (colaborador_email) DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c"), {"e": r.colaborador_email, "b": r.banco, "t": r.tipo_chave, "c": r.chave_pix})
            s.commit()
    
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.write("👥 **Usuários/Admin**")
        new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
        if st.button("💾 Salvar Usuários"):
            with conn.session as s:
                for r in new_u.itertuples():
                    s.execute(text("INSERT INTO usuarios (email, valor_hora, senha, is_admin) VALUES (:e, :v, :s, :a) ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a"), {"e": r.email, "v": r.valor_hora, "s": r.senha, "a": r.is_admin})
                s.commit()
            st.rerun()

# --- FOOTER ---
st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>OnCall Humana by Pedro Reis | v6.0 Sentinel</p>", unsafe_allow_html=True)