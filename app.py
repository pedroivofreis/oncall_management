import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import uuid
import time

st.set_page_config(page_title="Gestão OnCall", layout="wide", page_icon="🚀")

# --- 1. CONEXÃO ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- 2. CARREGAMENTO E MIGRAÇÃO DE DADOS ---
try:
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "competencia", "colaborador_email", "projeto", "tipo", "horas", "descricao", "status_aprovaca", "data_decisao"])

# [MIGRAÇÃO] Garante que colunas novas existam nos dados velhos
# 1. Competência
if "competencia" not in df_lancamentos.columns:
    df_lancamentos["competencia"] = ""

# 2. Tipo (Front, Back, etc) - NOVO!
if "tipo" not in df_lancamentos.columns:
    df_lancamentos["tipo"] = "Geral" # Preenche antigos como Geral

# Preenche competências vazias (Correção retroativa)
mask_vazia = df_lancamentos["competencia"].isna() | (df_lancamentos["competencia"] == "") | (df_lancamentos["competencia"] == "nan")
if mask_vazia.any():
    datas_temp = pd.to_datetime(df_lancamentos.loc[mask_vazia, "data_registro"], errors='coerce')
    df_lancamentos.loc[mask_vazia, "competencia"] = datas_temp.dt.strftime("%Y-%m")
    df_lancamentos["competencia"] = df_lancamentos["competencia"].fillna(datetime.now().strftime("%Y-%m"))

# Garante status padrão
df_lancamentos["status_aprovaca"] = df_lancamentos["status_aprovaca"].fillna("Pendente").replace("", "Pendente")
df_lancamentos["tipo"] = df_lancamentos["tipo"].fillna("Geral").replace("nan", "Geral")

# --- 3. VARIÁVEIS GLOBAIS ---
try:
    user_email = st.user.email
    if user_email is None: raise Exception()
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# Limpa lista de projetos (remove vazios)
lista_projetos = df_config["projetos"].dropna().unique().tolist()
lista_projetos = [p for p in lista_projetos if p and str(p).lower() != "nan" and str(p).lower() != "none"]
if not lista_projetos: lista_projetos = ["Sistema de horas", "Outros"]

try:
    valor_hora_padrao = float(df_config["valor_hora"].dropna().iloc[0])
except:
    valor_hora_padrao = 100.0

# --- 4. ACESSO ---
if user_email not in ADMINS and user_email not in df_config["emails_autorizados"].values:
    st.error(f"🔒 Acesso negado para {user_email}.")
    st.stop()

# --- 5. INTERFACE ---
st.title("🚀 Gestão OnCall")

tabs_list = ["📝 Lançar"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Painel da Clau", "📊 BI & Financeiro", "⚙️ Config"]

abas = st.tabs(tabs_list)

# === ABA 1: LANÇAR (COM O NOVO CAMPO TIPO) ===
with abas[0]:
    st.caption(f"Logado como: {user_email}")
    with st.form("form_lan", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        proj = c1.selectbox("Projeto", lista_projetos)
        # NOVO CAMPO TIPO
        tipo_ativ = c2.selectbox("Tipo da Atividade", ["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Reunião/Alinhamento", "Outros"])
        hor = c3.number_input("Horas", min_value=0.5, step=0.5, format="%.1f")
        
        c4, c5 = st.columns([1, 2])
        comp_atual = datetime.now().strftime("%Y-%m")
        c4.text_input("Competência", value=comp_atual, disabled=True)
        desc = c5.text_area("Descrição detalhada")
        
        if st.form_submit_button("Enviar Registro"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "competencia": comp_atual,
                "colaborador_email": user_email,
                "projeto": proj,
                "tipo": tipo_ativ, # Salva o tipo
                "horas": hor,
                "descricao": desc,
                "status_aprovaca": "Pendente",
                "data_decisao": ""
            }])
            final = pd.concat([df_lancamentos, novo], ignore_index=True).astype(str)
            conn.update(worksheet="lancamentos", data=final)
            st.success("Sucesso! Registro enviado.")
            st.rerun()

# === ÁREA ADMIN ===
if user_email in ADMINS:
    
    # ABA 2: PAINEL DA CLAU
    with abas[1]:
        st.subheader("🛡️ Central de Controle")
        
        # --- IMPORTADOR ---
        with st.expander("📥 Importar Excel Retroativo"):
            st.info("O sistema agora aceita o formato padrão.")
            arquivo = st.file_uploader("Selecione o arquivo .xlsx", type=["xlsx"])
            
            if arquivo:
                try:
                    df_header = pd.read_excel(arquivo, header=None, nrows=2)
                    email_colab = str(df_header.iloc[0, 1]).strip()
                    
                    if "@" not in email_colab:
                        st.error("⚠️ E-mail não encontrado na célula B1.")
                    else:
                        df_excel = pd.read_excel(arquivo, header=4).dropna(subset=["Data", "Descrição"])
                        st.write(f"Colaborador: **{email_colab}** | Registros: {len(df_excel)}")
                        
                        if st.button("🚀 Processar"):
                            novos = []
                            for _, row in df_excel.iterrows():
                                try:
                                    raw_h = row["Horas"]
                                    if hasattr(raw_h, 'hour'): h_float = raw_h.hour + (raw_h.minute/60)
                                    else: h_float = float(str(raw_h).replace(",", "."))
                                except: h_float = 0.0
                                
                                if h_float <= 0: continue
                                
                                data_r = pd.to_datetime(row["Data"], errors='coerce')
                                if pd.isna(data_r): continue
                                
                                novos.append({
                                    "id": str(uuid.uuid4()),
                                    "data_registro": data_r.strftime("%Y-%m-%d %H:%M:%S"),
                                    "competencia": data_r.strftime("%Y-%m"),
                                    "colaborador_email": email_colab,
                                    "projeto": "Outros",
                                    "tipo": "Geral", # Padrão para importação
                                    "horas": h_float,
                                    "descricao": str(row["Descrição"]),
                                    "status_aprovaca": "Aprovado",
                                    "data_decisao": datetime.now().strftime("%Y-%m-%d")
                                })
                            
                            if novos:
                                df_fim = pd.concat([df_lancamentos, pd.DataFrame(novos)], ignore_index=True).astype(str)
                                conn.update(worksheet="lancamentos", data=df_fim)
                                st.success("Importado!")
                                time.sleep(1)
                                st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")

        st.divider()
        st.markdown("#### 📝 Edição Geral")
        
        # Editor atualizado com coluna TIPO
        edited_df = st.data_editor(
            df_lancamentos,
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Rejeitado"], required=True),
                "competencia": st.column_config.TextColumn("Competência"),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Outros"]),
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos),
                "data_registro": st.column_config.TextColumn("Data", disabled=True)
            },
            disabled=["id", "colaborador_email"],
            hide_index=True,
            num_rows="dynamic"
        )
        
        if st.button("💾 Salvar Alterações"):
            for i, row in edited_df.iterrows():
                if row["status_aprovaca"] != "Pendente" and (pd.isna(row["data_decisao"]) or row["data_decisao"] == ""):
                    edited_df.at[i, "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
            
            # Limpeza antes de salvar para evitar erros
            edited_df = edited_df.fillna("")
            conn.update(worksheet="lancamentos", data=edited_df.astype(str))
            st.success("Atualizado!")
            st.rerun()

    # ABA 3: BI
    with abas[2]:
        st.subheader("📊 Inteligência Financeira")
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        
        c_fil, c_kpi = st.columns([1, 3])
        with c_fil:
            meses = sorted([x for x in df_bi["competencia"].unique() if x], reverse=True)
            if not meses: meses = [datetime.now().strftime("%Y-%m")]
            mes = st.selectbox("Competência", ["TODOS"] + meses)
        
        df_view = df_bi if mes == "TODOS" else df_bi[df_bi["competencia"] == mes]
        aprov = df_view[df_view["status_aprovaca"] == "Aprovado"]
        
        tot_h = aprov["horas"].sum()
        with c_kpi:
            k1, k2, k3 = st.columns(3)
            k1.metric("Horas", f"{tot_h:.1f}h")
            k2.metric("Total R$", f"R$ {tot_h * valor_hora_padrao:,.2f}")
            k3.metric("Registros", len(aprov))
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            if not aprov.empty:
                st.markdown("### 👥 Colaboradores")
                grp = aprov.groupby("colaborador_email").agg(Horas=("horas", "sum")).reset_index()
                grp["R$"] = grp["Horas"] * valor_hora_padrao
                st.dataframe(grp, hide_index=True, use_container_width=True)
        with c2:
            if not aprov.empty:
                st.markdown("### 🛠️ Por Tipo de Atividade")
                st.bar_chart(aprov.groupby("tipo")["horas"].sum())

    # ABA 4: CONFIGURAÇÕES (CORRIGIDA)
    with abas[3]:
        st.subheader("Configurações")
        st.info("Adicione novos projetos nas linhas vazias abaixo.")
        
        conf_edit = st.data_editor(df_config, num_rows="dynamic")
        
        if st.button("Salvar Configurações"):
            # CORREÇÃO CRÍTICA: Preenche buracos com vazio antes de salvar
            # Isso evita que o Google Sheets rejeite linhas com 'None' ou 'NaN'
            conf_limpa = conf_edit.fillna("")
            conn.update(worksheet="config", data=conf_limpa.astype(str))
            st.success("Configuração salva com sucesso! (Recarregando...)")
            time.sleep(1)
            st.rerun()