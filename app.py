import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

st.set_page_config(page_title="Oncall Management - v8.2", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. CARREGAMENTO ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
    df_lancamentos.columns = [c.strip().lower() for c in df_lancamentos.columns]
    
    # Garantia da coluna email_enviado
    if 'email_enviado' not in df_lancamentos.columns:
        df_lancamentos['email_enviado'] = ""
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

# --- 3. CONFIGURAÇÕES & SENHAS (TRATAMENTO DE ERRO) ---
try:
    # Projetos independentes
    lista_projetos = df_config["projetos"].dropna().unique().tolist()
    
    # Validação da coluna 'senhas' para evitar o KeyError
    if "senhas" not in df_config.columns:
        st.error("⚠️ Coluna 'senhas' não encontrada na aba 'config'. Adicione-a para continuar.")
        st.stop()
        
    df_users = df_config[["emails_autorizados", "valor_hora", "senhas"]].dropna(subset=["emails_autorizados"])
    dict_users = {}
    for _, row in df_users.iterrows():
        dict_users[row["emails_autorizados"].strip()] = {
            "valor": pd.to_numeric(row["valor_hora"], errors='coerce') or 0,
            "senha": str(row["senhas"]).strip()
        }
    ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]
except Exception as e:
    st.error(f"Erro na estrutura das configurações: {e}")
    st.stop()

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
    st.info("👈 Identifique-se para acessar seu painel.")
    st.stop()

# --- 5. INTERFACE ---
tabs_list = ["📝 Lançar", "📊 Meu Dashboard"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Gerencial", "📈 BI Financeiro", "⚙️ Configurações"]
tabs = st.tabs(tabs_list)

# === ABA: LANÇAR (INCLUI UPLOAD EM MASSA) ===
with tabs[0]:
    metodo = st.radio("Método de Lançamento:", ["Individual", "Em Massa (CSV/Excel)"], horizontal=True)
    
    if metodo == "Individual":
        with st.form("form_lan", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            proj = c1.selectbox("Projeto", lista_projetos)
            tipo = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infra", "Testes", "Reunião", "Outros"])
            data_f = c3.date_input("Data da Atividade", value=datetime.now())
            hrs = st.number_input("Horas", min_value=0.5, step=0.5)
            desc = st.text_area("Descrição")
            if st.form_submit_button("Enviar Lançamento"):
                novo = {
                    "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "colaborador_email": user_email, "projeto": proj, "horas": str(hrs),
                    "status_aprovaca": "Pendente", "data_decisao": "", "competencia": data_f.strftime("%Y-%m"),
                    "tipo": tipo, "descricão": desc, "email_enviado": ""
                }
                ordem = ["id", "data_registro", "colaborador_email", "projeto", "horas", 
                         "status_aprovaca", "data_decisao", "competencia", "tipo", "descricão", "email_enviado"]
                df_final = pd.concat([df_lancamentos, pd.DataFrame([novo])[ordem]], ignore_index=True)
                conn.update(worksheet="lancamentos", data=df_final.astype(str))
                st.success("✅ Lançado!"); time.sleep(1); st.rerun()

    else:
        st.info("O arquivo deve conter as colunas: projeto, horas, tipo, descricão, data (YYYY-MM-DD)")
        arquivo = st.file_uploader("Subir arquivo", type=["csv", "xlsx"])
        if arquivo:
            try:
                df_massa = pd.read_csv(arquivo) if arquivo.name.endswith('.csv') else pd.read_excel(arquivo)
                if st.button("Confirmar Importação"):
                    novos_registros = []
                    for _, r in df_massa.iterrows():
                        novos_registros.append({
                            "id": str(uuid.uuid4()), "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "colaborador_email": user_email, "projeto": r["projeto"], "horas": str(r["horas"]),
                            "status_aprovaca": "Pendente", "data_decisao": "", 
                            "competencia": str(r["data"])[:7], "tipo": r["tipo"], "descricão": r["descricão"], "email_enviado": ""
                        })
                    df_final = pd.concat([df_lancamentos, pd.DataFrame(novos_registros)], ignore_index=True)
                    conn.update(worksheet="lancamentos", data=df_final.astype(str))
                    st.success(f"✅ {len(novos_registros)} registros importados!"); time.sleep(1); st.rerun()
            except Exception as e:
                st.error(f"Erro no formato do arquivo: {e}")

# === ABA: MEU DASHBOARD ===
with tabs[1]:
    meus_dados = df_lancamentos[df_lancamentos["colaborador_email"] == user_email].copy()
    meus_dados["horas"] = pd.to_numeric(meus_dados["horas"], errors="coerce").fillna(0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aprovadas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Aprovado']['horas'].sum()}h")
    c2.metric("Negadas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Rejeitado']['horas'].sum()}h")
    c3.metric("Pagas", f"{meus_dados[meus_dados['status_aprovaca'] == 'Pago']['horas'].sum()}h")
    c4.metric("Pendentes", f"{meus_dados[meus_dados['status_aprovaca'] == 'Pendente']['horas'].sum()}h")
    st.dataframe(meus_dados, use_container_width=True, hide_index=True)

# === ÁREA ADMIN ===
if user_email in ADMINS:
    with tabs[2]: # GERENCIAL
        sub1, sub2 = st.tabs(["✓ Aprovações", "💰 Pagamentos"])
        with sub1:
            df_edit = st.data_editor(df_lancamentos, hide_index=True)
            if st.button("Salvar Edições"):
                conn.update(worksheet="lancamentos", data=df_edit.astype(str))
                st.success("Salvo!"); st.rerun()
        with sub2:
            comp = st.selectbox("Mês de Referência:", sorted(df_lancamentos["competencia"].unique(), reverse=True))
            df_p = df_lancamentos[(df_lancamentos["competencia"] == comp) & (df_lancamentos["status_aprovaca"] == "Aprovado")].copy()
            df_p["horas"] = pd.to_numeric(df_p["horas"], errors="coerce").fillna(0)
            df_p["total"] = df_p["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0)) * df_p["horas"]
            st.table(df_p.groupby("colaborador_email")["total"].sum().reset_index())
            if st.button(f"Marcar {comp} como PAGO"):
                df_lancamentos.loc[(df_lancamentos["competencia"] == comp) & (df_lancamentos["status_aprovaca"] == "Aprovado"), "status_aprovaca"] = "Pago"
                conn.update(worksheet="lancamentos", data=df_lancamentos.astype(str))
                st.success("Pagamentos registrados!"); st.rerun()

    with tabs[3]: # BI
        filt = st.multiselect("Competências:", sorted(df_lancamentos["competencia"].unique()), default=sorted(df_lancamentos["competencia"].unique()))
        df_bi = df_lancamentos[df_lancamentos["competencia"].isin(filt)].copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        df_bi["custo"] = df_bi["horas"] * df_bi["colaborador_email"].map(lambda x: dict_users.get(x, {}).get("valor", 0))
        validos = df_bi[df_bi["status_aprovaca"].isin(["Aprovado", "Pago"])]
        st.metric("Custo Total no Período", f"R$ {validos['custo'].sum():,.2f}")
        st.bar_chart(validos.groupby("projeto")["custo"].sum())

    with tabs[4]: # CONFIG
        conf_edit = st.data_editor(df_config, num_rows="dynamic", hide_index=True)
        if st.button("Salvar Configurações"):
            conn.update(worksheet="config", data=conf_edit.astype(str))
            st.success("Configurações atualizadas!"); st.rerun()