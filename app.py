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

# --- 2. CARREGAMENTO ---
try:
    # ttl=0 é CRUCIAL para não pegar cache velho
    df_config = conn.read(worksheet="config", ttl=0)
    df_lancamentos = conn.read(worksheet="lancamentos", ttl=0)
except:
    df_config = pd.DataFrame(columns=["projetos", "emails_autorizados", "valor_hora"])
    df_lancamentos = pd.DataFrame(columns=["id", "data_registro", "competencia", "colaborador_email", "projeto", "tipo", "horas", "descricao", "status_aprovaca", "data_decisao"])

# Migração / Tratamento de colunas
if "competencia" not in df_lancamentos.columns: df_lancamentos["competencia"] = ""
if "tipo" not in df_lancamentos.columns: df_lancamentos["tipo"] = "Geral"

mask_vazia = df_lancamentos["competencia"].isna() | (df_lancamentos["competencia"] == "") | (df_lancamentos["competencia"] == "nan")
if mask_vazia.any():
    datas_temp = pd.to_datetime(df_lancamentos.loc[mask_vazia, "data_registro"], errors='coerce')
    df_lancamentos.loc[mask_vazia, "competencia"] = datas_temp.dt.strftime("%Y-%m")
    df_lancamentos["competencia"] = df_lancamentos["competencia"].fillna(datetime.now().strftime("%Y-%m"))

df_lancamentos["status_aprovaca"] = df_lancamentos["status_aprovaca"].fillna("Pendente").replace("", "Pendente")
df_lancamentos["tipo"] = df_lancamentos["tipo"].fillna("Geral").replace("nan", "Geral")

# --- 3. VARIÁVEIS GLOBAIS (LEITURA ROBUSTA) ---
try:
    # Limpeza profunda ao ler projetos
    raw_projs = df_config["projetos"].unique().tolist()
    lista_projetos = [str(x).strip() for x in raw_projs if str(x).lower() not in ["nan", "none", "", "0"]]
    if not lista_projetos: lista_projetos = ["Sistema de horas"]

    # Limpeza profunda ao ler emails
    raw_emails = df_config["emails_autorizados"].unique().tolist()
    lista_emails = [str(x).strip() for x in raw_emails if str(x).lower() not in ["nan", "none", "", "0"] and "@" in str(x)]
    
    try:
        valor_hora_padrao = float(df_config["valor_hora"].dropna().iloc[0])
    except:
        valor_hora_padrao = 100.0
except Exception as e:
    st.error(f"Erro ao ler configurações: {e}")
    st.stop()

try:
    user_email = st.user.email
    if user_email is None: raise Exception()
except:
    user_email = "pedroivofernandesreis@gmail.com"

ADMINS = ["pedroivofernandesreis@gmail.com", "claudiele.andrade@gmail.com"]

# --- 4. ACESSO ---
if user_email not in ADMINS and user_email not in lista_emails:
    st.error(f"🔒 Acesso negado para {user_email}.")
    st.stop()

# --- 5. INTERFACE ---
st.title("🚀 Gestão OnCall")

tabs_list = ["📝 Lançar"]
if user_email in ADMINS:
    tabs_list += ["🛡️ Painel da Clau", "📊 BI & Financeiro", "⚙️ Config"]

abas = st.tabs(tabs_list)

# === ABA 1: LANÇAR ===
with abas[0]:
    st.caption(f"Logado como: {user_email}")
    with st.form("form_lan", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        proj = c1.selectbox("Projeto", lista_projetos)
        tipo_ativ = c2.selectbox("Tipo", ["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Reunião", "Outros"])
        hor = c3.number_input("Horas", min_value=0.5, step=0.5, format="%.1f")
        
        c4, c5 = st.columns([1, 2])
        comp_atual = datetime.now().strftime("%Y-%m")
        c4.text_input("Competência", value=comp_atual, disabled=True)
        desc = c5.text_area("Descrição")
        
        if st.form_submit_button("Enviar Registro"):
            novo = pd.DataFrame([{
                "id": str(uuid.uuid4()),
                "data_registro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "competencia": comp_atual,
                "colaborador_email": user_email,
                "projeto": proj,
                "tipo": tipo_ativ,
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
        with st.expander("📥 Importar Excel Retroativo"):
            arquivo = st.file_uploader("Arquivo .xlsx", type=["xlsx"])
            if arquivo and st.button("Processar Importação"):
                try:
                    df_header = pd.read_excel(arquivo, header=None, nrows=2)
                    email_colab = str(df_header.iloc[0, 1]).strip()
                    if "@" in email_colab:
                        df_excel = pd.read_excel(arquivo, header=4).dropna(subset=["Data", "Descrição"])
                        novos = []
                        for _, row in df_excel.iterrows():
                            try:
                                h_val = row["Horas"]
                                if hasattr(h_val, 'hour'): h_float = h_val.hour + (h_val.minute/60)
                                else: h_float = float(str(h_val).replace(",", "."))
                            except: h_float = 0.0
                            
                            if h_float > 0:
                                d_real = pd.to_datetime(row["Data"], errors='coerce')
                                if not pd.isna(d_real):
                                    novos.append({
                                        "id": str(uuid.uuid4()),
                                        "data_registro": d_real.strftime("%Y-%m-%d %H:%M:%S"),
                                        "competencia": d_real.strftime("%Y-%m"),
                                        "colaborador_email": email_colab,
                                        "projeto": "Outros",
                                        "tipo": "Geral",
                                        "horas": h_float,
                                        "descricao": str(row["Descrição"]),
                                        "status_aprovaca": "Aprovado",
                                        "data_decisao": datetime.now().strftime("%Y-%m-%d")
                                    })
                        if novos:
                            final_imp = pd.concat([df_lancamentos, pd.DataFrame(novos)], ignore_index=True).astype(str)
                            conn.update(worksheet="lancamentos", data=final_imp)
                            st.success(f"{len(novos)} registros importados!")
                            time.sleep(1)
                            st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

        st.divider()
        st.markdown("#### 📝 Edição Geral")
        edited_df = st.data_editor(
            df_lancamentos,
            column_config={
                "status_aprovaca": st.column_config.SelectboxColumn("Status", options=["Pendente", "Aprovado", "Rejeitado"], required=True),
                "projeto": st.column_config.SelectboxColumn("Projeto", options=lista_projetos),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Front-end", "Back-end", "Banco de Dados", "Infraestrutura", "Reunião", "Outros"]),
                "data_registro": st.column_config.TextColumn("Data", disabled=True)
            },
            disabled=["id", "colaborador_email"], hide_index=True, num_rows="dynamic"
        )
        if st.button("💾 Salvar Alterações"):
            for i, row in edited_df.iterrows():
                if row["status_aprovaca"] != "Pendente" and (pd.isna(row["data_decisao"]) or row["data_decisao"] == ""):
                    edited_df.at[i, "data_decisao"] = datetime.now().strftime("%Y-%m-%d")
            conn.update(worksheet="lancamentos", data=edited_df.fillna("").astype(str))
            st.success("Salvo!")
            st.rerun()

    # ABA 3: BI
    with abas[2]:
        st.subheader("📊 Inteligência Financeira")
        df_bi = df_lancamentos.copy()
        df_bi["horas"] = pd.to_numeric(df_bi["horas"], errors="coerce").fillna(0)
        c_f, c_k = st.columns([1, 3])
        with c_f:
            ms = sorted([x for x in df_bi["competencia"].unique() if x], reverse=True)
            if not ms: ms = [datetime.now().strftime("%Y-%m")]
            sel_m = st.selectbox("Competência", ["TODOS"] + ms)
        view = df_bi if sel_m == "TODOS" else df_bi[df_bi["competencia"] == sel_m]
        apr = view[view["status_aprovaca"] == "Aprovado"]
        tot_h = apr["horas"].sum()
        with c_k:
            k1, k2, k3 = st.columns(3)
            k1.metric("Horas", f"{tot_h:.1f}h")
            k2.metric("Total R$", f"R$ {tot_h * valor_hora_padrao:,.2f}")
            k3.metric("Registros", len(apr))
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            if not apr.empty:
                grp = apr.groupby("colaborador_email").agg(Horas=("horas", "sum")).reset_index()
                grp["R$"] = grp["Horas"] * valor_hora_padrao
                st.dataframe(grp, hide_index=True, use_container_width=True)
        with c2:
            if not apr.empty: st.bar_chart(apr.groupby("tipo")["horas"].sum())

    # ABA 4: CONFIGURAÇÕES (CORRIGIDA E BLINDADA)
    with abas[3]:
        st.subheader("⚙️ Configurações do Sistema")
        
        col_proj, col_email, col_val = st.columns(3)
        
        with col_proj:
            st.markdown("##### 📂 Projetos Ativos")
            df_p = pd.DataFrame({"projetos": lista_projetos})
            edit_p = st.data_editor(df_p, num_rows="dynamic", key="edit_proj", hide_index=True, use_container_width=True)
            
        with col_email:
            st.markdown("##### 📧 Emails Autorizados")
            df_e = pd.DataFrame({"emails_autorizados": lista_emails})
            edit_e = st.data_editor(df_e, num_rows="dynamic", key="edit_email", hide_index=True, use_container_width=True)
            
        with col_val:
            st.markdown("##### 💰 Valor Hora (R$)")
            novo_valor = st.number_input("Valor Base", value=valor_hora_padrao, step=10.0)

        if st.button("💾 Salvar Configurações Gerais"):
            # 1. PEGA OS DADOS LIMPOS DOS EDITORES
            # O truque aqui é converter pra lista e limpar vazios/nones na força bruta
            novos_projetos = [str(p).strip() for p in edit_p["projetos"].tolist() if str(p).strip() not in ["", "nan", "None"]]
            novos_emails = [str(e).strip() for e in edit_e["emails_autorizados"].tolist() if str(e).strip() not in ["", "nan", "None"]]
            
            # 2. CALCULA O TAMANHO MÁXIMO (PARA CRIAR O QUADRADO)
            max_len = max(len(novos_projetos), len(novos_emails), 1)
            
            # 3. PREENCHE AS LISTAS MENORES COM STRING VAZIA "" (IMPORTANTE!)
            # O Google Sheets precisa que todas colunas tenham o mesmo tamanho
            novos_projetos += [""] * (max_len - len(novos_projetos))
            novos_emails += [""] * (max_len - len(novos_emails))
            valores_hora = [novo_valor] + [""] * (max_len - 1)
            
            # 4. CRIA O DATAFRAME FINAL PERFEITO
            df_salvar = pd.DataFrame({
                "projetos": novos_projetos,
                "emails_autorizados": novos_emails,
                "valor_hora": valores_hora
            })
            
            # 5. SALVA FORÇANDO TUDO PARA STRING
            conn.update(worksheet="config", data=df_salvar.astype(str))
            st.cache_data.clear() # Limpa o cache pra ver a mudança na hora
            st.success("✅ Configurações salvas no Google Sheets!")
            time.sleep(1.5)
            st.rerun()