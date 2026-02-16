import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time
import io

# Configuração da Página
st.set_page_config(page_title="Oncall Management - v8.8", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CARREGAMENTO ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
    df_lancamentos.columns = [c.strip().lower() for c in df_lancamentos.columns]
    
    # GARANTIA DE COLUNAS: Evita o erro KeyError das imagens 9924c8 e 999542
    colunas_obrigatorias = ['email_enviado', 'valor_hora_historico']
    for col in colunas_obrigatorias:
        if col not in df_lancamentos.columns:
            df_lancamentos[col] = ""
            
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# --- 3. CONFIGURAÇÕES INDEPENDENTES ---
# Projetos lidos de forma totalmente isolada da coluna D
lista_projetos = df_config["projetos"].dropna().astype(str).str.strip().unique().tolist()

# Usuários lidos das colunas A, B e C
if "senhas" not in df_config.columns:
    st.error("⚠️ Coluna 'senhas' não encontrada na aba 'config'.")
    st.stop()

df_u = df_config[["emails_autorizados", "valor_hora", "senhas"]].dropna(subset=["emails_autorizados"])
dict_users = {}
for _, row in df_u.iterrows():
    dict_users[row["emails_autorizados"].strip()] = {
        "valor": pd.to_numeric(row["valor_hora"], errors='coerce') or 0,
        "senha": str(row["senhas"]).strip()
    }

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. LOGIN ---
st.sidebar.title("🔐 Acesso OnCall")
user_email = st.sidebar.selectbox("Usuário:", options=["Selecione..."] + sorted(list(dict_users.keys())))
autenticado = False

if user_email != "Selecione...":
    senha_digitada = st.sidebar.text_input("Senha:", type="password")
    if senha_digitada == dict_users[user_email]["senha"]:
        autenticado = True
    elif senha_digitada:
        st.sidebar.error("Senha incorreta.")

if not autenticado:
    st.info("👈 Identifique-se na lateral para acessar.")
    st.stop()

# --- 5. INTERFACE ---
tabs_list = ["📝 Lançar Horas", "📊 Meu Dashboard"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Gerencial", "📈 BI Financeiro", "⚙️ Configurações"]
tabs = st.tabs(tabs_list)

# === ABA: LANÇAR HORAS ===
with tabs[0]:
    metodo = st.radio("Forma de Lançamento:", ["Lançamento Dinâmico (+)", "Importação (.xlsx)"], horizontal=True)
    
    if metodo == "Lançamento Dinâmico (+)":
        df_template = pd.DataFrame(columns=["projeto", "tipo", "data", "horas", "descricão"])
        df_editor = st.data_editor(
            df_template, num_rows="dynamic", use_container_width=True,
            column_config={
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos, required=True),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião", "Outros"], required=True),
                "data": st.column_config.DateColumn("Data", default=datetime.now(), required=True),
                "horas": st.column_config.NumberColumn("Horas", min_value=0.5, step=0.5, required=True),
                "descricão": st.column_config.TextColumn("Descrição", required=True)
            }
        )
        if st.button("🚀 Enviar Lançamentos"):
            if not df_editor.empty:
                valor_atual = dict_users[user_email]["valor"]
                novos = []
                for _, r in df_editor.iterrows():
                    novos.append({
                        "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]),
                        "status_aprovaca": "Pendente", "data_decisao": "", 
                        "competencia": r["data"].strftime("%Y-%m") if hasattr(r["data"], 'strftime') else str(r["data"])[:7], 
                        "tipo": r["tipo"], "descricão": r["descricão"], 
                        "email_enviado": "", "valor_hora_historico": str(valor_atual)
                    })
                df_final = pd.concat([df_lancamentos, pd.DataFrame(novos)], ignore_index=True)
                conn.update(worksheet="lancamentos", data=df_final.astype(str))
                st.success("✅ Enviado!"); time.sleep(1); st.rerun()

    else:
        # GERAÇÃO DE MODELO XLSX
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=["projeto","horas","tipo","descricão","data"]).to_excel(writer, index=False)
        st.download_button("📥 Baixar Modelo .xlsx", data=buffer.getvalue(), file_name="modelo_oncall.xlsx")
        
        arquivo = st.file_uploader("Subir arquivo (.xlsx)", type=["xlsx"])
        if arquivo and st.button("Confirmar Importação"):
            df_m = pd.read_excel(arquivo)
            valor_atual = dict_users[user_email]["valor"]
            novos_m = []
            for _, r in df_m.iterrows():
                novos_m.append({
                    "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]),
                    "status_aprovaca": "Pendente", "data_decisao": "", 
                    "competencia": str(r["data"])[:7], "tipo": r["tipo"], "descricão": r["descricão"], 
                    "email_enviado": "", "valor_hora_historico": str(valor_atual)
                })
            df_final = pd.concat([df_lancamentos, pd.DataFrame(novos_m)], ignore_index=True)
            conn.update(worksheet="lancamentos", data=df_final.astype(str)); st.rerun()

# === ABA: MEU DASHBOARD ===
with tabs[1]:
    meus_dados = df_lancamentos[df_lancamentos["colaborador_email"] == user_email].copy()
    meus_dados["horas"] = pd.to_numeric(meus_dados["horas"], errors="coerce").fillna(0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aprovadas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Aprovado']['horas'].sum():.1f}h")
    c2.metric("Pagas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Pago']['horas'].sum():.1f}h")
    c3.metric("Pendentes", f"{meus_dados[meus_dados['status_aprovaca'] == 'Pendente']['horas'].sum():.1f}h")
    c4.metric("Rejeitadas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Rejeitado']['horas'].sum():.1f}h")
    st.dataframe(meus_dados.sort_values("data_registro", ascending=False), use_container_width=True, hide_index=True)

# === ÁREA ADMIN ===
if user_email in ADMINS:
    with tabs[2]: # GERENCIAL
        sub1, sub2 = st.tabs(["✓ Aprovações", "💰 Financeiro"])
        with sub1:
            df_ed = st.data_editor(df_lancamentos, hide_index=True, use_container_width=True)
            if st.button("💾 Salvar Alterações"):
                conn.update(worksheet="lancamentos", data=df_ed.astype(str)); st.rerun()
        with sub2:
            mes = st.selectbox("Mês Referência:", sorted(df_lancamentos["competencia"].unique(), reverse=True))
            df_p = df_lancamentos[(df_lancamentos["competencia"] == mes) & (df_lancamentos["status_aprovaca"] == "Aprovado")].copy()
            df_p["horas"] = pd.to_numeric(df_p["horas"], errors="coerce").fillna(0)
            
            # PROTEÇÃO FINANCEIRA: Usa o valor histórico congelado ou o atual se for lançamento antigo
            df_p["v_h"] = pd.to_numeric(df_p["valor_hora_historico"], errors="coerce").fillna(
                df_p["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0))
            )
            df_p["total"] = df_p["v_h"] * df_p["horas"]
            
            st.dataframe(df_p.groupby("colaborador_email")["total"].sum().reset_index(), use_container_width=True)
            if st.button(f"Confirmar Pagamento de {mes}"):
                df_lancamentos.loc[(df_lancamentos["competencia"] == mes) & (df_lancamentos["status_aprovaca"] == "Aprovado"), "status_aprovaca"] = "Pago"
                conn.update(worksheet="lancamentos", data=df_lancamentos.astype(str)); st.rerun()

    with tabs[3]: # BI FINANCEIRO RESTAURADO
        filt = st.multiselect("Filtrar Meses:", sorted(df_lancamentos["competencia"].unique()), default=sorted(df_lancamentos["competencia"].unique()))
        df_bi = df_lancamentos[df_lancamentos["competencia"].isin(filt)].copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["v_h"] = pd.to_numeric(df_bi["valor_hora_historico"], errors="coerce").fillna(
            df_bi["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0))
        )
        df_bi["custo"] = df_bi["horas"] * df_bi["v_h"]
        
        validos = df_bi[df_bi["status_aprovaca"].isin(["Aprovado", "Pago"])]
        
        m1, m2 = st.columns(2)
        m1.metric("Investimento Total", f"R$ {validos['custo'].sum():,.2f}")
        m2.metric("Horas Totais", f"{validos['horas'].sum():.1f}h")
        
        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("### 🏗️ Custo por Projeto")
            st.bar_chart(validos.groupby("projeto")["custo"].sum(), color="#2e7d32")
        with g2:
            st.markdown("### 🛠️ Horas por Tipo")
            st.bar_chart(validos.groupby("tipo")["horas"].sum(), color="#29b5e8")

    with tabs[4]: # CONFIGURAÇÕES
        st.info("💡 Coluna 'Projetos' é independente. Gerencie Usuários (A, B, C) e Projetos (D) aqui.")
        conf_ed = st.data_editor(df_config, num_rows="dynamic", hide_index=True, use_container_width=True)
        if st.button("💾 Salvar Configurações"):
            conn.update(worksheet="config", data=conf_ed.astype(str)); st.rerun()

# --- RODAPÉ ---
st.markdown("---")
st.markdown(f"<p style='text-align: center; color: grey;'>Projeto by <b>Pedro Reis</b> | OnCall Management v8.8</p>", unsafe_allow_html=True)