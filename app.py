import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time
import io
from sqlalchemy import text

# --- 1. CONFIGURAÇÃO DA PÁGINA (ESTILO ENTERPRISE) ---
st.set_page_config(page_title="OnCall Humana - Master v5.1", layout="wide", page_icon="🛡️")

# --- 2. CONEXÃO COM O BANCO NEON (TRAVA DE SEGURANÇA) ---
def get_connection():
    try:
        c = st.connection("postgresql", type="sql")
        c.query("SELECT 1", ttl=0) # Wake-up call
        return c
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: {e}")
        st.stop()

conn = get_connection()

# --- 3. FUNÇÕES DE CARREGAMENTO (DADOS EM TEMPO REAL) ---
def get_all_data(): return conn.query("SELECT * FROM lancamentos ORDER BY data_registro DESC", ttl=0)
def get_config_users(): return conn.query("SELECT * FROM usuarios", ttl=0)
def get_config_projs(): return conn.query("SELECT * FROM projetos", ttl=0)
def get_bancos(): return conn.query("SELECT * FROM dados_bancarios", ttl=0)

# --- 4. LOGIN E CONTROLE DE NÍVEL DE ACESSO ---
df_u_login = get_config_users()
dict_users = {row.email: {
    "valor": float(row.valor_hora), 
    "senha": str(row.senha), 
    "is_admin": bool(getattr(row, 'is_admin', False)) 
} for row in df_u_login.itertuples()}

SUPER_ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

st.sidebar.title("🛡️ OnCall Humana")
user_email = st.sidebar.selectbox("Usuário:", ["..."] + list(dict_users.keys()))

if user_email == "...":
    st.info("👈 Selecione seu usuário para acessar o sistema.")
    st.stop()

senha_input = st.sidebar.text_input("Senha:", type="password")
if senha_input != dict_users[user_email]["senha"]:
    st.sidebar.error("Senha incorreta.")
    st.stop()

# Definição se o usuário logado pode ver as abas Master
is_user_admin = dict_users[user_email]["is_admin"] or user_email in SUPER_ADMINS

# --- 5. CARREGAMENTO GLOBAL DE DADOS ---
df_lan = get_all_data()
df_projs = get_config_projs()
df_banc = get_bancos()
lista_projetos = df_projs['nome'].tolist() if not df_projs.empty else ["Sustentação"]

# --- 6. INTERFACE EM ABAS (DINÂMICA POR PERFIL) ---
if is_user_admin:
    tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel", "🛡️ Admin Aprovações", "💸 Pagamentos", "📈 BI Estratégico", "⚙️ Configurações"])
else:
    tabs = st.tabs(["📝 Lançamentos", "📊 Meu Painel"])

# === ABA 1: LANÇAMENTOS (FORMULÁRIO + MODELO) ===
with tabs[0]:
    st.subheader("📝 Registro de Atividade")
    
    # Modelo para o pessoal saber a ordem (mesmo sem upload, serve de guia)
    with st.expander("📄 Guia de Colunas para Massa"):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=["data", "projeto", "usuario", "horas", "tipo", "descricao"]).to_excel(writer, index=False)
        st.download_button("📂 Baixar Planilha Modelo", data=buffer.getvalue(), file_name="modelo_oncall.xlsx")

    with st.form("f_ind", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        p = c1.selectbox("Projeto", lista_projetos)
        t = c2.selectbox("Tipo", ["Front-end", "Back-end", "Infra", "QA", "Dados", "Reunião", "Banco de Dados"])
        d = c3.date_input("Data", datetime.now())
        h = st.number_input("Horas Trabalhadas", min_value=0.5, step=0.5)
        desc = st.text_input("Descrição detalhada da entrega")
        
        if st.form_submit_button("🚀 Gravar Lançamento"):
            with conn.session as s:
                s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                          {"id": str(uuid.uuid4()), "e": user_email, "p": p, "h": h, "c": d.strftime("%Y-%m"), "t": t, "d": desc, "v": dict_users[user_email]["valor"]})
                s.commit()
            st.success("Gravado com sucesso!"); time.sleep(0.5); st.rerun()

# === ABA 2: MEU PAINEL (BI PESSOAL) ===
with tabs[1]:
    st.subheader(f"📊 Painel de {user_email.split('@')[0].upper()}")
    meus = df_lan[df_lan["colaborador_email"] == user_email].copy()
    if not meus.empty:
        meus["total_r$"] = meus["horas"] * meus["valor_hora_historico"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Minhas Horas Totais", f"{meus['horas'].sum():.1f}h")
        c2.metric("Meu Valor a Receber", f"R$ {meus['total_r$'].sum():,.2f}")
        c3.metric("Lançamentos", len(meus))
        st.dataframe(meus[['data_registro', 'projeto', 'horas', 'total_r$', 'status_aprovaca', 'status_pagamento', 'descricao']], use_container_width=True, hide_index=True)
    else:
        st.info("Ainda não há lançamentos registrados para sua conta.")

# --- SEÇÃO EXCLUSIVA PARA ADMINS (TRAVA MASTER) ---
if is_user_admin:
    # === ABA 3: ADMIN (COPIAR E COLAR + GESTÃO) ===
    with tabs[2]:
        st.subheader("🛡️ Central de Comando Admin")
        
        # FUNCIONALIDADE COPIAR E COLAR (O QUE VOCÊ PEDIU)
        with st.expander("📥 IMPORTAÇÃO RÁPIDA (Copiar e Colar do Excel)"):
            st.write("Ordem das colunas: **Data | Projeto | E-mail do Usuário | Horas | Tipo | Descrição**")
            cola_texto = st.text_area("Cole as linhas aqui:", height=200, placeholder="Ex: 16/02/2026	Humana	medico@email.com	4.5	Backend	Ajuste de Fluxo")
            
            if cola_texto:
                try:
                    df_paste = pd.read_csv(io.StringIO(cola_texto), sep='\t', names=["data", "projeto", "usuario", "horas", "tipo", "descricao"])
                    st.write("📋 Prévia dos dados identificados:")
                    st.dataframe(df_paste, use_container_width=True)
                    
                    if st.button("🚀 Confirmar e Gravar Tudo no Banco"):
                        with conn.session as s:
                            for r in df_paste.itertuples():
                                v_h = dict_users.get(r.usuario, {}).get("valor", 0)
                                comp_gen = pd.to_datetime(r.data, dayfirst=True).strftime("%Y-%m")
                                s.execute(text("INSERT INTO lancamentos (id, colaborador_email, projeto, horas, competencia, tipo, descricao, valor_hora_historico) VALUES (:id, :e, :p, :h, :c, :t, :d, :v)"),
                                          {"id": str(uuid.uuid4()), "e": r.usuario, "p": r.projeto, "h": r.horas, "c": comp_gen, "t": r.tipo, "d": r.descricao, "v": v_h})
                            s.commit()
                        st.success("Importação concluída com sucesso!"); time.sleep(1); st.rerun()
                except Exception as e:
                    st.error(f"Erro no processamento. Verifique se as colunas estão separadas por 'Tab'. Erro: {e}")

        st.divider()
        st.write("**Edição e Aprovação em Massa:**")
        
        # Botões de Ação Rápida que você gostou
        c_ap, c_neg = st.columns(2)
        if c_ap.button("✅ APROVAR TODOS PENDENTES", use_container_width=True):
            with conn.session as s:
                s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Aprovado' WHERE status_aprovaca = 'Pendente'"))
                s.commit()
            st.rerun()
        if c_neg.button("❌ REJEITAR TODOS PENDENTES", use_container_width=True):
            with conn.session as s:
                s.execute(text("UPDATE lancamentos SET status_aprovaca = 'Negado' WHERE status_aprovaca = 'Pendente'"))
                s.commit()
            st.rerun()

        # Editor Master com Lixeira
        df_adm_v = df_lan.copy()
        df_adm_v.insert(0, "🗑️", False)
        df_ed = st.data_editor(df_adm_v, use_container_width=True, hide_index=True,
                               column_config={
                                   "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Negado"]),
                                   "🗑️": st.column_config.CheckboxColumn("Excluir?")
                               })
        
        c_salvar, c_delete = st.columns(2)
        if c_salvar.button("💾 Sincronizar Alterações Manuais", use_container_width=True):
            with conn.session as s:
                for r in df_ed.itertuples():
                    s.execute(text("UPDATE lancamentos SET status_aprovaca = :s, horas = :h, projeto = :p WHERE id = :id"), {"s": r.status_aprovaca, "h": r.horas, "p": r.projeto, "id": r.id})
                s.commit()
            st.rerun()
        if c_delete.button("🔥 EXCLUIR MARCADOS", type="primary", use_container_width=True):
            ids_x = df_ed[df_ed["🗑️"] == True]["id"].tolist()
            if ids_x:
                with conn.session as s:
                    s.execute(text("DELETE FROM lancamentos WHERE id IN :ids"), {"ids": tuple(ids_x)})
                    s.commit()
                st.rerun()

    # === ABA 4: PAGAMENTOS (DRILL-DOWN COMPLETO) ===
    with tabs[3]:
        st.subheader("💸 Consolidação Financeira")
        df_ap = df_lan[df_lan['status_aprovaca'] == 'Aprovado'].copy()
        if not df_ap.empty:
            df_ap['total_r$'] = df_ap['horas'] * df_ap['valor_hora_historico']
            df_g = df_ap.groupby(['competencia', 'colaborador_email']).agg({'total_r$': 'sum', 'horas': 'sum'}).reset_index()
            
            for idx, row in df_g.iterrows():
                with st.expander(f"📅 {row['competencia']} | 👤 {row['colaborador_email']} | 💰 R$ {row['total_r$']:,.2f}"):
                    det = df_ap[(df_ap['competencia'] == row['competencia']) & (df_ap['colaborador_email'] == row['colaborador_email'])]
                    st.table(det[['data_registro', 'projeto', 'horas', 'total_r$']])
                    
                    status_atual = det['status_pagamento'].iloc[0] if 'status_pagamento' in det.columns else "Em aberto"
                    c_sel, c_btn = st.columns([3, 1])
                    novo_s = c_sel.selectbox(f"Mudar Status Pagamento ({idx})", ["Em aberto", "Pago", "Parcial"], 
                                             index=["Em aberto", "Pago", "Parcial"].index(status_atual if status_atual in ["Em aberto", "Pago", "Parcial"] else "Em aberto"))
                    if c_btn.button(f"Confirmar Baixa {idx}"):
                        with conn.session as s:
                            s.execute(text("UPDATE lancamentos SET status_pagamento = :s WHERE competencia = :c AND colaborador_email = :e AND status_aprovaca = 'Aprovado'"),
                                      {"s": novo_s, "c": row['competencia'], "e": row['colaborador_email']})
                            s.commit()
                        st.rerun()
        else:
            st.warning("Não há lançamentos aprovados para pagamento.")

    # === ABA 5: BI ESTRATÉGICO (MÉTRICAS E GRÁFICOS) ===
    with tabs[4]:
        st.subheader("📈 Inteligência de Custos")
        df_bi = df_lan.copy()
        df_bi["custo"] = df_bi["horas"] * df_bi["valor_hora_historico"]
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Linhas no Banco", len(df_bi))
        k2.metric("Horas Totais", f"{df_bi['horas'].sum():.1f}h")
        k3.metric("Custo Total Operacional", f"R$ {df_bi['custo'].sum():,.2f}")
        k4.metric("Já Pago", f"R$ {df_bi[df_bi['status_pagamento'] == 'Pago']['custo'].sum():,.2f}")
        
        cg1, cg2 = st.columns(2)
        with cg1:
            st.write("**Horas por Tipo de Atividade**")
            st.bar_chart(df_bi.groupby("tipo")["horas"].sum())
        with cg2:
            st.write("**Custo por Projeto**")
            st.bar_chart(df_bi.groupby("projeto")["custo"].sum())
            
        st.write("**Ranking por Colaborador**")
        st.dataframe(df_bi.groupby("colaborador_email").agg({'horas': 'sum', 'custo': 'sum'}).sort_values('horas', ascending=False), use_container_width=True)

    # === ABA 6: CONFIGURAÇÕES (USUÁRIOS, PROJETOS E BANCOS) ===
    with tabs[5]:
        st.subheader("⚙️ Configurações Master")
        
        st.write("🏦 **Dados Bancários e PIX**")
        new_banc = st.data_editor(df_banc, num_rows="dynamic", hide_index=True)
        if st.button("💾 Salvar Dados Bancários"):
            with conn.session as s:
                for r in new_banc.itertuples():
                    s.execute(text("INSERT INTO dados_bancarios (colaborador_email, banco, tipo_chave, chave_pix) VALUES (:e, :b, :t, :c) ON CONFLICT (colaborador_email) DO UPDATE SET banco=:b, tipo_chave=:t, chave_pix=:c"), 
                              {"e": r.colaborador_email, "b": r.banco, "t": r.tipo_chave, "c": r.chave_pix})
                s.commit()
            st.success("Dados bancários atualizados!")

        st.divider()
        c_u, c_p = st.columns(2)
        with c_u:
            st.write("👥 **Gestão de Usuários e Admins**")
            new_u = st.data_editor(df_u_login, num_rows="dynamic", hide_index=True)
            if st.button("💾 Salvar Usuários"):
                with conn.session as s:
                    for r in new_u.itertuples():
                        s.execute(text("INSERT INTO usuarios (email, valor_hora, senha, is_admin) VALUES (:e, :v, :s, :a) ON CONFLICT (email) DO UPDATE SET valor_hora=:v, senha=:s, is_admin=:a"), 
                                  {"e": r.email, "v": r.valor_hora, "s": r.senha, "a": r.is_admin})
                    s.commit()
                st.rerun()
        with c_p:
            st.write("📁 **Gestão de Projetos**")
            new_p = st.data_editor(df_projs, num_rows="dynamic", hide_index=True)
            if st.button("💾 Salvar Projetos"):
                with conn.session as s:
                    for r in new_p.itertuples():
                        s.execute(text("INSERT INTO projetos (nome) VALUES (:n) ON CONFLICT (nome) DO NOTHING"), {"n": r.nome})
                    s.commit()
                st.rerun()

# --- FOOTER ---
st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>OnCall Humana by Pedro Reis | v5.1 Master Pro Enterprise</p>", unsafe_allow_html=True)